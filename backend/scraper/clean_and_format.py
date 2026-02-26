"""
Clean raw speeches and generate synthetic Q&A training pairs using AWS Bedrock.

Local mode (default):
  Input:  backend/scraper/data/raw_speeches.jsonl
  Output: backend/scraper/data/training_data.jsonl

S3 mode (--bucket / --output-bucket):
  Input:  s3://{bucket}/raw/individual/*.jsonl
  Output: s3://{output-bucket}/training_data.jsonl
"""

import argparse
import json
import logging
import random
import re
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
INPUT_FILE = DATA_DIR / "raw_speeches.jsonl"
OUTPUT_FILE = DATA_DIR / "training_data.jsonl"

BEDROCK_MODEL_ID = "eu.anthropic.claude-sonnet-4-20250514-v1:0"

# AWS Bedrock client (uses AWS credentials from environment / instance profile)
bedrock = boto3.client("bedrock-runtime")

SYSTEM_PROMPT = """\
You are a data-preparation assistant. Given a speech by Barack Obama, generate \
3-5 question-answer pairs suitable for fine-tuning an LLM to respond in Obama's \
distinctive speaking style.

Rules:
- Questions should be about substantive topics covered in the speech (policy, \
values, events, etc.)
- Answers should be 2-4 paragraphs and written in Obama's voice: thoughtful, \
measured, using phrases like "Look," "Let me be clear," "Here's the thing," \
inclusive language ("we" over "I"), acknowledging complexity, building to \
an uplifting conclusion
- Do NOT simply quote the speech verbatim — synthesize and paraphrase in \
Obama's style
- Return valid JSON: an array of objects with "instruction" and "output" keys
- "instruction" = the question, "output" = the Obama-style answer
"""

QA_GENERATION_PROMPT = """\
Speech title: {title}
Date: {date}

Speech text (may be truncated):
{text}

Generate 3-5 Q&A pairs as described. Return ONLY the JSON array, no other text.
"""


def clean_text(text: str) -> str:
    """Clean speech text: normalize whitespace, remove artifacts."""
    # Remove common artifacts
    text = re.sub(r"\[applause\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[laughter\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[crosstalk\]", "", text, flags=re.IGNORECASE)
    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def generate_qa_pairs(speech: dict) -> tuple[list[dict], dict]:
    """Use AWS Bedrock to generate Q&A pairs from a speech.

    Returns (pairs, usage) where usage has inputTokens/outputTokens.
    """
    text = speech["text"]
    # Truncate to ~6000 chars to stay within reasonable token limits
    if len(text) > 6000:
        text = text[:6000] + "\n\n[truncated]"

    prompt = QA_GENERATION_PROMPT.format(
        title=speech.get("title", "Unknown"),
        date=speech.get("date", "Unknown"),
        text=text,
    )

    try:
        response = bedrock.converse(
            modelId=BEDROCK_MODEL_ID,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 2000},
        )

        usage = response.get("usage", {})
        content = response["output"]["message"]["content"][0]["text"].strip()

        # Extract JSON array from response
        # Handle cases where Claude wraps in markdown code blocks
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\n?", "", content)
            content = re.sub(r"\n?```$", "", content)

        pairs = json.loads(content)
        if not isinstance(pairs, list):
            return [], usage

        # Validate and format
        valid_pairs = []
        for pair in pairs:
            if "instruction" in pair and "output" in pair:
                valid_pairs.append(
                    {
                        "instruction": pair["instruction"],
                        "input": "",
                        "output": pair["output"],
                    }
                )
        return valid_pairs, usage

    except (json.JSONDecodeError, ClientError) as e:
        logger.warning("Failed to generate Q&A for '%s': %s", speech.get("title"), e)
        return [], {}


def load_speeches_from_s3(bucket: str) -> list[dict]:
    """Load individual speech files from s3://{bucket}/raw/individual/*.jsonl."""
    s3 = boto3.client("s3")
    prefix = "raw/individual/"
    keys: list[str] = []

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".jsonl"):
                keys.append(obj["Key"])

    logger.info("Found %d speech files in s3://%s/%s", len(keys), bucket, prefix)

    speeches: list[dict] = []
    for key in keys:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode()
        for line in body.strip().splitlines():
            if line.strip():
                speeches.append(json.loads(line))

    return speeches


def upload_to_s3(local_path: Path, bucket: str, key: str) -> None:
    """Upload a local file to S3."""
    s3 = boto3.client("s3")
    s3.upload_file(str(local_path), bucket, key)
    logger.info("Uploaded %s to s3://%s/%s", local_path, bucket, key)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean speeches and generate Q&A pairs"
    )
    parser.add_argument("--bucket", help="S3 bucket to read raw speeches from")
    parser.add_argument(
        "--output-bucket", help="S3 bucket to write training_data.jsonl to"
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="Randomly sample N speeches (0 = all, default)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sampling")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    # Load speeches
    if args.bucket:
        speeches = load_speeches_from_s3(args.bucket)
    else:
        if not INPUT_FILE.exists():
            logger.error("Input file not found: %s", INPUT_FILE)
            logger.error("Run scrape_speeches.py first.")
            sys.exit(1)

        speeches = []
        with open(INPUT_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    speeches.append(json.loads(line))

    logger.info("Loaded %d speeches", len(speeches))

    # Sample if requested
    if args.sample > 0 and args.sample < len(speeches):
        random.seed(args.seed)
        speeches = random.sample(speeches, args.sample)
        logger.info("Sampled %d speeches (seed=%d)", args.sample, args.seed)

    # Clean texts
    for s in speeches:
        s["text"] = clean_text(s["text"])

    # Claude Sonnet 4 pricing (per 1M tokens)
    INPUT_COST_PER_M = 3.0
    OUTPUT_COST_PER_M = 15.0

    # Generate Q&A pairs
    all_pairs: list[dict] = []
    total_input_tokens = 0
    total_output_tokens = 0
    for i, speech in enumerate(speeches, 1):
        pairs, usage = generate_qa_pairs(speech)
        all_pairs.extend(pairs)
        total_input_tokens += usage.get("inputTokens", 0)
        total_output_tokens += usage.get("outputTokens", 0)
        if pairs:
            logger.info(
                "[%d/%d] Generated %d pairs for: %s",
                i,
                len(speeches),
                len(pairs),
                speech.get("title", "")[:60],
            )
        else:
            logger.info(
                "[%d/%d] No pairs for: %s",
                i,
                len(speeches),
                speech.get("title", "")[:60],
            )
        if i % 100 == 0:
            cost = (total_input_tokens * INPUT_COST_PER_M / 1e6) + (
                total_output_tokens * OUTPUT_COST_PER_M / 1e6
            )
            logger.info(
                "Token usage so far: %d input, %d output — est. cost $%.2f",
                total_input_tokens,
                total_output_tokens,
                cost,
            )

    total_cost = (total_input_tokens * INPUT_COST_PER_M / 1e6) + (
        total_output_tokens * OUTPUT_COST_PER_M / 1e6
    )
    logger.info("Total Q&A pairs generated: %d", len(all_pairs))
    logger.info(
        "Total tokens: %d input, %d output — est. cost $%.2f",
        total_input_tokens,
        total_output_tokens,
        total_cost,
    )

    # Write output
    with open(OUTPUT_FILE, "w") as f:
        for pair in all_pairs:
            f.write(json.dumps(pair) + "\n")

    logger.info("Saved to %s", OUTPUT_FILE)

    # Upload to S3 if requested
    if args.output_bucket:
        upload_to_s3(OUTPUT_FILE, args.output_bucket, "training_data.jsonl")


if __name__ == "__main__":
    main()

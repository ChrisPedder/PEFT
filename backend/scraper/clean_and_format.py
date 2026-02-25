"""
Clean raw speeches and generate synthetic Q&A training pairs using AWS Bedrock.

Input:  backend/scraper/data/raw_speeches.jsonl
Output: backend/scraper/data/training_data.jsonl
"""

import json
import logging
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

BEDROCK_MODEL_ID = "anthropic.claude-sonnet-4-20250514-v1:0"

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


def generate_qa_pairs(speech: dict) -> list[dict]:
    """Use AWS Bedrock to generate Q&A pairs from a speech."""
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

        content = response["output"]["message"]["content"][0]["text"].strip()

        # Extract JSON array from response
        # Handle cases where Claude wraps in markdown code blocks
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\n?", "", content)
            content = re.sub(r"\n?```$", "", content)

        pairs = json.loads(content)
        if not isinstance(pairs, list):
            return []

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
        return valid_pairs

    except (json.JSONDecodeError, ClientError) as e:
        logger.warning("Failed to generate Q&A for '%s': %s", speech.get("title"), e)
        return []


def main() -> None:
    if not INPUT_FILE.exists():
        logger.error("Input file not found: %s", INPUT_FILE)
        logger.error("Run scrape_speeches.py first.")
        sys.exit(1)

    # Load raw speeches
    speeches: list[dict] = []
    with open(INPUT_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                speeches.append(json.loads(line))

    logger.info("Loaded %d speeches", len(speeches))

    # Clean texts
    for s in speeches:
        s["text"] = clean_text(s["text"])

    # Generate Q&A pairs
    all_pairs: list[dict] = []
    for i, speech in enumerate(speeches, 1):
        pairs = generate_qa_pairs(speech)
        all_pairs.extend(pairs)
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

    logger.info("Total Q&A pairs generated: %d", len(all_pairs))

    # Write output
    with open(OUTPUT_FILE, "w") as f:
        for pair in all_pairs:
            f.write(json.dumps(pair) + "\n")

    logger.info("Saved to %s", OUTPUT_FILE)


if __name__ == "__main__":
    main()

"""
Upload raw scraped speeches to S3.

Usage:
    python upload_to_s3.py [--bucket BUCKET_NAME]
"""

import argparse
import logging
from pathlib import Path

import boto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload raw speeches to S3")
    parser.add_argument(
        "--bucket",
        default=None,
        help="S3 bucket name (defaults to peft-speech-data-<account_id>)",
    )
    args = parser.parse_args()

    s3 = boto3.client("s3")
    sts = boto3.client("sts")

    bucket = args.bucket
    if not bucket:
        account_id = sts.get_caller_identity()["Account"]
        bucket = f"peft-speech-data-{account_id}"

    files_to_upload = [
        ("raw_speeches.jsonl", "raw/speeches.jsonl"),
    ]

    for local_name, s3_key in files_to_upload:
        local_path = DATA_DIR / local_name
        if local_path.exists():
            logger.info("Uploading %s -> s3://%s/%s", local_name, bucket, s3_key)
            s3.upload_file(str(local_path), bucket, s3_key)
            logger.info("Done (%s bytes)", f"{local_path.stat().st_size:,}")
        else:
            logger.info("Skipping %s (not found)", local_name)

    logger.info("Upload complete.")


if __name__ == "__main__":
    main()

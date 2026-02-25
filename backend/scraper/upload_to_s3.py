"""
Upload raw scraped speeches to S3.

Usage:
    python upload_to_s3.py [--bucket BUCKET_NAME]
"""

import argparse
from pathlib import Path

import boto3

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
            print(f"Uploading {local_name} → s3://{bucket}/{s3_key}")
            s3.upload_file(str(local_path), bucket, s3_key)
            print(f"  Done ({local_path.stat().st_size:,} bytes)")
        else:
            print(f"Skipping {local_name} (not found)")

    print("\nUpload complete.")


if __name__ == "__main__":
    main()

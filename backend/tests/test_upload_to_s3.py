"""Tests for backend/scraper/upload_to_s3.py."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


@mock_aws
def test_upload_with_explicit_bucket(tmp_path):
    """Uploads files to S3 when --bucket is provided explicitly."""
    # Create the bucket
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="my-custom-bucket")

    # Create temp data files
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "raw_speeches.jsonl").write_text('{"title":"test"}\n')
    (data_dir / "training_data.jsonl").write_text('{"instruction":"q"}\n')

    with (
        patch("sys.argv", ["upload_to_s3.py", "--bucket", "my-custom-bucket"]),
        patch("backend.scraper.upload_to_s3.DATA_DIR", data_dir),
    ):
        from backend.scraper.upload_to_s3 import main

        main()

    # Verify objects were uploaded
    objs = s3.list_objects_v2(Bucket="my-custom-bucket")
    keys = [o["Key"] for o in objs["Contents"]]
    assert "raw/speeches.jsonl" in keys
    assert "processed/training_data.jsonl" in keys


@mock_aws
def test_upload_auto_bucket(tmp_path):
    """Auto-detects account ID and constructs the bucket name when --bucket is omitted."""
    # moto STS returns a known account ID
    sts = boto3.client("sts", region_name="us-east-1")
    account_id = sts.get_caller_identity()["Account"]
    bucket_name = f"peft-speech-data-{account_id}"

    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=bucket_name)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "raw_speeches.jsonl").write_text('{"title":"test"}\n')
    (data_dir / "training_data.jsonl").write_text('{"instruction":"q"}\n')

    with (
        patch("sys.argv", ["upload_to_s3.py"]),
        patch("backend.scraper.upload_to_s3.DATA_DIR", data_dir),
    ):
        from backend.scraper.upload_to_s3 import main

        main()

    objs = s3.list_objects_v2(Bucket=bucket_name)
    keys = [o["Key"] for o in objs["Contents"]]
    assert "raw/speeches.jsonl" in keys
    assert "processed/training_data.jsonl" in keys


@mock_aws
def test_upload_skips_missing_files(tmp_path):
    """Missing local files are skipped without raising errors."""
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="my-bucket")

    # Create data dir with only one of the expected files
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "raw_speeches.jsonl").write_text('{"title":"test"}\n')
    # training_data.jsonl deliberately missing

    with (
        patch("sys.argv", ["upload_to_s3.py", "--bucket", "my-bucket"]),
        patch("backend.scraper.upload_to_s3.DATA_DIR", data_dir),
    ):
        from backend.scraper.upload_to_s3 import main

        main()

    objs = s3.list_objects_v2(Bucket="my-bucket")
    keys = [o["Key"] for o in objs["Contents"]]
    assert "raw/speeches.jsonl" in keys
    assert "processed/training_data.jsonl" not in keys

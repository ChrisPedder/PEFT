"""Shared fixtures for the PEFT backend test suite."""

import json
import os
import tempfile
from pathlib import Path

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Create a temp directory with sample JSONL files."""
    raw_speeches = [
        {
            "title": "Inaugural Address",
            "date": "January 20, 2009",
            "source": "app",
            "url": "https://www.presidency.ucsb.edu/documents/inaugural-address-14",
            "text": "My fellow citizens: I stand here today humbled by the task before us. "
            * 20,
        },
        {
            "title": "Remarks on the Economy",
            "date": "February 4, 2009",
            "source": "wh_archives",
            "url": "https://obamawhitehouse.archives.gov/remarks-economy",
            "text": "Good morning, everybody. This morning I want to talk about the economy. "
            * 20,
        },
    ]
    training_data = [
        {
            "instruction": "What was the main theme of your inaugural address?",
            "input": "",
            "output": "Look, the main theme of my inaugural address was about responsibility.",
        },
        {
            "instruction": "How did you approach economic policy?",
            "input": "",
            "output": "Let me be clear, we inherited a crisis unlike any we had seen.",
        },
    ]

    raw_path = tmp_path / "raw_speeches.jsonl"
    with open(raw_path, "w") as f:
        for speech in raw_speeches:
            f.write(json.dumps(speech) + "\n")

    training_path = tmp_path / "training_data.jsonl"
    with open(training_path, "w") as f:
        for pair in training_data:
            f.write(json.dumps(pair) + "\n")

    return tmp_path


@pytest.fixture
def mock_s3():
    """Moto S3 mock that creates the peft-speech-data bucket."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="peft-speech-data-123456789012")
        yield s3


@pytest.fixture
def mock_dynamodb():
    """Moto DynamoDB mock that creates the peft-training-metrics table."""
    with mock_aws():
        dynamodb = boto3.client("dynamodb", region_name="us-east-1")
        dynamodb.create_table(
            TableName="peft-training-metrics",
            KeySchema=[
                {"AttributeName": "job_id", "KeyType": "HASH"},
                {"AttributeName": "timestamp", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield dynamodb


@pytest.fixture
def sample_speech():
    """Return a sample speech dict."""
    return {
        "title": "Remarks by the President on the Economy",
        "date": "June 14, 2010",
        "source": "app",
        "url": "https://www.presidency.ucsb.edu/documents/remarks-economy-42",
        "text": "Thank you. Thank you so much. Please, have a seat. "
        "I want to talk today about the economy and where we go from here. " * 15,
    }


@pytest.fixture
def sample_training_pair():
    """Return a sample training pair dict."""
    return {
        "instruction": "What is your approach to bipartisan cooperation?",
        "input": "",
        "output": (
            "Look, I've always believed that we can find common ground if "
            "we're willing to listen to each other. Here's the thing -- "
            "our democracy works best when we engage in honest debate."
        ),
    }

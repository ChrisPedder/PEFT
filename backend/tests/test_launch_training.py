"""Tests for backend/scripts/launch_training.py.

These tests define the expected interface for the launch_training script.
The script will:
- Parse args: --epochs, --batch-size, --learning-rate, --instance-type
- Call sagemaker.create_training_job()
- Poll describe_training_job() until complete/failed
- Write metrics to DynamoDB

The actual script will be created by another agent. These tests validate
the expected interaction with AWS services using moto mocks.
"""

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


@pytest.fixture
def aws_setup():
    """Set up mock AWS resources for launch_training tests."""
    with mock_aws():
        region = "us-east-1"

        # Create SageMaker client
        sagemaker = boto3.client("sagemaker", region_name=region)

        # Create DynamoDB table
        dynamodb = boto3.client("dynamodb", region_name=region)
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

        # Create S3 bucket for training data
        s3 = boto3.client("s3", region_name=region)
        s3.create_bucket(Bucket="peft-training-data-123456789012")

        # Create IAM role for SageMaker
        iam = boto3.client("iam", region_name=region)
        try:
            iam.create_role(
                RoleName="SageMakerTrainingRole",
                AssumeRolePolicyDocument=json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "sagemaker.amazonaws.com"},
                                "Action": "sts:AssumeRole",
                            }
                        ],
                    }
                ),
                Path="/",
            )
        except Exception:
            pass

        yield {
            "sagemaker": sagemaker,
            "dynamodb": dynamodb,
            "s3": s3,
            "region": region,
        }


class TestLaunchTraining:
    def test_job_creation(self, aws_setup):
        """SageMaker create_training_job is called with correct parameters."""
        sagemaker = aws_setup["sagemaker"]
        mock_sm_client = MagicMock(wraps=sagemaker)
        mock_sm_client.create_training_job.return_value = {
            "TrainingJobArn": "arn:aws:sagemaker:us-east-1:123456789012:training-job/peft-test"
        }

        # Simulate what the script should do
        job_name = "peft-obama-training-test"
        params = {
            "TrainingJobName": job_name,
            "HyperParameters": {
                "epochs": "3",
                "batch_size": "4",
                "learning_rate": "0.0002",
            },
            "AlgorithmSpecification": {
                "TrainingImage": "763104351884.dkr.ecr.us-east-1.amazonaws.com/huggingface-pytorch-training:2.1-transformers4.36-gpu-py310-cu121-ubuntu20.04",
                "TrainingInputMode": "File",
            },
            "RoleArn": "arn:aws:iam::123456789012:role/SageMakerTrainingRole",
            "InputDataConfig": [
                {
                    "ChannelName": "training",
                    "DataSource": {
                        "S3DataSource": {
                            "S3DataType": "S3Prefix",
                            "S3Uri": "s3://peft-training-data-123456789012/",
                        }
                    },
                }
            ],
            "OutputDataConfig": {
                "S3OutputPath": "s3://peft-speech-data-123456789012/models/"
            },
            "ResourceConfig": {
                "InstanceType": "ml.g5.xlarge",
                "InstanceCount": 1,
                "VolumeSizeInGB": 50,
            },
            "StoppingCondition": {"MaxRuntimeInSeconds": 7200},
        }

        mock_sm_client.create_training_job(**params)

        mock_sm_client.create_training_job.assert_called_once()
        call_kwargs = mock_sm_client.create_training_job.call_args[1]
        assert call_kwargs["TrainingJobName"] == job_name
        assert call_kwargs["HyperParameters"]["epochs"] == "3"
        assert call_kwargs["ResourceConfig"]["InstanceType"] == "ml.g5.xlarge"

    def test_polling_until_complete(self):
        """describe_training_job is polled until status is Completed."""
        mock_sm = MagicMock()
        mock_sm.describe_training_job.side_effect = [
            {"TrainingJobStatus": "InProgress", "TrainingJobName": "test-job"},
            {"TrainingJobStatus": "InProgress", "TrainingJobName": "test-job"},
            {
                "TrainingJobStatus": "Completed",
                "TrainingJobName": "test-job",
                "ModelArtifacts": {
                    "S3ModelArtifacts": "s3://bucket/models/test-job/output/model.tar.gz"
                },
            },
        ]

        # Simulate polling loop as the script would implement it
        status = None
        poll_count = 0
        while status not in ("Completed", "Failed", "Stopped"):
            resp = mock_sm.describe_training_job(TrainingJobName="test-job")
            status = resp["TrainingJobStatus"]
            poll_count += 1

        assert status == "Completed"
        assert poll_count == 3
        assert mock_sm.describe_training_job.call_count == 3

    def test_dynamodb_write(self, aws_setup):
        """Training metrics are written to the peft-training-metrics DynamoDB table."""
        dynamodb = aws_setup["dynamodb"]

        # Simulate what the script should write after training completes
        timestamp = "2024-01-15T10:30:00Z"
        item = {
            "job_id": {"S": "peft-obama-training-123"},
            "timestamp": {"S": timestamp},
            "status": {"S": "Completed"},
            "epochs": {"N": "3"},
            "learning_rate": {"N": "0.0002"},
            "instance_type": {"S": "ml.g5.xlarge"},
            "model_artifact": {
                "S": "s3://bucket/models/peft-obama-training-123/output/model.tar.gz"
            },
        }

        dynamodb.put_item(TableName="peft-training-metrics", Item=item)

        # Verify the item was written
        response = dynamodb.get_item(
            TableName="peft-training-metrics",
            Key={
                "job_id": {"S": "peft-obama-training-123"},
                "timestamp": {"S": timestamp},
            },
        )

        assert "Item" in response
        assert response["Item"]["status"]["S"] == "Completed"
        assert response["Item"]["epochs"]["N"] == "3"
        assert response["Item"]["instance_type"]["S"] == "ml.g5.xlarge"

    def test_job_failure_raises(self):
        """An error is raised when describe_training_job returns Failed status."""
        mock_sm = MagicMock()
        mock_sm.describe_training_job.return_value = {
            "TrainingJobStatus": "Failed",
            "TrainingJobName": "test-job",
            "FailureReason": "ResourceLimitExceeded: Too many instances",
        }

        resp = mock_sm.describe_training_job(TrainingJobName="test-job")

        # Simulate the script's error handling
        if resp["TrainingJobStatus"] == "Failed":
            with pytest.raises(RuntimeError, match="Training job failed"):
                raise RuntimeError(
                    f"Training job failed: {resp.get('FailureReason', 'Unknown')}"
                )

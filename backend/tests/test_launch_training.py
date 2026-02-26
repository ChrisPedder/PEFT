"""Tests for backend/scripts/launch_training.py — SageMaker training job lifecycle."""

import io
import json
import sys
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.scripts.launch_training import (
    create_training_job,
    main,
    poll_training_job,
    upload_training_code,
    write_metrics,
)


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


class TestUploadTrainingCode:
    def test_upload_training_code(self, aws_setup):
        """upload_training_code packages training dir and uploads to S3."""
        s3 = aws_setup["s3"]
        bucket = "peft-training-data-123456789012"
        key = "code/test-job/sourcedir.tar.gz"

        uri = upload_training_code(s3, bucket, key)

        assert uri == f"s3://{bucket}/{key}"

        # Download and verify the tarball contents
        obj = s3.get_object(Bucket=bucket, Key=key)
        buf = io.BytesIO(obj["Body"].read())
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            names = tar.getnames()
        assert "train.py" in names


class TestCreateTrainingJob:
    def test_calls_sagemaker_with_correct_params(self):
        """create_training_job passes all parameters to SageMaker."""
        mock_sm = MagicMock()

        result = create_training_job(
            sagemaker_client=mock_sm,
            job_name="peft-test-job",
            role_arn="arn:aws:iam::123:role/TrainingRole",
            image_uri="763104351884.dkr.ecr.us-east-1.amazonaws.com/hf-training:latest",
            data_uri="s3://bucket/qa/",
            output_uri="s3://bucket/output/",
            hyperparameters={"epochs": "3", "sagemaker_program": "train.py"},
            instance_type="ml.g5.xlarge",
        )

        assert result == "peft-test-job"
        mock_sm.create_training_job.assert_called_once()
        call_kwargs = mock_sm.create_training_job.call_args[1]
        assert call_kwargs["TrainingJobName"] == "peft-test-job"
        assert call_kwargs["HyperParameters"]["epochs"] == "3"
        assert call_kwargs["HyperParameters"]["sagemaker_program"] == "train.py"
        assert call_kwargs["RoleArn"] == "arn:aws:iam::123:role/TrainingRole"
        assert call_kwargs["ResourceConfig"]["InstanceType"] == "ml.g5.xlarge"
        assert call_kwargs["ResourceConfig"]["VolumeSizeInGB"] == 50
        assert call_kwargs["StoppingCondition"]["MaxRuntimeInSeconds"] == 7200
        assert (
            call_kwargs["InputDataConfig"][0]["DataSource"]["S3DataSource"]["S3Uri"]
            == "s3://bucket/qa/"
        )
        assert call_kwargs["OutputDataConfig"]["S3OutputPath"] == "s3://bucket/output/"


class TestPollTrainingJob:
    def test_polls_until_completed(self):
        """poll_training_job polls until status is Completed and returns response."""
        mock_sm = MagicMock()
        completed_response = {
            "TrainingJobStatus": "Completed",
            "ModelArtifacts": {"S3ModelArtifacts": "s3://bucket/output/model.tar.gz"},
        }
        mock_sm.describe_training_job.side_effect = [
            {"TrainingJobStatus": "InProgress"},
            {"TrainingJobStatus": "InProgress"},
            completed_response,
        ]

        with patch("backend.scripts.launch_training.time.sleep"):
            result = poll_training_job(
                sagemaker_client=mock_sm,
                job_name="test-job",
                poll_interval=1,
            )

        assert result["TrainingJobStatus"] == "Completed"
        assert (
            result["ModelArtifacts"]["S3ModelArtifacts"]
            == "s3://bucket/output/model.tar.gz"
        )
        assert mock_sm.describe_training_job.call_count == 3

    def test_raises_on_failure(self):
        """poll_training_job raises RuntimeError when job fails."""
        mock_sm = MagicMock()
        mock_sm.describe_training_job.return_value = {
            "TrainingJobStatus": "Failed",
            "FailureReason": "ResourceLimitExceeded",
        }

        with pytest.raises(RuntimeError, match="ResourceLimitExceeded"):
            poll_training_job(sagemaker_client=mock_sm, job_name="test-job")

    def test_raises_on_failure_unknown_reason(self):
        """poll_training_job raises RuntimeError with 'Unknown' when no reason given."""
        mock_sm = MagicMock()
        mock_sm.describe_training_job.return_value = {
            "TrainingJobStatus": "Failed",
        }

        with pytest.raises(RuntimeError, match="Unknown"):
            poll_training_job(sagemaker_client=mock_sm, job_name="test-job")

    def test_returns_on_stopped(self):
        """poll_training_job returns normally when job is Stopped."""
        mock_sm = MagicMock()
        mock_sm.describe_training_job.return_value = {
            "TrainingJobStatus": "Stopped",
        }

        result = poll_training_job(sagemaker_client=mock_sm, job_name="test-job")
        assert result["TrainingJobStatus"] == "Stopped"


class TestWriteMetrics:
    def test_writes_basic_metrics(self):
        """write_metrics writes job status and model artifact to DynamoDB."""
        mock_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        job_description = {
            "TrainingJobStatus": "Completed",
            "ModelArtifacts": {
                "S3ModelArtifacts": "s3://bucket/output/model.tar.gz",
            },
        }

        write_metrics(
            dynamodb_resource=mock_dynamodb,
            job_name="peft-test-job",
            job_description=job_description,
        )

        mock_dynamodb.Table.assert_called_once_with("peft-training-metrics")
        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["job_id"] == "peft-test-job"
        assert item["status"] == "Completed"
        assert item["model_artifact"] == "s3://bucket/output/model.tar.gz"
        assert "timestamp" in item

    def test_writes_final_metrics(self):
        """write_metrics extracts and sanitizes FinalMetricDataList entries."""
        mock_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        job_description = {
            "TrainingJobStatus": "Completed",
            "FinalMetricDataList": [
                {"MetricName": "train:loss", "Value": 0.396},
                {"MetricName": "eval/accuracy", "Value": 0.85},
                {"MetricName": "", "Value": 1.0},  # empty name, should be skipped
                {"MetricName": "lr", "Value": None},  # None value, should be skipped
            ],
        }

        write_metrics(
            dynamodb_resource=mock_dynamodb,
            job_name="peft-test-job",
            job_description=job_description,
        )

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["train_loss"] == "0.396"
        assert item["eval_accuracy"] == "0.85"
        assert "" not in item
        assert "lr" not in item

    def test_handles_missing_artifacts(self):
        """write_metrics works when ModelArtifacts is not in the response."""
        mock_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        job_description = {"TrainingJobStatus": "Stopped"}

        write_metrics(
            dynamodb_resource=mock_dynamodb,
            job_name="peft-test-job",
            job_description=job_description,
        )

        item = mock_table.put_item.call_args[1]["Item"]
        assert "model_artifact" not in item
        assert item["status"] == "Stopped"


class TestMain:
    def test_main_orchestrates_full_workflow(self):
        """main() uploads code, creates job, polls, and writes metrics."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}

        mock_sm = MagicMock()
        mock_sm.describe_training_job.return_value = {
            "TrainingJobStatus": "Completed",
            "ModelArtifacts": {
                "S3ModelArtifacts": "s3://peft-model-artifacts-123456789012/output/model.tar.gz",
            },
            "FinalMetricDataList": [
                {"MetricName": "train:loss", "Value": 0.4},
            ],
        }

        mock_s3 = MagicMock()

        mock_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        mock_session = MagicMock()
        mock_session.region_name = "eu-central-1"

        def mock_client(service, **kwargs):
            if service == "sts":
                return mock_sts
            if service == "sagemaker":
                return mock_sm
            if service == "s3":
                return mock_s3
            return MagicMock()

        with (
            patch("sys.argv", ["launch_training.py", "--epochs", "1"]),
            patch(
                "backend.scripts.launch_training.boto3.client",
                side_effect=mock_client,
            ),
            patch(
                "backend.scripts.launch_training.boto3.session.Session",
                return_value=mock_session,
            ),
            patch(
                "backend.scripts.launch_training.boto3.resource",
                return_value=mock_dynamodb,
            ),
            patch("backend.scripts.launch_training.time.sleep"),
            patch(
                "backend.scripts.launch_training.upload_training_code",
                return_value="s3://bucket/code/sourcedir.tar.gz",
            ),
        ):
            main()

        # Verify training job was created
        mock_sm.create_training_job.assert_called_once()
        call_kwargs = mock_sm.create_training_job.call_args[1]
        assert call_kwargs["HyperParameters"]["epochs"] == "1"
        assert call_kwargs["HyperParameters"]["sagemaker_program"] == "train.py"

        # Verify metrics were written
        mock_table.put_item.assert_called_once()

    def test_main_unsupported_region(self):
        """main() raises ValueError for unsupported region."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}

        mock_session = MagicMock()
        mock_session.region_name = "ap-northeast-1"

        with (
            patch("sys.argv", ["launch_training.py"]),
            patch(
                "backend.scripts.launch_training.boto3.client",
                return_value=mock_sts,
            ),
            patch(
                "backend.scripts.launch_training.boto3.session.Session",
                return_value=mock_session,
            ),
            pytest.raises(ValueError, match="No HuggingFace training image"),
        ):
            main()

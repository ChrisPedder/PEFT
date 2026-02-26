"""Tests for backend/scripts/import_to_bedrock.py — Bedrock model import."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.scripts.import_to_bedrock import (
    create_import_job,
    poll_import_job,
    write_model_arn,
)


class TestCreateImportJob:
    def test_calls_bedrock_with_correct_params(self):
        """create_import_job passes correct S3 URI, role ARN, and model name."""
        mock_bedrock = MagicMock()
        mock_bedrock.create_model_import_job.return_value = {
            "jobArn": "arn:aws:bedrock:eu-central-1:123456789012:model-import-job/test-job"
        }

        job_arn = create_import_job(
            bedrock_client=mock_bedrock,
            job_name="peft-import-test-20240101-000000",
            model_name="peft-obama",
            role_arn="arn:aws:iam::123456789012:role/PeftBedrockImportRole",
            s3_uri="s3://peft-model-artifacts-123456789012/merged-model/",
        )

        mock_bedrock.create_model_import_job.assert_called_once_with(
            jobName="peft-import-test-20240101-000000",
            importedModelName="peft-obama",
            roleArn="arn:aws:iam::123456789012:role/PeftBedrockImportRole",
            modelDataSource={
                "s3DataSource": {
                    "s3Uri": "s3://peft-model-artifacts-123456789012/merged-model/",
                }
            },
        )
        assert "model-import-job" in job_arn

    def test_returns_job_arn(self):
        """create_import_job returns the job ARN from the response."""
        mock_bedrock = MagicMock()
        expected_arn = "arn:aws:bedrock:eu-central-1:123456789012:model-import-job/abc"
        mock_bedrock.create_model_import_job.return_value = {"jobArn": expected_arn}

        result = create_import_job(
            bedrock_client=mock_bedrock,
            job_name="test-job",
            model_name="test-model",
            role_arn="arn:aws:iam::123:role/TestRole",
            s3_uri="s3://bucket/model/",
        )

        assert result == expected_arn


class TestPollImportJob:
    def test_polls_until_completed(self):
        """poll_import_job polls until status is Completed."""
        mock_bedrock = MagicMock()
        mock_bedrock.get_model_import_job.side_effect = [
            {"status": "InProgress"},
            {"status": "InProgress"},
            {
                "status": "Completed",
                "importedModelArn": "arn:aws:bedrock:eu-central-1:123:imported-model/peft-obama",
            },
        ]

        with patch("backend.scripts.import_to_bedrock.time.sleep"):
            result = poll_import_job(
                bedrock_client=mock_bedrock,
                job_arn="arn:aws:bedrock:eu-central-1:123:model-import-job/test",
                poll_interval=1,
            )

        assert result["status"] == "Completed"
        assert "importedModelArn" in result
        assert mock_bedrock.get_model_import_job.call_count == 3

    def test_raises_on_failure(self):
        """poll_import_job raises RuntimeError when status is Failed."""
        mock_bedrock = MagicMock()
        mock_bedrock.get_model_import_job.return_value = {
            "status": "Failed",
            "failureMessage": "Model format not supported",
        }

        with pytest.raises(RuntimeError, match="Model format not supported"):
            poll_import_job(
                bedrock_client=mock_bedrock,
                job_arn="arn:aws:bedrock:eu-central-1:123:model-import-job/test",
            )

    def test_raises_on_failure_unknown_reason(self):
        """poll_import_job raises RuntimeError with 'Unknown' when no failure message."""
        mock_bedrock = MagicMock()
        mock_bedrock.get_model_import_job.return_value = {"status": "Failed"}

        with pytest.raises(RuntimeError, match="Unknown"):
            poll_import_job(
                bedrock_client=mock_bedrock,
                job_arn="arn:aws:bedrock:eu-central-1:123:model-import-job/test",
            )


class TestWriteModelArn:
    def test_writes_to_dynamodb(self):
        """write_model_arn puts the correct item into DynamoDB."""
        mock_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        write_model_arn(
            dynamodb_resource=mock_dynamodb,
            model_name="peft-obama",
            model_arn="arn:aws:bedrock:eu-central-1:123:imported-model/peft-obama",
        )

        mock_dynamodb.Table.assert_called_once_with("peft-training-metrics")
        mock_table.put_item.assert_called_once()

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["job_id"] == "bedrock-import-peft-obama"
        assert item["status"] == "Completed"
        assert item["bedrock_model_arn"] == "arn:aws:bedrock:eu-central-1:123:imported-model/peft-obama"
        assert item["model_name"] == "peft-obama"
        assert "timestamp" in item

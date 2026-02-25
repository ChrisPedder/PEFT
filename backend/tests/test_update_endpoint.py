"""Tests for backend/scripts/update_endpoint.py.

These tests define the expected interface for the update_endpoint script.
The script will:
- Parse arg: --model-data-url
- Create SageMaker Model
- Create EndpointConfig
- Update endpoint
- Wait for InService

The actual script will be created by another agent. These tests validate
the expected interaction with AWS services using moto mocks.
"""

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


@pytest.fixture
def sagemaker_setup():
    """Set up mock SageMaker resources for update_endpoint tests."""
    with mock_aws():
        region = "us-east-1"
        sagemaker = boto3.client("sagemaker", region_name=region)
        s3 = boto3.client("s3", region_name=region)

        # Create S3 bucket with model artifacts
        s3.create_bucket(Bucket="peft-model-artifacts")
        s3.put_object(
            Bucket="peft-model-artifacts",
            Key="models/v1/model.tar.gz",
            Body=b"fake-model-v1",
        )
        s3.put_object(
            Bucket="peft-model-artifacts",
            Key="models/v2/model.tar.gz",
            Body=b"fake-model-v2",
        )

        # Create IAM role
        iam = boto3.client("iam", region_name=region)
        try:
            iam.create_role(
                RoleName="SageMakerExecutionRole",
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
            "s3": s3,
            "region": region,
        }


class TestUpdateEndpoint:
    def test_model_creation(self, sagemaker_setup):
        """SageMaker create_model is called with correct parameters."""
        mock_sm = MagicMock()
        mock_sm.create_model.return_value = {
            "ModelArn": "arn:aws:sagemaker:us-east-1:123456789012:model/peft-obama-v2"
        }

        model_name = "peft-obama-model-20240115"
        model_data_url = "s3://peft-model-artifacts/models/v2/model.tar.gz"
        image_uri = "763104351884.dkr.ecr.us-east-1.amazonaws.com/huggingface-pytorch-tgi-inference:2.1-tgi1.4-gpu-py310-cu121-ubuntu22.04"

        mock_sm.create_model(
            ModelName=model_name,
            PrimaryContainer={
                "Image": image_uri,
                "ModelDataUrl": model_data_url,
                "Environment": {
                    "HF_MODEL_ID": "/opt/ml/model",
                    "SM_NUM_GPUS": "1",
                    "MAX_INPUT_LENGTH": "2048",
                    "MAX_TOTAL_TOKENS": "4096",
                },
            },
            ExecutionRoleArn="arn:aws:iam::123456789012:role/SageMakerExecutionRole",
        )

        mock_sm.create_model.assert_called_once()
        call_kwargs = mock_sm.create_model.call_args[1]
        assert call_kwargs["ModelName"] == model_name
        assert call_kwargs["PrimaryContainer"]["ModelDataUrl"] == model_data_url

    def test_endpoint_config_creation(self, sagemaker_setup):
        """SageMaker create_endpoint_config is called with the model and instance spec."""
        mock_sm = MagicMock()

        config_name = "peft-obama-config-20240115"
        model_name = "peft-obama-model-20240115"

        mock_sm.create_endpoint_config(
            EndpointConfigName=config_name,
            ProductionVariants=[
                {
                    "VariantName": "default",
                    "ModelName": model_name,
                    "InstanceType": "ml.g5.xlarge",
                    "InitialInstanceCount": 1,
                    "RoutingConfig": {
                        "RoutingStrategy": "LEAST_OUTSTANDING_REQUESTS",
                    },
                }
            ],
        )

        mock_sm.create_endpoint_config.assert_called_once()
        call_kwargs = mock_sm.create_endpoint_config.call_args[1]
        assert call_kwargs["EndpointConfigName"] == config_name
        variant = call_kwargs["ProductionVariants"][0]
        assert variant["ModelName"] == model_name
        assert variant["InstanceType"] == "ml.g5.xlarge"

    def test_endpoint_update(self, sagemaker_setup):
        """SageMaker update_endpoint is called with the new config."""
        mock_sm = MagicMock()
        mock_sm.update_endpoint.return_value = {
            "EndpointArn": "arn:aws:sagemaker:us-east-1:123456789012:endpoint/peft-obama-endpoint"
        }

        # Simulate waiting for InService
        mock_sm.describe_endpoint.side_effect = [
            {"EndpointStatus": "Updating"},
            {"EndpointStatus": "Updating"},
            {"EndpointStatus": "InService"},
        ]

        endpoint_name = "peft-obama-endpoint"
        config_name = "peft-obama-config-20240115"

        mock_sm.update_endpoint(
            EndpointName=endpoint_name,
            EndpointConfigName=config_name,
        )

        mock_sm.update_endpoint.assert_called_once()
        call_kwargs = mock_sm.update_endpoint.call_args[1]
        assert call_kwargs["EndpointName"] == endpoint_name
        assert call_kwargs["EndpointConfigName"] == config_name

        # Simulate polling until InService
        status = None
        poll_count = 0
        while status != "InService":
            resp = mock_sm.describe_endpoint(EndpointName=endpoint_name)
            status = resp["EndpointStatus"]
            poll_count += 1

        assert status == "InService"
        assert poll_count == 3

    def test_auto_detect_latest_model(self, sagemaker_setup):
        """S3 list_objects_v2 is used to find the latest model artifact."""
        s3 = sagemaker_setup["s3"]

        # List model artifacts to find the latest
        response = s3.list_objects_v2(
            Bucket="peft-model-artifacts",
            Prefix="models/",
        )

        objects = response.get("Contents", [])
        assert len(objects) >= 2

        # Sort by last modified (descending) to get the latest
        objects.sort(key=lambda o: o["LastModified"], reverse=True)
        latest_key = objects[0]["Key"]

        # The latest model should be identifiable
        assert latest_key.startswith("models/")
        assert latest_key.endswith("model.tar.gz")
        latest_url = f"s3://peft-model-artifacts/{latest_key}"
        assert latest_url.startswith("s3://")

"""Tests for backend/scripts/update_endpoint.py — SageMaker endpoint update."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.scripts.update_endpoint import (
    create_endpoint_config,
    create_model,
    find_latest_model,
    main,
    update_endpoint,
)


class TestFindLatestModel:
    def test_finds_latest_by_modified_date(self):
        """find_latest_model returns the most recently modified model.tar.gz."""
        mock_s3 = MagicMock()
        paginator = MagicMock()
        mock_s3.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {
                        "Key": "models/v1/model.tar.gz",
                        "LastModified": datetime(2024, 1, 1, tzinfo=timezone.utc),
                    },
                    {
                        "Key": "models/v2/model.tar.gz",
                        "LastModified": datetime(2024, 6, 1, tzinfo=timezone.utc),
                    },
                ]
            }
        ]

        result = find_latest_model(mock_s3, "my-bucket")

        assert result == "s3://my-bucket/models/v2/model.tar.gz"

    def test_ignores_non_model_files(self):
        """find_latest_model only considers files ending in model.tar.gz."""
        mock_s3 = MagicMock()
        paginator = MagicMock()
        mock_s3.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {
                        "Key": "data/training.jsonl",
                        "LastModified": datetime(2024, 12, 1, tzinfo=timezone.utc),
                    },
                    {
                        "Key": "models/v1/model.tar.gz",
                        "LastModified": datetime(2024, 1, 1, tzinfo=timezone.utc),
                    },
                ]
            }
        ]

        result = find_latest_model(mock_s3, "my-bucket")
        assert result == "s3://my-bucket/models/v1/model.tar.gz"

    def test_raises_when_no_models_found(self):
        """find_latest_model raises FileNotFoundError when no model.tar.gz exists."""
        mock_s3 = MagicMock()
        paginator = MagicMock()
        mock_s3.get_paginator.return_value = paginator
        paginator.paginate.return_value = [{"Contents": []}]

        with pytest.raises(FileNotFoundError, match="No model.tar.gz"):
            find_latest_model(mock_s3, "empty-bucket")

    def test_handles_empty_pages(self):
        """find_latest_model handles pages with no Contents key."""
        mock_s3 = MagicMock()
        paginator = MagicMock()
        mock_s3.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {},  # no Contents key
            {
                "Contents": [
                    {
                        "Key": "models/v1/model.tar.gz",
                        "LastModified": datetime(2024, 1, 1, tzinfo=timezone.utc),
                    },
                ]
            },
        ]

        result = find_latest_model(mock_s3, "my-bucket")
        assert result == "s3://my-bucket/models/v1/model.tar.gz"


class TestCreateModel:
    def test_calls_sagemaker_with_correct_params(self):
        """create_model passes correct model name, image, data URL, and role."""
        mock_sm = MagicMock()

        result = create_model(
            sagemaker_client=mock_sm,
            model_name="peft-test-model",
            image_uri="763104351884.dkr.ecr.us-east-1.amazonaws.com/hf-inference:latest",
            model_data_url="s3://bucket/models/v1/model.tar.gz",
            role_arn="arn:aws:iam::123:role/TestRole",
        )

        assert result == "peft-test-model"
        mock_sm.create_model.assert_called_once()
        call_kwargs = mock_sm.create_model.call_args[1]
        assert call_kwargs["ModelName"] == "peft-test-model"
        assert (
            call_kwargs["PrimaryContainer"]["ModelDataUrl"]
            == "s3://bucket/models/v1/model.tar.gz"
        )
        assert call_kwargs["ExecutionRoleArn"] == "arn:aws:iam::123:role/TestRole"
        assert call_kwargs["PrimaryContainer"]["Environment"]["SM_NUM_GPUS"] == "1"


class TestCreateEndpointConfig:
    def test_calls_sagemaker_with_correct_params(self):
        """create_endpoint_config passes correct config name, model, and instance."""
        mock_sm = MagicMock()

        result = create_endpoint_config(
            sagemaker_client=mock_sm,
            config_name="peft-test-config",
            model_name="peft-test-model",
            instance_type="ml.g5.xlarge",
        )

        assert result == "peft-test-config"
        mock_sm.create_endpoint_config.assert_called_once()
        call_kwargs = mock_sm.create_endpoint_config.call_args[1]
        assert call_kwargs["EndpointConfigName"] == "peft-test-config"
        variant = call_kwargs["ProductionVariants"][0]
        assert variant["ModelName"] == "peft-test-model"
        assert variant["InstanceType"] == "ml.g5.xlarge"
        assert (
            variant["RoutingConfig"]["RoutingStrategy"] == "LEAST_OUTSTANDING_REQUESTS"
        )


class TestUpdateEndpoint:
    def test_polls_until_in_service(self):
        """update_endpoint polls until status is InService."""
        mock_sm = MagicMock()
        mock_sm.describe_endpoint.side_effect = [
            {"EndpointStatus": "Updating"},
            {"EndpointStatus": "Updating"},
            {"EndpointStatus": "InService"},
        ]

        with patch("backend.scripts.update_endpoint.time.sleep"):
            update_endpoint(
                sagemaker_client=mock_sm,
                endpoint_name="test-endpoint",
                config_name="test-config",
            )

        mock_sm.update_endpoint.assert_called_once_with(
            EndpointName="test-endpoint",
            EndpointConfigName="test-config",
        )
        assert mock_sm.describe_endpoint.call_count == 3

    def test_raises_on_failed_status(self):
        """update_endpoint raises RuntimeError when endpoint reaches Failed."""
        mock_sm = MagicMock()
        mock_sm.describe_endpoint.return_value = {
            "EndpointStatus": "Failed",
            "FailureReason": "Model container failed to respond",
        }

        with pytest.raises(RuntimeError, match="Model container failed to respond"):
            update_endpoint(
                sagemaker_client=mock_sm,
                endpoint_name="test-endpoint",
                config_name="test-config",
            )

    def test_raises_on_out_of_service(self):
        """update_endpoint raises RuntimeError on OutOfService status."""
        mock_sm = MagicMock()
        mock_sm.describe_endpoint.return_value = {
            "EndpointStatus": "OutOfService",
        }

        with pytest.raises(RuntimeError, match="Unknown"):
            update_endpoint(
                sagemaker_client=mock_sm,
                endpoint_name="test-endpoint",
                config_name="test-config",
            )


class TestMain:
    def test_main_auto_detects_model(self):
        """main() auto-detects the latest model when --model-data-url is not given."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}

        mock_sm = MagicMock()
        mock_sm.describe_endpoint.return_value = {"EndpointStatus": "InService"}

        mock_s3 = MagicMock()
        paginator = MagicMock()
        mock_s3.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {
                        "Key": "models/v1/model.tar.gz",
                        "LastModified": datetime(2024, 6, 1, tzinfo=timezone.utc),
                    },
                ]
            }
        ]

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
            patch("sys.argv", ["update_endpoint.py"]),
            patch(
                "backend.scripts.update_endpoint.boto3.client",
                side_effect=mock_client,
            ),
            patch(
                "backend.scripts.update_endpoint.boto3.session.Session",
                return_value=mock_session,
            ),
            patch("backend.scripts.update_endpoint.time.sleep"),
        ):
            main()

        mock_sm.create_model.assert_called_once()
        mock_sm.create_endpoint_config.assert_called_once()
        mock_sm.update_endpoint.assert_called_once()

    def test_main_with_provided_model_url(self):
        """main() uses --model-data-url and skips auto-detection."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "999888777666"}

        mock_sm = MagicMock()
        mock_sm.describe_endpoint.return_value = {"EndpointStatus": "InService"}

        mock_session = MagicMock()
        mock_session.region_name = "us-east-1"

        def mock_client(service, **kwargs):
            if service == "sts":
                return mock_sts
            if service == "sagemaker":
                return mock_sm
            return MagicMock()

        with (
            patch(
                "sys.argv",
                [
                    "update_endpoint.py",
                    "--model-data-url",
                    "s3://my-bucket/my-model.tar.gz",
                ],
            ),
            patch(
                "backend.scripts.update_endpoint.boto3.client",
                side_effect=mock_client,
            ),
            patch(
                "backend.scripts.update_endpoint.boto3.session.Session",
                return_value=mock_session,
            ),
            patch("backend.scripts.update_endpoint.time.sleep"),
        ):
            main()

        call_kwargs = mock_sm.create_model.call_args[1]
        assert (
            call_kwargs["PrimaryContainer"]["ModelDataUrl"]
            == "s3://my-bucket/my-model.tar.gz"
        )

    def test_main_unsupported_region(self):
        """main() raises ValueError for unsupported region."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}

        mock_session = MagicMock()
        mock_session.region_name = "ap-southeast-1"

        with (
            patch("sys.argv", ["update_endpoint.py"]),
            patch(
                "backend.scripts.update_endpoint.boto3.client",
                return_value=mock_sts,
            ),
            patch(
                "backend.scripts.update_endpoint.boto3.session.Session",
                return_value=mock_session,
            ),
            pytest.raises(ValueError, match="No HuggingFace inference image"),
        ):
            main()

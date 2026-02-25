"""
Update the SageMaker endpoint with a new model version.

This script:
- Auto-detects the latest model artifact from S3 (or uses a provided URL)
- Creates a new SageMaker Model resource
- Creates a new EndpointConfig
- Updates the endpoint to use the new config
- Waits for the endpoint to reach InService status

Usage:
    python update_endpoint.py
    python update_endpoint.py --model-data-url s3://bucket/path/to/model.tar.gz
"""

import argparse
import time
from datetime import datetime, timezone

import boto3


# ---------------------------------------------------------------------------
# HuggingFace inference container images by region
# ---------------------------------------------------------------------------

HF_INFERENCE_IMAGES = {
    "us-east-1": "763104351884.dkr.ecr.us-east-1.amazonaws.com/huggingface-pytorch-inference:2.1.0-transformers4.37.0-gpu-py310-cu118-ubuntu20.04",
    "us-west-2": "763104351884.dkr.ecr.us-west-2.amazonaws.com/huggingface-pytorch-inference:2.1.0-transformers4.37.0-gpu-py310-cu118-ubuntu20.04",
    "eu-west-1": "763104351884.dkr.ecr.eu-west-1.amazonaws.com/huggingface-pytorch-inference:2.1.0-transformers4.37.0-gpu-py310-cu118-ubuntu20.04",
    "eu-central-1": "763104351884.dkr.ecr.eu-central-1.amazonaws.com/huggingface-pytorch-inference:2.1.0-transformers4.37.0-gpu-py310-cu118-ubuntu20.04",
}

ENDPOINT_NAME = "peft-obama-endpoint"
INSTANCE_TYPE = "ml.g5.xlarge"


def find_latest_model(s3_client, bucket: str) -> str:
    """Find the latest model.tar.gz artifact in an S3 bucket.

    Lists all objects in the bucket, filters for model.tar.gz files,
    and returns the S3 URI of the most recently modified one.

    Args:
        s3_client: Boto3 S3 client.
        bucket: Name of the S3 bucket to search.

    Returns:
        The full S3 URI of the latest model.tar.gz (e.g., s3://bucket/path/model.tar.gz).

    Raises:
        FileNotFoundError: If no model.tar.gz files are found in the bucket.
    """
    paginator = s3_client.get_paginator("list_objects_v2")
    model_objects = []

    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith("model.tar.gz"):
                model_objects.append(obj)

    if not model_objects:
        raise FileNotFoundError(
            f"No model.tar.gz files found in s3://{bucket}/"
        )

    # Sort by LastModified descending to find the most recent
    model_objects.sort(key=lambda o: o["LastModified"], reverse=True)
    latest_key = model_objects[0]["Key"]
    latest_uri = f"s3://{bucket}/{latest_key}"

    print(f"Found {len(model_objects)} model artifact(s). Latest: {latest_uri}")
    return latest_uri


def create_model(
    sagemaker_client,
    model_name: str,
    image_uri: str,
    model_data_url: str,
    role_arn: str,
) -> str:
    """Create a SageMaker Model resource.

    Args:
        sagemaker_client: Boto3 SageMaker client.
        model_name: Name for the SageMaker Model.
        image_uri: URI of the HuggingFace inference container image.
        model_data_url: S3 URI of the model.tar.gz artifact.
        role_arn: IAM execution role ARN for SageMaker.

    Returns:
        The model name.
    """
    sagemaker_client.create_model(
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
        ExecutionRoleArn=role_arn,
    )

    print(f"SageMaker Model '{model_name}' created.")
    return model_name


def create_endpoint_config(
    sagemaker_client,
    config_name: str,
    model_name: str,
    instance_type: str,
) -> str:
    """Create a SageMaker EndpointConfig.

    Args:
        sagemaker_client: Boto3 SageMaker client.
        config_name: Name for the EndpointConfig.
        model_name: Name of the SageMaker Model to use.
        instance_type: EC2 instance type for the endpoint.

    Returns:
        The endpoint config name.
    """
    sagemaker_client.create_endpoint_config(
        EndpointConfigName=config_name,
        ProductionVariants=[
            {
                "VariantName": "AllTraffic",
                "ModelName": model_name,
                "InstanceType": instance_type,
                "InitialInstanceCount": 1,
            }
        ],
    )

    print(f"EndpointConfig '{config_name}' created.")
    return config_name


def update_endpoint(
    sagemaker_client,
    endpoint_name: str,
    config_name: str,
    poll_interval: int = 30,
) -> None:
    """Update the SageMaker endpoint and wait for it to reach InService status.

    Args:
        sagemaker_client: Boto3 SageMaker client.
        endpoint_name: Name of the endpoint to update.
        config_name: Name of the new EndpointConfig.
        poll_interval: Seconds between status polls (default 30).

    Raises:
        RuntimeError: If the endpoint reaches a failed state.
    """
    sagemaker_client.update_endpoint(
        EndpointName=endpoint_name,
        EndpointConfigName=config_name,
    )
    print(f"Endpoint '{endpoint_name}' update initiated with config '{config_name}'.")

    # Poll until InService
    terminal_states = {"InService", "Failed", "OutOfService"}

    while True:
        response = sagemaker_client.describe_endpoint(
            EndpointName=endpoint_name
        )
        status = response["EndpointStatus"]
        print(f"Endpoint '{endpoint_name}' status: {status}")

        if status in terminal_states:
            if status != "InService":
                failure_reason = response.get("FailureReason", "Unknown")
                raise RuntimeError(
                    f"Endpoint update failed with status '{status}': {failure_reason}"
                )
            print(f"Endpoint '{endpoint_name}' is now InService.")
            return

        time.sleep(poll_interval)


def main() -> None:
    """Orchestrate the endpoint update: find model, create resources, and update."""
    parser = argparse.ArgumentParser(
        description="Update the SageMaker PEFT endpoint with a new model version."
    )
    parser.add_argument(
        "--model-data-url",
        type=str,
        default=None,
        help="S3 URI of model.tar.gz. If not provided, auto-detects the latest model.",
    )
    args = parser.parse_args()

    # Auto-detect AWS account ID and region
    sts = boto3.client("sts")
    account_id = sts.get_caller_identity()["Account"]
    region = boto3.session.Session().region_name or "us-east-1"

    print(f"AWS Account: {account_id}")
    print(f"Region: {region}")

    # Resolve container image
    image_uri = HF_INFERENCE_IMAGES.get(region)
    if not image_uri:
        raise ValueError(
            f"No HuggingFace inference image configured for region '{region}'. "
            f"Supported regions: {list(HF_INFERENCE_IMAGES.keys())}"
        )

    # Build resource identifiers
    role_arn = f"arn:aws:iam::{account_id}:role/PeftSageMakerExecutionRole"
    model_bucket = f"peft-model-artifacts-{account_id}"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    model_name = f"peft-obama-model-{timestamp}"
    config_name = f"peft-obama-config-{timestamp}"

    # Create AWS clients
    sagemaker_client = boto3.client("sagemaker", region_name=region)
    s3_client = boto3.client("s3", region_name=region)

    # Step 1: Resolve model data URL
    model_data_url = args.model_data_url
    if not model_data_url:
        print(f"\nAuto-detecting latest model in s3://{model_bucket}/...")
        model_data_url = find_latest_model(s3_client, model_bucket)
    else:
        print(f"\nUsing provided model: {model_data_url}")

    # Step 2: Create SageMaker Model
    print(f"\nCreating SageMaker Model '{model_name}'...")
    create_model(
        sagemaker_client=sagemaker_client,
        model_name=model_name,
        image_uri=image_uri,
        model_data_url=model_data_url,
        role_arn=role_arn,
    )

    # Step 3: Create EndpointConfig
    print(f"\nCreating EndpointConfig '{config_name}'...")
    create_endpoint_config(
        sagemaker_client=sagemaker_client,
        config_name=config_name,
        model_name=model_name,
        instance_type=INSTANCE_TYPE,
    )

    # Step 4: Update the endpoint
    print(f"\nUpdating endpoint '{ENDPOINT_NAME}'...")
    update_endpoint(
        sagemaker_client=sagemaker_client,
        endpoint_name=ENDPOINT_NAME,
        config_name=config_name,
        poll_interval=30,
    )

    print(f"\nEndpoint update complete.")
    print(f"  Endpoint: {ENDPOINT_NAME}")
    print(f"  Model: {model_name}")
    print(f"  Config: {config_name}")
    print(f"  Model artifact: {model_data_url}")


if __name__ == "__main__":
    main()

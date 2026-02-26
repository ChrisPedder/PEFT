"""
Launch a SageMaker training job for PEFT fine-tuning and write metrics to DynamoDB.

This script:
- Creates a SageMaker training job using the HuggingFace training container
- Polls the job until it completes or fails
- Writes final training metrics to the peft-training-metrics DynamoDB table

Usage:
    python launch_training.py --epochs 3 --batch-size 4 --learning-rate 2e-4
"""

import argparse
import time
from datetime import datetime, timezone

import boto3

# ---------------------------------------------------------------------------
# HuggingFace training container images by region
# ---------------------------------------------------------------------------

HF_TRAINING_IMAGES = {
    "us-east-1": "763104351884.dkr.ecr.us-east-1.amazonaws.com/huggingface-pytorch-training:2.1.0-transformers4.36.0-gpu-py310-cu121-ubuntu20.04",
    "us-west-2": "763104351884.dkr.ecr.us-west-2.amazonaws.com/huggingface-pytorch-training:2.1.0-transformers4.36.0-gpu-py310-cu121-ubuntu20.04",
    "eu-west-1": "763104351884.dkr.ecr.eu-west-1.amazonaws.com/huggingface-pytorch-training:2.1.0-transformers4.36.0-gpu-py310-cu121-ubuntu20.04",
    "eu-central-1": "763104351884.dkr.ecr.eu-central-1.amazonaws.com/huggingface-pytorch-training:2.1.0-transformers4.36.0-gpu-py310-cu121-ubuntu20.04",
}

DYNAMODB_TABLE = "peft-training-metrics"
ENDPOINT_NAME = "peft-obama-endpoint"


def create_training_job(
    sagemaker_client,
    job_name: str,
    role_arn: str,
    image_uri: str,
    data_uri: str,
    output_uri: str,
    hyperparameters: dict,
    instance_type: str,
) -> str:
    """Create a SageMaker training job.

    Args:
        sagemaker_client: Boto3 SageMaker client.
        job_name: Name for the training job.
        role_arn: IAM role ARN for SageMaker to assume.
        image_uri: URI of the HuggingFace training container image.
        data_uri: S3 URI for the training data input channel.
        output_uri: S3 URI for model output artifacts.
        hyperparameters: Dict of hyperparameters (all values must be strings).
        instance_type: EC2 instance type for training.

    Returns:
        The training job name.
    """
    sagemaker_client.create_training_job(
        TrainingJobName=job_name,
        HyperParameters=hyperparameters,
        AlgorithmSpecification={
            "TrainingImage": image_uri,
            "TrainingInputMode": "File",
        },
        RoleArn=role_arn,
        InputDataConfig=[
            {
                "ChannelName": "training",
                "DataSource": {
                    "S3DataSource": {
                        "S3DataType": "S3Prefix",
                        "S3Uri": data_uri,
                    }
                },
            }
        ],
        OutputDataConfig={
            "S3OutputPath": output_uri,
        },
        ResourceConfig={
            "InstanceType": instance_type,
            "InstanceCount": 1,
            "VolumeSizeInGB": 50,
        },
        StoppingCondition={"MaxRuntimeInSeconds": 7200},
    )

    print(f"Training job '{job_name}' created successfully.")
    return job_name


def poll_training_job(
    sagemaker_client,
    job_name: str,
    poll_interval: int = 60,
) -> dict:
    """Poll a SageMaker training job until it reaches a terminal state.

    Args:
        sagemaker_client: Boto3 SageMaker client.
        job_name: Name of the training job to monitor.
        poll_interval: Seconds between each poll (default 60).

    Returns:
        The final describe_training_job response dict.

    Raises:
        RuntimeError: If the training job fails.
    """
    terminal_states = {"Completed", "Failed", "Stopped"}

    while True:
        response = sagemaker_client.describe_training_job(TrainingJobName=job_name)
        status = response["TrainingJobStatus"]
        print(f"Training job '{job_name}' status: {status}")

        if status in terminal_states:
            if status == "Failed":
                reason = response.get("FailureReason", "Unknown")
                raise RuntimeError(f"Training job failed: {reason}")
            return response

        time.sleep(poll_interval)


def write_metrics(
    dynamodb_resource,
    job_name: str,
    job_description: dict,
) -> None:
    """Write training metrics from a completed job to DynamoDB.

    Args:
        dynamodb_resource: Boto3 DynamoDB resource (not client).
        job_name: The training job name (used as partition key).
        job_description: The describe_training_job response dict.
    """
    table = dynamodb_resource.Table(DYNAMODB_TABLE)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    item = {
        "job_id": job_name,
        "timestamp": timestamp,
        "status": job_description.get("TrainingJobStatus", "Unknown"),
    }

    # Extract model artifact location if available
    model_artifacts = job_description.get("ModelArtifacts", {})
    if "S3ModelArtifacts" in model_artifacts:
        item["model_artifact"] = model_artifacts["S3ModelArtifacts"]

    # Extract final metrics from FinalMetricDataList
    final_metrics = job_description.get("FinalMetricDataList", [])
    for metric in final_metrics:
        metric_name = metric.get("MetricName", "")
        metric_value = metric.get("Value")
        if metric_name and metric_value is not None:
            # Sanitize metric name for DynamoDB attribute name
            safe_name = metric_name.replace(":", "_").replace("/", "_")
            item[safe_name] = str(metric_value)

    table.put_item(Item=item)
    print(f"Metrics written to DynamoDB table '{DYNAMODB_TABLE}' for job '{job_name}'.")


def main() -> None:
    """Orchestrate the training job lifecycle: create, poll, and record metrics."""
    parser = argparse.ArgumentParser(
        description="Launch a SageMaker PEFT training job and write metrics to DynamoDB."
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        help="Number of training epochs (default: 3)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=4,
        help="Per-device training batch size (default: 4)",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=2e-4,
        help="Learning rate (default: 2e-4)",
    )
    parser.add_argument(
        "--instance-type",
        type=str,
        default="ml.g5.xlarge",
        help="SageMaker instance type (default: ml.g5.xlarge)",
    )
    args = parser.parse_args()

    # Auto-detect AWS account ID and region
    sts = boto3.client("sts")
    account_id = sts.get_caller_identity()["Account"]
    region = boto3.session.Session().region_name or "us-east-1"

    print(f"AWS Account: {account_id}")
    print(f"Region: {region}")

    # Resolve container image
    image_uri = HF_TRAINING_IMAGES.get(region)
    if not image_uri:
        raise ValueError(
            f"No HuggingFace training image configured for region '{region}'. "
            f"Supported regions: {list(HF_TRAINING_IMAGES.keys())}"
        )

    # Build resource identifiers
    role_arn = f"arn:aws:iam::{account_id}:role/PeftTrainingRole"
    data_uri = f"s3://peft-training-data-{account_id}/qa/"
    output_uri = f"s3://peft-model-artifacts-{account_id}/"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    job_name = f"peft-obama-{timestamp}"

    hyperparameters = {
        "epochs": str(args.epochs),
        "per_device_train_batch_size": str(args.batch_size),
        "learning_rate": str(args.learning_rate),
    }

    print(f"Job name: {job_name}")
    print(f"Hyperparameters: {hyperparameters}")
    print(f"Instance type: {args.instance_type}")

    # Create AWS clients
    sagemaker_client = boto3.client("sagemaker", region_name=region)
    dynamodb_resource = boto3.resource("dynamodb", region_name=region)

    # Step 1: Create the training job
    create_training_job(
        sagemaker_client=sagemaker_client,
        job_name=job_name,
        role_arn=role_arn,
        image_uri=image_uri,
        data_uri=data_uri,
        output_uri=output_uri,
        hyperparameters=hyperparameters,
        instance_type=args.instance_type,
    )

    # Step 2: Poll until complete
    print("\nPolling training job status (every 60 seconds)...")
    job_description = poll_training_job(
        sagemaker_client=sagemaker_client,
        job_name=job_name,
        poll_interval=60,
    )

    # Step 3: Write metrics to DynamoDB
    print("\nWriting metrics to DynamoDB...")
    write_metrics(
        dynamodb_resource=dynamodb_resource,
        job_name=job_name,
        job_description=job_description,
    )

    print(f"\nTraining job '{job_name}' completed successfully.")

    # Print model artifact location
    model_artifacts = job_description.get("ModelArtifacts", {})
    if "S3ModelArtifacts" in model_artifacts:
        print(f"Model artifacts: {model_artifacts['S3ModelArtifacts']}")


if __name__ == "__main__":
    main()

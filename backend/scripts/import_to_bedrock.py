"""
Import a merged PEFT model from S3 into Amazon Bedrock via Custom Model Import.

This script:
- Auto-detects the AWS account ID and region
- Creates a Bedrock model import job pointing at the merged model in S3
- Polls until the import completes or fails
- Writes the imported model ARN to the peft-training-metrics DynamoDB table

Usage:
    python import_to_bedrock.py --model-name peft-obama [--role-arn arn:aws:iam::...]
"""

import argparse
import time
from datetime import datetime, timezone

import boto3

DYNAMODB_TABLE = "peft-training-metrics"


def create_import_job(
    bedrock_client,
    job_name: str,
    model_name: str,
    role_arn: str,
    s3_uri: str,
) -> str:
    """Create a Bedrock model import job.

    Returns:
        The job ARN.
    """
    response = bedrock_client.create_model_import_job(
        jobName=job_name,
        importedModelName=model_name,
        roleArn=role_arn,
        modelDataSource={
            "s3DataSource": {
                "s3Uri": s3_uri,
            }
        },
    )
    job_arn = response["jobArn"]
    print(f"Import job created: {job_arn}")
    return job_arn


def poll_import_job(
    bedrock_client,
    job_arn: str,
    poll_interval: int = 30,
) -> dict:
    """Poll a Bedrock import job until it reaches a terminal state.

    Returns:
        The final get_model_import_job response dict.

    Raises:
        RuntimeError: If the import job fails.
    """
    terminal_statuses = {"Completed", "Failed"}

    while True:
        response = bedrock_client.get_model_import_job(jobIdentifier=job_arn)
        status = response["status"]
        print(f"Import job status: {status}")

        if status in terminal_statuses:
            if status == "Failed":
                reason = response.get("failureMessage", "Unknown")
                raise RuntimeError(f"Import job failed: {reason}")
            return response

        time.sleep(poll_interval)


def write_model_arn(
    dynamodb_resource,
    model_name: str,
    model_arn: str,
) -> None:
    """Write the imported model ARN to DynamoDB for reference."""
    table = dynamodb_resource.Table(DYNAMODB_TABLE)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    table.put_item(
        Item={
            "job_id": f"bedrock-import-{model_name}",
            "timestamp": timestamp,
            "status": "Completed",
            "bedrock_model_arn": model_arn,
            "model_name": model_name,
        }
    )
    print(f"Model ARN written to DynamoDB table '{DYNAMODB_TABLE}'.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import a merged PEFT model into Amazon Bedrock."
    )
    parser.add_argument(
        "--model-name",
        default="peft-obama",
        help="Name for the imported Bedrock model (default: peft-obama)",
    )
    parser.add_argument(
        "--role-arn",
        default=None,
        help="IAM role ARN for Bedrock to read S3 (auto-detected if not provided)",
    )
    args = parser.parse_args()

    # Auto-detect AWS account ID and region
    sts = boto3.client("sts")
    account_id = sts.get_caller_identity()["Account"]
    region = boto3.session.Session().region_name or "eu-central-1"

    print(f"AWS Account: {account_id}")
    print(f"Region: {region}")

    # Build resource identifiers
    role_arn = args.role_arn or f"arn:aws:iam::{account_id}:role/PeftBedrockImportRole"
    s3_uri = f"s3://peft-model-artifacts-{account_id}/merged-model/"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    job_name = f"peft-import-{args.model_name}-{timestamp}"

    print(f"Model name: {args.model_name}")
    print(f"S3 URI: {s3_uri}")
    print(f"Role ARN: {role_arn}")
    print(f"Job name: {job_name}")

    # Create AWS clients
    bedrock_client = boto3.client("bedrock", region_name=region)
    dynamodb_resource = boto3.resource("dynamodb", region_name=region)

    # Step 1: Create the import job
    job_arn = create_import_job(
        bedrock_client=bedrock_client,
        job_name=job_name,
        model_name=args.model_name,
        role_arn=role_arn,
        s3_uri=s3_uri,
    )

    # Step 2: Poll until complete
    print("\nPolling import job status (every 30 seconds)...")
    result = poll_import_job(
        bedrock_client=bedrock_client,
        job_arn=job_arn,
        poll_interval=30,
    )

    model_arn = result["importedModelArn"]
    print(f"\nImport complete! Model ARN: {model_arn}")

    # Step 3: Write model ARN to DynamoDB
    write_model_arn(
        dynamodb_resource=dynamodb_resource,
        model_name=args.model_name,
        model_arn=model_arn,
    )

    print(f"\nUse this model ARN in your Lambda environment variable BEDROCK_MODEL_ID:")
    print(f"  {model_arn}")


if __name__ == "__main__":
    main()

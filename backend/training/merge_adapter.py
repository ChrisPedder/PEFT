"""
Merge LoRA adapter weights into the base model and upload to S3.

This creates a standalone model that can be loaded without the adapter separately.

Usage:
    python merge_adapter.py \
        --adapter-path ./output \
        --merged-output ./merged_model \
        [--upload-bucket peft-model-artifacts-XXXX]
"""

import argparse
import os

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge LoRA adapter into base model")
    parser.add_argument(
        "--adapter-path",
        required=True,
        help="Path to the trained LoRA adapter directory",
    )
    parser.add_argument(
        "--merged-output",
        required=True,
        help="Output directory for the merged model",
    )
    parser.add_argument(
        "--upload-bucket",
        default=None,
        help="S3 bucket to upload merged model (optional)",
    )
    args = parser.parse_args()

    os.makedirs(args.merged_output, exist_ok=True)

    print(f"Loading base model: {BASE_MODEL}")
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="cpu",
        low_cpu_mem_usage=True,
    )

    print(f"Loading adapter from: {args.adapter_path}")
    model = PeftModel.from_pretrained(base_model, args.adapter_path)

    print("Merging adapter weights...")
    model = model.merge_and_unload()

    print(f"Saving merged model to: {args.merged_output}")
    model.save_pretrained(args.merged_output, safe_serialization=True)

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    tokenizer.save_pretrained(args.merged_output)

    print("Merge complete!")

    # Optional: upload to S3
    if args.upload_bucket:
        import boto3

        s3 = boto3.client("s3")
        prefix = "merged-model/"

        print(f"Uploading to s3://{args.upload_bucket}/{prefix}...")
        for root, dirs, files in os.walk(args.merged_output):
            for fname in files:
                local_path = os.path.join(root, fname)
                rel_path = os.path.relpath(local_path, args.merged_output)
                s3_key = f"{prefix}{rel_path}"
                print(f"  {rel_path} → {s3_key}")
                s3.upload_file(local_path, args.upload_bucket, s3_key)

        print("Upload complete!")


if __name__ == "__main__":
    main()

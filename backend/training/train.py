"""
QLoRA fine-tuning script for Mistral-7B-Instruct on Obama Q&A data.

Designed to run as a SageMaker training job or locally on a GPU machine.

Usage (local):
    python train.py --data-path ./data/training_data.jsonl --output-dir ./output

Usage (SageMaker):
    Launched via SageMaker HuggingFace Estimator — reads from SM_CHANNEL_TRAINING
    and writes to SM_MODEL_DIR env vars.
"""

import argparse
import json
import os
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from trl import SFTTrainer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"
MAX_SEQ_LENGTH = 2048

LORA_CONFIG = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=[
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    ],
)

QUANTIZATION_CONFIG = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)


def format_instruction(sample: dict) -> str:
    """Format a training sample into Mistral's chat template."""
    return f"<s>[INST] {sample['instruction']} [/INST] " f"{sample['output']}</s>"


def load_dataset(data_path: str) -> Dataset:
    """Load JSONL training data."""
    samples = []
    with open(data_path) as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))

    print(f"Loaded {len(samples)} training samples")

    # Format into text field
    texts = [format_instruction(s) for s in samples]
    return Dataset.from_dict({"text": texts})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-path",
        default=os.environ.get("SM_CHANNEL_TRAINING", "./data/training_data.jsonl"),
        help="Path to training data JSONL (or SageMaker channel dir)",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("SM_MODEL_DIR", "./output"),
        help="Output directory for adapter weights",
    )
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--warmup-ratio", type=float, default=0.03)
    args = parser.parse_args()

    # Resolve data path — SageMaker passes a directory
    data_path = args.data_path
    if os.path.isdir(data_path):
        data_path = os.path.join(data_path, "training_data.jsonl")

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    print(f"Base model: {BASE_MODEL}")
    print(f"Data path: {data_path}")
    print(f"Output dir: {output_dir}")

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # Load model with 4-bit quantization
    print("Loading model with QLoRA quantization...")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=QUANTIZATION_CONFIG,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )

    # Prepare for k-bit training
    model = prepare_model_for_kbit_training(model)

    # Apply LoRA
    model = get_peft_model(model, LORA_CONFIG)
    model.print_trainable_parameters()

    # Load dataset
    dataset = load_dataset(data_path)

    # Training arguments
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        logging_steps=10,
        save_strategy="epoch",
        bf16=True,
        optim="paged_adamw_8bit",
        max_grad_norm=0.3,
        lr_scheduler_type="cosine",
        report_to="none",
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )

    # Trainer
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        tokenizer=tokenizer,
        args=training_args,
        max_seq_length=MAX_SEQ_LENGTH,
        dataset_text_field="text",
        packing=True,
    )

    print("Starting training...")
    trainer.train()

    # Save adapter weights
    print(f"Saving adapter to {output_dir}")
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    print("Training complete!")


if __name__ == "__main__":
    main()

"""Tests for backend/training/train.py — pure functions only (no GPU required)."""

import json
import sys
from importlib.machinery import ModuleSpec
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Import Dataset before mocking torch, so the datasets library can inspect
# the real (or absent) torch without interference from our mocks.
from datasets import Dataset

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _make_mock_module(name):
    """Create a MagicMock that behaves like a proper Python module for imports."""
    mod = MagicMock()
    mod.__spec__ = ModuleSpec(name, None)
    mod.__name__ = name
    mod.__package__ = name
    mod.__path__ = []
    mod.__file__ = f"/mock/{name}/__init__.py"
    return mod


# Create mock modules for the heavy ML dependencies
_mock_torch = _make_mock_module("torch")
_mock_torch.bfloat16 = "bfloat16"

_patches = {
    "torch": _mock_torch,
    "peft": _make_mock_module("peft"),
    "trl": _make_mock_module("trl"),
    "transformers": _make_mock_module("transformers"),
    "bitsandbytes": _make_mock_module("bitsandbytes"),
    "accelerate": _make_mock_module("accelerate"),
}

with patch.dict("sys.modules", _patches):
    from backend.training.train import format_instruction, load_dataset


class TestFormatInstruction:
    def test_format_instruction(self):
        """format_instruction wraps in the Mistral chat template."""
        sample = {
            "instruction": "What is your economic policy?",
            "input": "",
            "output": "Look, we need to invest in the middle class.",
        }
        result = format_instruction(sample)

        assert result.startswith("<s>[INST]")
        assert "[/INST]" in result
        assert result.endswith("</s>")
        assert "What is your economic policy?" in result
        assert "Look, we need to invest in the middle class." in result

    def test_format_instruction_special_chars(self):
        """format_instruction handles special characters in text."""
        sample = {
            "instruction": 'What about "hope & change"?',
            "input": "",
            "output": "That's the <core> of what we believe — 100%.",
        }
        result = format_instruction(sample)

        assert '<s>[INST] What about "hope & change"? [/INST]' in result
        assert "That's the <core> of what we believe — 100%.</s>" in result


class TestLoadDataset:
    def test_load_dataset(self, tmp_path):
        """load_dataset reads JSONL and returns a Dataset with formatted texts."""
        data_file = tmp_path / "training_data.jsonl"
        samples = [
            {
                "instruction": "What is your view?",
                "input": "",
                "output": "My view is clear.",
            },
            {
                "instruction": "How about jobs?",
                "input": "",
                "output": "We need more jobs.",
            },
        ]
        with open(data_file, "w") as f:
            for s in samples:
                f.write(json.dumps(s) + "\n")

        ds = load_dataset(str(data_file))

        assert isinstance(ds, Dataset)
        assert len(ds) == 2
        assert "text" in ds.column_names
        assert "<s>[INST]" in ds[0]["text"]
        assert "What is your view?" in ds[0]["text"]
        assert "My view is clear." in ds[0]["text"]

    def test_load_dataset_skips_empty_lines(self, tmp_path):
        """load_dataset skips blank lines in the JSONL file."""
        data_file = tmp_path / "training_data.jsonl"
        content = (
            json.dumps(
                {
                    "instruction": "Question?",
                    "input": "",
                    "output": "Answer.",
                }
            )
            + "\n\n\n"
            + json.dumps(
                {
                    "instruction": "Another?",
                    "input": "",
                    "output": "Response.",
                }
            )
            + "\n"
        )
        data_file.write_text(content)

        ds = load_dataset(str(data_file))

        assert len(ds) == 2
        assert "Question?" in ds[0]["text"]
        assert "Another?" in ds[1]["text"]

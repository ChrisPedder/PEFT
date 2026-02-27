"""Tests for backend/training/merge_adapter.py."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# Mock all heavy ML dependencies before importing
_mock_torch = MagicMock()
_mock_torch.bfloat16 = "bfloat16"
_mock_base_model = MagicMock()
_mock_peft_model = MagicMock()
_mock_merged_model = MagicMock()
_mock_tokenizer = MagicMock()

_mock_peft_model.merge_and_unload.return_value = _mock_merged_model
_mock_PeftModel = MagicMock()
_mock_PeftModel.from_pretrained.return_value = _mock_peft_model

_mock_AutoModel = MagicMock()
_mock_AutoModel.from_pretrained.return_value = _mock_base_model

_mock_AutoTokenizer = MagicMock()
_mock_AutoTokenizer.from_pretrained.return_value = _mock_tokenizer


class TestArgParsing:
    def test_arg_parsing(self):
        """Verify required args (adapter-path, merged-output) and optional upload-bucket."""
        with patch.dict(
            "sys.modules",
            {
                "torch": _mock_torch,
                "peft": MagicMock(PeftModel=_mock_PeftModel),
                "transformers": MagicMock(
                    AutoModelForCausalLM=_mock_AutoModel,
                    AutoTokenizer=_mock_AutoTokenizer,
                ),
            },
        ):
            import importlib
            import backend.training.merge_adapter as mod

            importlib.reload(mod)

            # Missing required args should cause SystemExit
            with patch("sys.argv", ["merge_adapter.py"]):
                with pytest.raises(SystemExit):
                    mod.main()


class TestMergeWithoutUpload:
    def test_merge_without_upload(self, tmp_path):
        """Merge completes without S3 upload when --upload-bucket is not set."""
        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        merged_dir = tmp_path / "merged"

        mock_base = MagicMock()
        mock_peft = MagicMock()
        mock_merged = MagicMock()
        mock_tok = MagicMock()

        mock_peft.merge_and_unload.return_value = mock_merged
        mock_PeftModel_local = MagicMock()
        mock_PeftModel_local.from_pretrained.return_value = mock_peft
        mock_AutoModel_local = MagicMock()
        mock_AutoModel_local.from_pretrained.return_value = mock_base
        mock_AutoTokenizer_local = MagicMock()
        mock_AutoTokenizer_local.from_pretrained.return_value = mock_tok

        with patch.dict(
            "sys.modules",
            {
                "torch": _mock_torch,
                "peft": MagicMock(PeftModel=mock_PeftModel_local),
                "transformers": MagicMock(
                    AutoModelForCausalLM=mock_AutoModel_local,
                    AutoTokenizer=mock_AutoTokenizer_local,
                ),
            },
        ):
            import importlib
            import backend.training.merge_adapter as mod

            importlib.reload(mod)

            with patch(
                "sys.argv",
                [
                    "merge_adapter.py",
                    "--adapter-path",
                    str(adapter_dir),
                    "--merged-output",
                    str(merged_dir),
                ],
            ):
                mod.main()

        mock_AutoModel_local.from_pretrained.assert_called_once()
        mock_PeftModel_local.from_pretrained.assert_called_once_with(
            mock_base, str(adapter_dir)
        )
        mock_peft.merge_and_unload.assert_called_once()
        mock_merged.save_pretrained.assert_called_once_with(
            str(merged_dir), safe_serialization=True
        )
        mock_AutoTokenizer_local.from_pretrained.assert_called_once_with(
            "mistralai/Mistral-7B-Instruct-v0.3", use_fast=False
        )
        mock_tok.save_pretrained.assert_called_once_with(str(merged_dir))


class TestS3Upload:
    @mock_aws
    def test_s3_upload_branch(self, tmp_path):
        """When --upload-bucket is set, merged model files are uploaded to S3."""
        # Create S3 bucket
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="my-model-bucket")

        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        merged_dir = tmp_path / "merged"
        merged_dir.mkdir()

        # Create some fake model files in merged_dir
        (merged_dir / "config.json").write_text('{"model_type":"test"}')
        (merged_dir / "model.safetensors").write_text("fake-weights")

        mock_base = MagicMock()
        mock_peft_m = MagicMock()
        mock_merged_m = MagicMock()
        mock_tok_m = MagicMock()

        mock_peft_m.merge_and_unload.return_value = mock_merged_m
        mock_PeftModel_s3 = MagicMock()
        mock_PeftModel_s3.from_pretrained.return_value = mock_peft_m
        mock_AutoModel_s3 = MagicMock()
        mock_AutoModel_s3.from_pretrained.return_value = mock_base
        mock_AutoTokenizer_s3 = MagicMock()
        mock_AutoTokenizer_s3.from_pretrained.return_value = mock_tok_m

        # Make save_pretrained a no-op (files already exist)
        mock_merged_m.save_pretrained = MagicMock()
        mock_tok_m.save_pretrained = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "torch": _mock_torch,
                "peft": MagicMock(PeftModel=mock_PeftModel_s3),
                "transformers": MagicMock(
                    AutoModelForCausalLM=mock_AutoModel_s3,
                    AutoTokenizer=mock_AutoTokenizer_s3,
                ),
            },
        ):
            import importlib
            import backend.training.merge_adapter as mod

            importlib.reload(mod)

            with patch(
                "sys.argv",
                [
                    "merge_adapter.py",
                    "--adapter-path",
                    str(adapter_dir),
                    "--merged-output",
                    str(merged_dir),
                    "--upload-bucket",
                    "my-model-bucket",
                ],
            ):
                mod.main()

        # Verify files were uploaded to S3
        objs = s3.list_objects_v2(Bucket="my-model-bucket")
        keys = sorted([o["Key"] for o in objs["Contents"]])
        assert "merged-model/config.json" in keys
        assert "merged-model/model.safetensors" in keys

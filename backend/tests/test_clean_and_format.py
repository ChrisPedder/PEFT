"""Tests for backend/scraper/clean_and_format.py."""

import json
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# We must patch boto3.client before importing the module,
# because clean_and_format instantiates the client at module level.
_mock_bedrock_client = MagicMock()
with patch("boto3.client", return_value=_mock_bedrock_client):
    from backend.scraper.clean_and_format import (
        clean_text,
        generate_qa_pairs,
        load_speeches_from_s3,
        main,
        parse_args,
    )


class TestCleanText:
    def test_clean_text_removes_artifacts(self):
        """clean_text strips [applause], [laughter], [crosstalk] markers."""
        text = "Thank you [applause] so much [LAUGHTER] for being here [Crosstalk]."
        result = clean_text(text)
        assert "[applause]" not in result
        assert "[laughter]" not in result.lower()
        assert "[crosstalk]" not in result.lower()
        assert "Thank you" in result
        assert "for being here" in result

    def test_clean_text_normalizes_whitespace(self):
        """clean_text collapses excessive newlines and spaces."""
        text = "Hello\n\n\n\n\nWorld\n\n\nFoo   bar    baz"
        result = clean_text(text)
        assert "\n\n\n" not in result
        assert "  " not in result
        assert "Hello" in result
        assert "World" in result
        assert "Foo bar baz" in result


def _bedrock_response(
    qa_json: str, input_tokens: int = 500, output_tokens: int = 300
) -> dict:
    """Build a Bedrock converse() response dict."""
    return {
        "output": {"message": {"content": [{"text": qa_json}]}},
        "usage": {"inputTokens": input_tokens, "outputTokens": output_tokens},
    }


class TestGenerateQaPairs:
    @patch("backend.scraper.clean_and_format.bedrock")
    def test_generate_qa_pairs_success(self, mock_bedrock):
        """generate_qa_pairs parses valid JSON response into instruction/output pairs."""
        qa_json = json.dumps(
            [
                {
                    "instruction": "What about the economy?",
                    "output": "Look, the economy is improving.",
                },
                {
                    "instruction": "What about healthcare?",
                    "output": "Let me be clear, healthcare matters.",
                },
            ]
        )
        mock_bedrock.converse.return_value = _bedrock_response(qa_json)

        speech = {
            "title": "Remarks on Economy",
            "date": "2010-01-01",
            "text": "Today I want to talk about the economy. " * 10,
        }
        pairs, usage = generate_qa_pairs(speech)

        assert len(pairs) == 2
        assert pairs[0]["instruction"] == "What about the economy?"
        assert pairs[0]["output"] == "Look, the economy is improving."
        assert pairs[0]["input"] == ""
        assert pairs[1]["instruction"] == "What about healthcare?"
        assert usage["inputTokens"] == 500
        assert usage["outputTokens"] == 300

    @patch("backend.scraper.clean_and_format.bedrock")
    def test_generate_qa_pairs_with_code_block(self, mock_bedrock):
        """generate_qa_pairs handles JSON wrapped in markdown code blocks."""
        qa_json = '```json\n[{"instruction": "Q?", "output": "A."}]\n```'
        mock_bedrock.converse.return_value = _bedrock_response(qa_json)

        speech = {
            "title": "Speech",
            "date": "2010-01-01",
            "text": "Some speech text here. " * 10,
        }
        pairs, usage = generate_qa_pairs(speech)

        assert len(pairs) == 1
        assert pairs[0]["instruction"] == "Q?"
        assert pairs[0]["output"] == "A."

    @patch("backend.scraper.clean_and_format.bedrock")
    def test_generate_qa_pairs_api_error(self, mock_bedrock):
        """generate_qa_pairs returns empty list on Bedrock ClientError."""
        mock_bedrock.converse.side_effect = ClientError(
            error_response={
                "Error": {"Code": "ThrottlingException", "Message": "Rate limited"}
            },
            operation_name="Converse",
        )

        speech = {
            "title": "Speech",
            "date": "2010-01-01",
            "text": "Some speech text. " * 10,
        }
        pairs, usage = generate_qa_pairs(speech)
        assert pairs == []
        assert usage == {}

    @patch("backend.scraper.clean_and_format.bedrock")
    def test_generate_qa_pairs_truncates_long_text(self, mock_bedrock):
        """generate_qa_pairs truncates text longer than 6000 chars."""
        qa_json = json.dumps([{"instruction": "Q?", "output": "A."}])
        mock_bedrock.converse.return_value = _bedrock_response(qa_json)

        speech = {
            "title": "Long Speech",
            "date": "2010-01-01",
            "text": "A" * 8000,
        }
        generate_qa_pairs(speech)

        # Verify the prompt sent to the API contains truncated text
        call_args = mock_bedrock.converse.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        prompt_content = messages[0]["content"][0]["text"]
        assert "[truncated]" in prompt_content


class TestParseArgs:
    def test_defaults(self):
        """parse_args returns correct defaults with no arguments."""
        args = parse_args([])
        assert args.bucket is None
        assert args.output_bucket is None
        assert args.sample == 0
        assert args.seed == 42

    def test_all_args(self):
        """parse_args parses all arguments correctly."""
        args = parse_args(
            [
                "--bucket",
                "my-data-bucket",
                "--output-bucket",
                "my-training-bucket",
                "--sample",
                "50",
                "--seed",
                "123",
            ]
        )
        assert args.bucket == "my-data-bucket"
        assert args.output_bucket == "my-training-bucket"
        assert args.sample == 50
        assert args.seed == 123


class TestLoadSpeechesFromS3:
    @patch("backend.scraper.clean_and_format.boto3.client")
    def test_load_speeches_from_s3(self, mock_boto3_client):
        """load_speeches_from_s3 reads individual speech files via paginator."""
        speech1 = {"title": "Speech 1", "date": "2010-01-01", "text": "Hello world"}
        speech2 = {"title": "Speech 2", "date": "2010-02-01", "text": "Goodbye world"}

        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        # Mock paginator
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "raw/individual/speech1.jsonl"},
                    {"Key": "raw/individual/speech2.jsonl"},
                    {"Key": "raw/individual/readme.txt"},  # should be skipped
                ]
            }
        ]

        # Mock get_object
        def mock_get_object(Bucket, Key):
            if "speech1" in Key:
                body = json.dumps(speech1)
            else:
                body = json.dumps(speech2)
            return {"Body": BytesIO(body.encode())}

        mock_s3.get_object.side_effect = mock_get_object

        speeches = load_speeches_from_s3("test-bucket")

        assert len(speeches) == 2
        assert speeches[0]["title"] == "Speech 1"
        assert speeches[1]["title"] == "Speech 2"

        mock_s3.get_paginator.assert_called_once_with("list_objects_v2")
        mock_paginator.paginate.assert_called_once_with(
            Bucket="test-bucket", Prefix="raw/individual/"
        )
        # Only .jsonl files fetched (not readme.txt)
        assert mock_s3.get_object.call_count == 2


class TestMain:
    @patch("backend.scraper.clean_and_format.bedrock")
    def test_main_local_mode(self, mock_bedrock, tmp_path):
        """main reads from local file when no --bucket arg is given."""
        input_file = tmp_path / "raw_speeches.jsonl"
        speech = {
            "title": "Test Speech",
            "date": "2010-01-01",
            "source": "app",
            "url": "https://example.com/speech",
            "text": "This is a speech about policy. " * 10,
        }
        with open(input_file, "w") as f:
            f.write(json.dumps(speech) + "\n")

        output_file = tmp_path / "training_data.jsonl"

        qa_json = json.dumps(
            [
                {
                    "instruction": "What about policy?",
                    "output": "Look, policy is important.",
                }
            ]
        )
        mock_bedrock.converse.return_value = _bedrock_response(qa_json)

        with (
            patch("backend.scraper.clean_and_format.INPUT_FILE", input_file),
            patch("backend.scraper.clean_and_format.OUTPUT_FILE", output_file),
        ):
            main([])

        assert output_file.exists()
        with open(output_file) as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert len(lines) == 1
        assert lines[0]["instruction"] == "What about policy?"

    @patch("backend.scraper.clean_and_format.bedrock")
    def test_main_sample_flag(self, mock_bedrock, tmp_path):
        """main with --sample N selects a subset of speeches."""
        input_file = tmp_path / "raw_speeches.jsonl"
        with open(input_file, "w") as f:
            for i in range(10):
                speech = {
                    "title": f"Speech {i}",
                    "date": "2010-01-01",
                    "text": f"Speech number {i} about topics. " * 10,
                }
                f.write(json.dumps(speech) + "\n")

        output_file = tmp_path / "training_data.jsonl"

        qa_json = json.dumps([{"instruction": "Q?", "output": "A."}])
        mock_bedrock.converse.return_value = _bedrock_response(qa_json)

        with (
            patch("backend.scraper.clean_and_format.INPUT_FILE", input_file),
            patch("backend.scraper.clean_and_format.OUTPUT_FILE", output_file),
        ):
            main(["--sample", "3", "--seed", "42"])

        # Should generate pairs for only 3 speeches
        assert mock_bedrock.converse.call_count == 3

    @patch("backend.scraper.clean_and_format.upload_to_s3")
    @patch("backend.scraper.clean_and_format.load_speeches_from_s3")
    @patch("backend.scraper.clean_and_format.bedrock")
    def test_main_s3_mode(self, mock_bedrock, mock_load, mock_upload, tmp_path):
        """main with --bucket reads from S3 and --output-bucket uploads result."""
        mock_load.return_value = [
            {"title": "S3 Speech", "date": "2010-01-01", "text": "Hello from S3. " * 10}
        ]

        qa_json = json.dumps([{"instruction": "Q?", "output": "A."}])
        mock_bedrock.converse.return_value = _bedrock_response(qa_json)

        output_file = tmp_path / "training_data.jsonl"

        with patch("backend.scraper.clean_and_format.OUTPUT_FILE", output_file):
            main(["--bucket", "my-data", "--output-bucket", "my-training"])

        mock_load.assert_called_once_with("my-data")
        mock_upload.assert_called_once_with(
            output_file, "my-training", "training_data.jsonl"
        )

        assert output_file.exists()
        with open(output_file) as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert len(lines) == 1

    def test_main_missing_input(self, tmp_path):
        """main exits with code 1 when input file does not exist."""
        missing_file = tmp_path / "nonexistent.jsonl"

        with (
            patch("backend.scraper.clean_and_format.INPUT_FILE", missing_file),
            pytest.raises(SystemExit) as exc_info,
        ):
            main([])

        assert exc_info.value.code == 1

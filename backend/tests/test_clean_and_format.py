"""Tests for backend/scraper/clean_and_format.py."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# We must patch anthropic.Anthropic before importing the module,
# because clean_and_format instantiates the client at module level.
_mock_anthropic_client = MagicMock()
with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
    with patch("anthropic.Anthropic", return_value=_mock_anthropic_client):
        from backend.scraper.clean_and_format import (
            clean_text,
            generate_qa_pairs,
            main,
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


class TestGenerateQaPairs:
    @patch("backend.scraper.clean_and_format.client")
    def test_generate_qa_pairs_success(self, mock_client):
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
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=qa_json)]
        mock_client.messages.create.return_value = mock_response

        speech = {
            "title": "Remarks on Economy",
            "date": "2010-01-01",
            "text": "Today I want to talk about the economy. " * 10,
        }
        result = generate_qa_pairs(speech)

        assert len(result) == 2
        assert result[0]["instruction"] == "What about the economy?"
        assert result[0]["output"] == "Look, the economy is improving."
        assert result[0]["input"] == ""
        assert result[1]["instruction"] == "What about healthcare?"

    @patch("backend.scraper.clean_and_format.client")
    def test_generate_qa_pairs_with_code_block(self, mock_client):
        """generate_qa_pairs handles JSON wrapped in markdown code blocks."""
        qa_json = '```json\n[{"instruction": "Q?", "output": "A."}]\n```'
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=qa_json)]
        mock_client.messages.create.return_value = mock_response

        speech = {
            "title": "Speech",
            "date": "2010-01-01",
            "text": "Some speech text here. " * 10,
        }
        result = generate_qa_pairs(speech)

        assert len(result) == 1
        assert result[0]["instruction"] == "Q?"
        assert result[0]["output"] == "A."

    @patch("backend.scraper.clean_and_format.client")
    def test_generate_qa_pairs_api_error(self, mock_client):
        """generate_qa_pairs returns empty list on API error."""
        import anthropic

        mock_client.messages.create.side_effect = anthropic.APIError(
            message="Rate limited",
            request=MagicMock(),
            body=None,
        )

        speech = {
            "title": "Speech",
            "date": "2010-01-01",
            "text": "Some speech text. " * 10,
        }
        result = generate_qa_pairs(speech)
        assert result == []

    @patch("backend.scraper.clean_and_format.client")
    def test_generate_qa_pairs_truncates_long_text(self, mock_client):
        """generate_qa_pairs truncates text longer than 6000 chars."""
        qa_json = json.dumps([{"instruction": "Q?", "output": "A."}])
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=qa_json)]
        mock_client.messages.create.return_value = mock_response

        speech = {
            "title": "Long Speech",
            "date": "2010-01-01",
            "text": "A" * 8000,
        }
        generate_qa_pairs(speech)

        # Verify the prompt sent to the API contains truncated text
        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        prompt_content = messages[0]["content"]
        assert "[truncated]" in prompt_content


class TestMain:
    @patch("backend.scraper.clean_and_format.client")
    def test_main_success(self, mock_client, tmp_path):
        """main reads input, generates Q&A pairs, and writes output."""
        # Create input file
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
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=qa_json)]
        mock_client.messages.create.return_value = mock_response

        with (
            patch("backend.scraper.clean_and_format.INPUT_FILE", input_file),
            patch("backend.scraper.clean_and_format.OUTPUT_FILE", output_file),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
        ):
            main()

        assert output_file.exists()
        with open(output_file) as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert len(lines) == 1
        assert lines[0]["instruction"] == "What about policy?"

    def test_main_missing_input(self, tmp_path):
        """main exits with code 1 when input file does not exist."""
        missing_file = tmp_path / "nonexistent.jsonl"

        with (
            patch("backend.scraper.clean_and_format.INPUT_FILE", missing_file),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1

    def test_main_missing_api_key(self, tmp_path):
        """main exits with code 1 when ANTHROPIC_API_KEY is not set."""
        input_file = tmp_path / "raw_speeches.jsonl"
        input_file.write_text('{"title":"t","text":"t"}\n')

        with (
            patch("backend.scraper.clean_and_format.INPUT_FILE", input_file),
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1

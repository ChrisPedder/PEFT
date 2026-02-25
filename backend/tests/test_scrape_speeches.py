"""Tests for backend/scraper/scrape_speeches.py."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import responses

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.scraper.scrape_speeches import (
    APP_BASE,
    APP_SEARCH,
    WH_BASE,
    WH_INDEX,
    deduplicate,
    fetch_page,
    main,
    scrape_app_index,
    scrape_app_speech,
    scrape_wh_index,
    scrape_wh_speech,
)


@responses.activate
def test_fetch_page_success():
    """fetch_page returns a BeautifulSoup object on a 200 response."""
    url = "https://example.com/test"
    responses.add(
        responses.GET,
        url,
        body="<html><body><h1>Hello</h1></body></html>",
        status=200,
        content_type="text/html",
    )

    soup = fetch_page(url)
    assert soup is not None
    assert soup.find("h1").get_text() == "Hello"


@responses.activate
def test_fetch_page_failure():
    """fetch_page returns None on a 500 response."""
    url = "https://example.com/error"
    responses.add(responses.GET, url, status=500)

    result = fetch_page(url)
    assert result is None


@responses.activate
@patch("backend.scraper.scrape_speeches.time.sleep")
def test_scrape_app_index(mock_sleep):
    """scrape_app_index extracts speech URLs from the APP index page."""
    # Page 0 with results
    page0_html = """
    <html><body>
    <div class="view-content">
      <div class="views-row">
        <a href="/documents/inaugural-address">Inaugural Address</a>
        <span class="date-display-single">January 20, 2009</span>
      </div>
      <div class="views-row">
        <a href="/documents/remarks-on-economy">Remarks on Economy</a>
        <span class="date-display-single">February 4, 2009</span>
      </div>
    </div>
    </body></html>
    """
    # Page 1 with no results (stops pagination)
    page1_html = "<html><body><div class='view-content'></div></body></html>"

    responses.add(
        responses.GET,
        f"{APP_SEARCH}&page=0",
        body=page0_html,
        status=200,
        content_type="text/html",
    )
    responses.add(
        responses.GET,
        f"{APP_SEARCH}&page=1",
        body=page1_html,
        status=200,
        content_type="text/html",
    )

    result = scrape_app_index()

    assert len(result) == 2
    assert result[0]["title"] == "Inaugural Address"
    assert result[0]["date"] == "January 20, 2009"
    assert result[0]["source"] == "app"
    assert "/documents/inaugural-address" in result[0]["url"]
    assert result[1]["title"] == "Remarks on Economy"
    mock_sleep.assert_called()


@responses.activate
def test_scrape_app_speech_success():
    """scrape_app_speech extracts text from a speech page with sufficient content."""
    url = "https://www.presidency.ucsb.edu/documents/test-speech"
    long_text = "This is a long speech about important topics. " * 20  # > 200 chars
    speech_html = f"""
    <html><body>
    <div class="field-docs-content">
      <p>{long_text}</p>
    </div>
    </body></html>
    """

    responses.add(
        responses.GET, url, body=speech_html, status=200, content_type="text/html"
    )

    meta = {
        "url": url,
        "title": "Test Speech",
        "date": "March 1, 2010",
        "source": "app",
    }
    result = scrape_app_speech(meta)

    assert result is not None
    assert result["title"] == "Test Speech"
    assert result["date"] == "March 1, 2010"
    assert result["source"] == "app"
    assert result["url"] == url
    assert len(result["text"]) > 200


@responses.activate
def test_scrape_app_speech_too_short():
    """scrape_app_speech returns None when text is under 200 characters."""
    url = "https://www.presidency.ucsb.edu/documents/short-speech"
    speech_html = """
    <html><body>
    <div class="field-docs-content"><p>Very short.</p></div>
    </body></html>
    """

    responses.add(
        responses.GET, url, body=speech_html, status=200, content_type="text/html"
    )

    meta = {
        "url": url,
        "title": "Short Speech",
        "date": "March 1, 2010",
        "source": "app",
    }
    result = scrape_app_speech(meta)
    assert result is None


@responses.activate
@patch("backend.scraper.scrape_speeches.time.sleep")
def test_scrape_wh_index(mock_sleep):
    """scrape_wh_index extracts speech URLs from the WH archives index."""
    page0_html = """
    <html><body>
    <div class="views-row">
      <h3><a href="/briefing-room/speeches/remarks-1">Remarks at Town Hall</a></h3>
      <span class="date-display-single">April 10, 2012</span>
    </div>
    <div class="views-row">
      <h3><a href="/briefing-room/speeches/remarks-2">Weekly Address</a></h3>
      <time>April 14, 2012</time>
    </div>
    </body></html>
    """
    page1_html = "<html><body></body></html>"

    responses.add(
        responses.GET,
        f"{WH_INDEX}?page=0",
        body=page0_html,
        status=200,
        content_type="text/html",
    )
    responses.add(
        responses.GET,
        f"{WH_INDEX}?page=1",
        body=page1_html,
        status=200,
        content_type="text/html",
    )

    result = scrape_wh_index()

    assert len(result) == 2
    assert result[0]["title"] == "Remarks at Town Hall"
    assert result[0]["source"] == "wh_archives"
    assert "/briefing-room/speeches/remarks-1" in result[0]["url"]
    assert result[1]["title"] == "Weekly Address"
    mock_sleep.assert_called()


@responses.activate
def test_scrape_wh_speech_success():
    """scrape_wh_speech extracts text from a WH archives speech page."""
    url = "https://obamawhitehouse.archives.gov/briefing-room/speeches/remarks-1"
    long_text = "Today I want to talk about the future of our country. " * 20

    speech_html = f"""
    <html><body>
    <div class="field-name-body">
      <p>{long_text}</p>
    </div>
    </body></html>
    """

    responses.add(
        responses.GET, url, body=speech_html, status=200, content_type="text/html"
    )

    meta = {
        "url": url,
        "title": "Remarks at Town Hall",
        "date": "April 10, 2012",
        "source": "wh_archives",
    }
    result = scrape_wh_speech(meta)

    assert result is not None
    assert result["title"] == "Remarks at Town Hall"
    assert result["source"] == "wh_archives"
    assert len(result["text"]) > 200


def test_deduplicate():
    """deduplicate removes entries with identical normalized titles."""
    speeches = [
        {
            "title": "Remarks by the President",
            "text": "speech 1",
            "source": "app",
        },
        {
            "title": "REMARKS BY THE PRESIDENT",
            "text": "speech 2",
            "source": "wh_archives",
        },
        {
            "title": "Remarks by the President!",
            "text": "speech 3",
            "source": "app",
        },
        {
            "title": "A Different Speech",
            "text": "speech 4",
            "source": "app",
        },
    ]

    result = deduplicate(speeches)

    assert len(result) == 2
    assert result[0]["title"] == "Remarks by the President"
    assert result[1]["title"] == "A Different Speech"


@patch("backend.scraper.scrape_speeches.time.sleep")
@patch("backend.scraper.scrape_speeches.scrape_wh_speech")
@patch("backend.scraper.scrape_speeches.scrape_wh_index")
@patch("backend.scraper.scrape_speeches.scrape_app_speech")
@patch("backend.scraper.scrape_speeches.scrape_app_index")
def test_main(
    mock_app_index,
    mock_app_speech,
    mock_wh_index,
    mock_wh_speech,
    mock_sleep,
    tmp_path,
):
    """main orchestrates scraping from both sources and writes JSONL output."""
    mock_app_index.return_value = [
        {
            "url": "https://example.com/s1",
            "title": "Speech One",
            "date": "Jan 1, 2010",
            "source": "app",
        }
    ]
    mock_app_speech.return_value = {
        "title": "Speech One",
        "date": "Jan 1, 2010",
        "source": "app",
        "url": "https://example.com/s1",
        "text": "Full text of speech one. " * 20,
    }
    mock_wh_index.return_value = [
        {
            "url": "https://example.com/s2",
            "title": "Speech Two",
            "date": "Feb 1, 2010",
            "source": "wh_archives",
        }
    ]
    mock_wh_speech.return_value = {
        "title": "Speech Two",
        "date": "Feb 1, 2010",
        "source": "wh_archives",
        "url": "https://example.com/s2",
        "text": "Full text of speech two. " * 20,
    }

    output_file = tmp_path / "raw_speeches.jsonl"

    with (
        patch("backend.scraper.scrape_speeches.DATA_DIR", tmp_path),
        patch("backend.scraper.scrape_speeches.OUTPUT_FILE", output_file),
    ):
        main()

    assert output_file.exists()
    with open(output_file) as f:
        lines = [json.loads(line) for line in f if line.strip()]

    assert len(lines) == 2
    assert lines[0]["title"] == "Speech One"
    assert lines[1]["title"] == "Speech Two"

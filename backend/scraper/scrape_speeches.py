"""
Scrape Obama speeches from:
  1. American Presidency Project (UCSB) — primary source
  2. Obama White House Archives — supplementary

Outputs raw speeches as JSONL to backend/scraper/data/raw_speeches.jsonl
"""

import argparse
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = DATA_DIR / "raw_speeches.jsonl"

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (research project; educational use) " "PeftScraper/1.0"
        )
    }
)

# Polite delay between requests (seconds)
REQUEST_DELAY = 1.5


def fetch_page(url: str) -> BeautifulSoup | None:
    """Fetch a page and return parsed HTML, or None on failure."""
    try:
        resp = SESSION.get(url, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Source 1: American Presidency Project (UCSB)
# ---------------------------------------------------------------------------

APP_BASE = "https://www.presidency.ucsb.edu"
APP_SEARCH = (
    f"{APP_BASE}/advanced-search"
    "?field-keywords=&field-keywords2=&field-keywords3="
    "&from%5Bdate%5D=01-20-2009&to%5Bdate%5D=01-20-2017"
    "&person2=200300"  # Barack Obama
    "&category2%5B%5D=8"  # Spoken Addresses and Remarks
    "&category2%5B%5D=46"  # Inaugural Addresses
    "&category2%5B%5D=45"  # State of the Union Addresses
    "&category2%5B%5D=52"  # Farewell Addresses
    "&category2%5B%5D=48"  # Saturday Weekly Addresses
    "&items_per_page=100"
)


def scrape_app_index() -> list[dict]:
    """Scrape the search index to get speech URLs from APP."""
    urls: list[dict] = []
    page = 0

    while True:
        url = f"{APP_SEARCH}&page={page}"
        logger.info("Fetching APP index page %d...", page)
        soup = fetch_page(url)
        if soup is None:
            break

        rows = soup.select("table.views-table tbody tr")
        if not rows:
            break

        for row in rows:
            cells = row.select("td")
            if len(cells) < 3:
                continue
            date_text = cells[0].get_text(strip=True)
            link_el = cells[2].select_one("a")
            if link_el and link_el.get("href"):
                urls.append(
                    {
                        "url": urljoin(APP_BASE, link_el["href"]),
                        "title": link_el.get_text(strip=True),
                        "date": date_text,
                        "source": "app",
                    }
                )

        page += 1
        time.sleep(REQUEST_DELAY)

    return urls


def scrape_app_speech(meta: dict) -> dict | None:
    """Scrape a single speech page from APP."""
    soup = fetch_page(meta["url"])
    if soup is None:
        return None

    body = soup.select_one("div.field-docs-content")
    if not body:
        return None

    text = body.get_text(separator="\n", strip=True)
    if len(text) < 200:
        return None

    return {
        "title": meta["title"],
        "date": meta["date"],
        "source": meta["source"],
        "url": meta["url"],
        "text": text,
    }


# ---------------------------------------------------------------------------
# Source 2: Obama White House Archives
# ---------------------------------------------------------------------------

WH_BASE = "https://obamawhitehouse.archives.gov"
WH_INDEX = f"{WH_BASE}/briefing-room/speeches-and-remarks"


def _is_obama_speech(title: str) -> bool:
    """Return True if the title likely refers to a speech by President Obama."""
    lower = title.lower().strip()
    # Positive match: title mentions Obama as the speaker
    if (
        "the president" in lower
        or "president obama" in lower
        or "president barack" in lower
    ):
        return True
    # Weekly addresses and their Spanish translations are Obama's
    if lower.startswith(("weekly address", "saturday address", "mensaje semanal")):
        return True
    # Spanish presidential remarks
    if "declaraciones del presidente" in lower:
        return True
    return False


def scrape_wh_index() -> list[dict]:
    """Scrape the White House archives index for speech URLs."""
    urls: list[dict] = []
    skipped = 0
    page = 0

    while True:
        url = f"{WH_INDEX}?page={page}"
        logger.info("Fetching WH index page %d...", page)
        soup = fetch_page(url)
        if soup is None:
            break

        items = soup.select("div.views-row")
        if not items:
            break

        for item in items:
            link_el = item.select_one("h3 a, .field-title a")
            date_el = item.select_one(".date-display-single, time")
            if link_el and link_el.get("href"):
                title = link_el.get_text(strip=True)
                if not _is_obama_speech(title):
                    skipped += 1
                    continue
                urls.append(
                    {
                        "url": urljoin(WH_BASE, link_el["href"]),
                        "title": title,
                        "date": date_el.get_text(strip=True) if date_el else "",
                        "source": "wh_archives",
                    }
                )

        page += 1
        time.sleep(REQUEST_DELAY)

    logger.info("Skipped %d non-Obama entries from WH archives", skipped)
    return urls


def scrape_wh_speech(meta: dict) -> dict | None:
    """Scrape a single speech from the White House archives."""
    soup = fetch_page(meta["url"])
    if soup is None:
        return None

    body = soup.select_one(
        "div.field-name-field-forall-body, div.field-name-body, div.pane-node-body, article .field--type-text-with-summary"
    )
    if not body:
        return None

    text = body.get_text(separator="\n", strip=True)
    if len(text) < 200:
        return None

    return {
        "title": meta["title"],
        "date": meta["date"],
        "source": meta["source"],
        "url": meta["url"],
        "text": text,
    }


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def deduplicate(speeches: list[dict]) -> list[dict]:
    """Remove duplicates based on title similarity."""
    seen_titles: set[str] = set()
    unique: list[dict] = []

    for s in speeches:
        # Normalize title for comparison
        norm = re.sub(r"[^a-z0-9 ]", "", s["title"].lower()).strip()
        norm = re.sub(r"\s+", " ", norm)
        if norm not in seen_titles:
            seen_titles.add(norm)
            unique.append(s)

    return unique


# ---------------------------------------------------------------------------
# Incremental S3 upload
# ---------------------------------------------------------------------------


def upload_speech_to_s3(speech: dict, index: int, bucket: str) -> None:
    """Upload a single speech as an individual S3 object."""
    import boto3

    s3 = boto3.client("s3")
    key = f"raw/individual/{index:05d}.jsonl"
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(speech) + "\n",
        ContentType="application/json",
    )
    logger.info("Uploaded to s3://%s/%s", bucket, key)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Obama speeches")
    parser.add_argument(
        "--bucket",
        default=None,
        help="S3 bucket to upload individual speech files to (optional)",
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Scrape all speeches to local file first (for resilience / local dev)
    with open(OUTPUT_FILE, "w") as f:
        # Source 1: American Presidency Project
        logger.info("=== Scraping American Presidency Project ===")
        app_index = scrape_app_index()
        logger.info("Found %d entries", len(app_index))

        for i, meta in enumerate(app_index, 1):
            speech = scrape_app_speech(meta)
            if speech:
                f.write(json.dumps(speech) + "\n")
                f.flush()
            logger.info("[APP %d/%d] %s", i, len(app_index), meta["title"])
            time.sleep(REQUEST_DELAY)

        # Source 2: White House Archives
        logger.info("=== Scraping White House Archives ===")
        wh_index = scrape_wh_index()
        logger.info("Found %d entries", len(wh_index))

        for i, meta in enumerate(wh_index, 1):
            speech = scrape_wh_speech(meta)
            if speech:
                f.write(json.dumps(speech) + "\n")
                f.flush()
            logger.info("[WH %d/%d] %s", i, len(wh_index), meta["title"])
            time.sleep(REQUEST_DELAY)

    # Re-read to deduplicate (need full list for comparison)
    all_speeches: list[dict] = []
    with open(OUTPUT_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                all_speeches.append(json.loads(line))

    unique_speeches = deduplicate(all_speeches)
    logger.info(
        "Total unique speeches: %d (from %d raw)",
        len(unique_speeches),
        len(all_speeches),
    )

    # Rewrite with deduplicated set
    with open(OUTPUT_FILE, "w") as f:
        for speech in unique_speeches:
            f.write(json.dumps(speech) + "\n")

    logger.info("Saved to %s", OUTPUT_FILE)

    # Upload deduplicated speeches as individual files to S3
    if args.bucket:
        logger.info("Uploading %d speeches to S3...", len(unique_speeches))
        for i, speech in enumerate(unique_speeches):
            upload_speech_to_s3(speech, i, args.bucket)
        logger.info("Uploaded %d individual speech files to S3", len(unique_speeches))


if __name__ == "__main__":
    main()

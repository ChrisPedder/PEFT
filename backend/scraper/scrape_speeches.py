"""
Scrape Obama speeches from:
  1. American Presidency Project (UCSB) — primary source
  2. Obama White House Archives — supplementary

Outputs raw speeches as JSONL to backend/scraper/data/raw_speeches.jsonl
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

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
        print(f"  [WARN] Failed to fetch {url}: {e}")
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
    "&items_per_page=100"
)


def scrape_app_index() -> list[dict]:
    """Scrape the search index to get speech URLs from APP."""
    urls: list[dict] = []
    page = 0

    while True:
        url = f"{APP_SEARCH}&page={page}"
        print(f"  Fetching APP index page {page}...")
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


def scrape_wh_index() -> list[dict]:
    """Scrape the White House archives index for speech URLs."""
    urls: list[dict] = []
    page = 0

    while True:
        url = f"{WH_INDEX}?page={page}"
        print(f"  Fetching WH index page {page}...")
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
                urls.append(
                    {
                        "url": urljoin(WH_BASE, link_el["href"]),
                        "title": link_el.get_text(strip=True),
                        "date": date_el.get_text(strip=True) if date_el else "",
                        "source": "wh_archives",
                    }
                )

        page += 1
        time.sleep(REQUEST_DELAY)

    return urls


def scrape_wh_speech(meta: dict) -> dict | None:
    """Scrape a single speech from the White House archives."""
    soup = fetch_page(meta["url"])
    if soup is None:
        return None

    body = soup.select_one(
        "div.field-name-body, div.pane-node-body, article .field--type-text-with-summary"
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
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    all_speeches: list[dict] = []

    # Source 1: American Presidency Project
    print("=== Scraping American Presidency Project ===")
    app_index = scrape_app_index()
    print(f"  Found {len(app_index)} entries")

    for meta in tqdm(app_index, desc="APP speeches"):
        speech = scrape_app_speech(meta)
        if speech:
            all_speeches.append(speech)
        time.sleep(REQUEST_DELAY)

    # Source 2: White House Archives
    print("\n=== Scraping White House Archives ===")
    wh_index = scrape_wh_index()
    print(f"  Found {len(wh_index)} entries")

    for meta in tqdm(wh_index, desc="WH speeches"):
        speech = scrape_wh_speech(meta)
        if speech:
            all_speeches.append(speech)
        time.sleep(REQUEST_DELAY)

    # Deduplicate
    all_speeches = deduplicate(all_speeches)
    print(f"\n=== Total unique speeches: {len(all_speeches)} ===")

    # Write output
    with open(OUTPUT_FILE, "w") as f:
        for speech in all_speeches:
            f.write(json.dumps(speech) + "\n")

    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

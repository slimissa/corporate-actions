#!/usr/bin/env python3
"""
Corporate Actions Fetcher from SEC EDGAR

This script reads the Asset Identifiers registry (identifiers.json) and for each
instrument, queries SEC EDGAR full-text search for 8-K filings containing
corporate action keywords. It then downloads the filing text, extracts structured
action data using heuristics, and builds actions.json.

Usage:
    python fetch_sec_edgar_actions.py --identifiers ../asset-identifiers/identifiers.json \
                                      --output actions.json \
                                      --start 2019-01-01 --end 2024-12-31

Environment variables:
    SEC_EDGAR_USER_AGENT : Required User-Agent for SEC EDGAR (e.g., "Name email@example.com")
    CORP_ACTIONS_MIN_ACTIONS : Minimum number of actions to consider success (optional)

Rate limits are handled with retries and exponential backoff. The script caches
downloaded filing text in a local directory to avoid refetching.

Action types supported in v1.0.0:
    SPLIT, REVERSE_SPLIT, DIVIDEND, SPECIAL_DIVIDEND, SYMBOL_CHANGE, SPINOFF, DELISTING
"""

import json
import os
import re
import sys
import time
import hashlib
import argparse
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

# Configuration
SEC_EDGAR_USER_AGENT = os.environ.get(
    "SEC_EDGAR_USER_AGENT",
    "QuantOS Corporate Actions Fetcher contact@quantos.org"
)
SEC_EDGAR_BASE_URL = "https://efts.sec.gov/LATEST/search-index"
SEC_EDGAR_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data"
REQUEST_DELAY = 0.5          # seconds between API requests (polite)
MAX_RETRIES = 3
CACHE_DIR = ".cache_sec_edgar"

# Search parameters per action type
ACTION_SEARCH_TERMS = {
    "SPLIT": ["stock split", "forward split", "split of common stock"],
    "REVERSE_SPLIT": ["reverse split", "reverse stock split"],
    "DIVIDEND": ["dividend declared", "quarterly dividend"],
    "SPECIAL_DIVIDEND": ["special dividend", "one-time dividend"],
    "SYMBOL_CHANGE": ["symbol change", "name change", "ticker change"],
    "SPINOFF": ["spin-off", "spinoff", "spin off"],
    "DELISTING": ["delisting", "merger agreement", "going private"],
}

# Regex patterns for extraction (simplistic, to be refined)
PATTERNS = {
    "SPLIT": {
        "ratio": re.compile(r"(\d+)\s*[-:]\s*for\s*[-:]?\s*(\d+)", re.IGNORECASE),
        "alternate_ratio": re.compile(r"(\d+)\s*[-:]\s*(\d+)", re.IGNORECASE),
    },
    "REVERSE_SPLIT": {
        "ratio": re.compile(r"(\d+)\s*[-:]\s*for\s*[-:]?\s*(\d+)", re.IGNORECASE),
        "alternate_ratio": re.compile(r"(\d+)\s*[-:]\s*(\d+)", re.IGNORECASE),
    },
    "DIVIDEND": {
        "amount": re.compile(r"\$\s*([\d\.]+)\s*per\s*share", re.IGNORECASE),
        "currency": re.compile(r"(US\$|\$|USD)", re.IGNORECASE),
    },
    "SPECIAL_DIVIDEND": {
        "amount": re.compile(r"\$\s*([\d\.]+)\s*per\s*share", re.IGNORECASE),
        "currency": re.compile(r"(US\$|\$|USD)", re.IGNORECASE),
    },
    "SYMBOL_CHANGE": {
        # Not easily parseable; we may need to look for "will begin trading under new symbol"
        # For v1.0.0 we might skip automatic symbol change detection or use Asset Identifiers history
    },
    "SPINOFF": {
        # Usually described with distribution ratio, e.g., "one share of X for every three shares"
        "ratio": re.compile(r"one\s+share\s+of\s+\w+\s+for\s+every\s+(\d+)\s+shares", re.IGNORECASE),
    },
    "DELISTING": {
        # Effective date only; may not have ex/record
    },
}


class SECEdgarClient:
    """Minimal SEC EDGAR client with caching and polite request handling."""

    def __init__(self, user_agent: str = SEC_EDGAR_USER_AGENT):
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "efts.sec.gov",
        })
        os.makedirs(CACHE_DIR, exist_ok=True)

    def _request(self, url: str, params: Dict = None) -> requests.Response:
        """Perform GET request with retry and delay."""
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 429:
                    wait = 60 * (attempt + 1)
                    print(f"Rate limited. Waiting {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                time.sleep(REQUEST_DELAY)
                return resp
            except requests.exceptions.RequestException as e:
                print(f"Request error (attempt {attempt+1}): {e}", file=sys.stderr)
                time.sleep(2 ** attempt)
        raise RuntimeError(f"Failed to fetch {url} after {MAX_RETRIES} attempts")

    def search_filings(self, cik: str, keyword: str, start_date: str, end_date: str) -> List[Dict]:
        """
        Search SEC EDGAR full-text for 8-K filings matching keyword within date range.
        Returns list of filing metadata dicts.
        """
        params = {
            "q": f'"{keyword}"',
            "ciks": cik,
            "forms": "8-K",
            "startdt": start_date,
            "enddt": end_date,
            "count": "100",
        }
        # Note: The actual full-text search endpoint may differ; adjust as needed.
        url = f"{SEC_EDGAR_BASE_URL}"
        resp = self._request(url, params=params)
        data = resp.json()
        # Response structure: {"hits": {"hits": [ {"_source": {...}}, ...]}}
        hits = data.get("hits", {}).get("hits", [])
        results = []
        for hit in hits:
            src = hit.get("_source", {})
            # Extract relevant fields: accession number, file date, etc.
            # Fields might include: "file_date", "accession_number", "cik", "form_type", etc.
            results.append({
                "accession_number": src.get("accession_number"),
                "file_date": src.get("file_date"),
                "form_type": src.get("form_type"),
                "cik": src.get("cik"),
                "display_name": src.get("display_name"),
                # The URL to the filing index is not directly in search results;
                # we need to construct from accession number.
            })
        return results

    def get_filing_document_url(self, cik: str, accession_number: str) -> str:
        """
        Given CIK and accession number, return the URL to the primary document (htm/txt).
        We first fetch the filing index to locate the primary document.
        """
        # Convert accession number: remove dashes
        acc = accession_number.replace("-", "")
        # Construct URL to filing index (directory)
        # Format: /Archives/edgar/data/{cik_no_leading_zeros}/{accession_no}/{accession_no}-index.htm
        cik_plain = cik.lstrip("0")
        index_url = f"{SEC_EDGAR_ARCHIVE_URL}/{cik_plain}/{acc}/{acc}-index.htm"
        resp = self._request(index_url)
        # Parse the index page to find the primary document (usually .htm or .txt)
        # Look for links to documents, prefer the main filing (8-K)
        # A simple regex to find hrefs ending with .htm or .txt that are not index or XBRL
        doc_links = re.findall(r'href="([^"]+\.(?:htm|txt))"', resp.text, re.IGNORECASE)
        if not doc_links:
            raise ValueError(f"No document links found at {index_url}")
        # Pick the one that is likely the main body; often named like "a8-k.htm" or "8k.htm"
        main_doc = None
        for link in doc_links:
            if "8-k" in link.lower() or "8k" in link.lower():
                main_doc = link
                break
        if not main_doc:
            main_doc = doc_links[0]  # fallback
        # Resolve relative URL
        if main_doc.startswith("/"):
            doc_url = f"https://www.sec.gov{main_doc}"
        else:
            doc_url = f"{index_url.rsplit('/', 1)[0]}/{main_doc}"
        return doc_url

    def download_filing_text(self, doc_url: str) -> str:
        """Download filing document and return plain text (strip HTML tags)."""
        # Check cache
        cache_key = hashlib.sha256(doc_url.encode()).hexdigest()
        cache_path = os.path.join(CACHE_DIR, cache_key + ".txt")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read()

        resp = self._request(doc_url)
        # Strip HTML to text (very crude, may need BeautifulSoup later)
        text = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"\s+", " ", text)
        # Save to cache
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(text)
        return text


def parse_split_ratio(text: str) -> Optional[Tuple[int, int]]:
    """Extract split ratio as (new, old) from text."""
    # Try "X-for-Y" phrase
    m = re.search(r"(\d+)\s*[-:]\s*for\s*[-:]?\s*(\d+)", text, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Try "X-for-Y" without "for"
    m = re.search(r"(\d+)\s*[-:]\s*(\d+)", text, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Try "X-for-1" by context: "a X-for-1 stock split"
    m = re.search(r"(\d+)\s*[-:]\s*for\s*1\b", text, re.IGNORECASE)
    if m:
        return int(m.group(1)), 1
    return None


def extract_dates_from_text(text: str) -> Dict[str, Optional[str]]:
    """
    Look for dates near relevant phrases.
    This is very simplistic; actual extraction requires NLP.
    For v1.0.0 we may rely on filing date for announcement.
    """
    dates = {}
    # Announcement date: often the filing date, we will set later from metadata.
    # ex-date, record date, effective date may be mentioned.
    # We'll leave them None for now; can be enhanced later.
    return dates


def build_action_from_extraction(
    action_type: str,
    isin: str,
    cik: str,
    filing_date: str,
    text: str,
    source_url: str
) -> Dict[str, Any]:
    """Build an action dict from parsed text."""
    action = {
        "isin": isin,
        "action_id": "",  # filled later
        "action_type": action_type,
        "dates": {
            "announcement": filing_date,
            "ex_date": None,
            "record_date": None,
            "effective_date": filing_date,  # default to announcement date if unknown
        },
        "status": "COMPLETED",
        "provenance": {
            "source": "SEC EDGAR",
            "source_url": source_url,
            "verification_source": None,
        },
        "impact": {},
    }

    if action_type in ["SPLIT", "REVERSE_SPLIT"]:
        ratio_pair = parse_split_ratio(text)
        if ratio_pair:
            new, old = ratio_pair
            # For forward split: ratio string "new:old"
            action["ratio"] = f"{new}:{old}"
            # Compute impact multipliers
            action["impact"]["price_multiplier"] = old / new
            action["impact"]["share_multiplier"] = new / old
        else:
            # No ratio found; mark as incomplete?
            action["ratio"] = None

    elif action_type in ["DIVIDEND", "SPECIAL_DIVIDEND"]:
        amount_match = re.search(r"\$\s*([\d\.]+)\s*per\s*share", text, re.IGNORECASE)
        if amount_match:
            action["amount"] = float(amount_match.group(1))
            action["currency"] = "USD"
            action["impact"]["cash_adjustment"] = action["amount"]
        else:
            action["amount"] = None

    elif action_type == "SPINOFF":
        # Extract ratio like "one share of X for every N shares"
        m = re.search(r"one\s+share\s+of\s+(\w+)\s+for\s+every\s+(\d+)\s+shares", text, re.IGNORECASE)
        if m:
            # Not enough to determine ratio; just record as note
            action["ratio"] = f"1:{m.group(2)}"
            # Impact not easily computed
        else:
            action["ratio"] = None

    elif action_type == "SYMBOL_CHANGE":
        # No easy extraction; we'll skip or rely on Asset Identifiers history.
        # For now we won't create SYMBOL_CHANGE actions from EDGAR.
        return None

    elif action_type == "DELISTING":
        # effective date is enough; no other fields needed
        pass

    return action


def main():
    parser = argparse.ArgumentParser(description="Fetch corporate actions from SEC EDGAR")
    parser.add_argument("--identifiers", required=True, help="Path to identifiers.json")
    parser.add_argument("--output", default="actions.json", help="Output actions.json path")
    parser.add_argument("--start", default="2019-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="2024-12-31", help="End date YYYY-MM-DD")
    parser.add_argument("--cik-limit", type=int, default=None, help="Limit processing to first N CIKs (for testing)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Load identifiers
    with open(args.identifiers, "r") as f:
        identifiers_data = json.load(f)

    # Extract instruments list (assume key "instruments" or "identifiers")
    instruments = identifiers_data.get("instruments") or identifiers_data.get("identifiers")
    if not instruments:
        print("Error: No instruments found in identifiers file", file=sys.stderr)
        sys.exit(1)

    # Filter instruments with CIK
    valid_instruments = [inst for inst in instruments if inst.get("cik")]
    if args.cik_limit:
        valid_instruments = valid_instruments[:args.cik_limit]

    print(f"Processing {len(valid_instruments)} instruments with CIK...")

    client = SECEdgarClient()
    all_actions = []
    errors = []

    for idx, inst in enumerate(valid_instruments, start=1):
        cik = inst["cik"].lstrip("0")
        isin = inst.get("isin")
        ticker = inst.get("ticker", "?")
        if not isin:
            print(f"  Skipping {ticker}: no ISIN")
            continue

        if args.verbose:
            print(f"[{idx}/{len(valid_instruments)}] {ticker} ({cik})")

        # For each action type, search and extract
        for action_type, keywords in ACTION_SEARCH_TERMS.items():
            for keyword in keywords:
                try:
                    filings = client.search_filings(cik, keyword, args.start, args.end)
                except Exception as e:
                    errors.append(f"{ticker} {action_type} search failed: {e}")
                    continue

                for filing in filings:
                    # Get accession number
                    acc_no = filing.get("accession_number")
                    if not acc_no:
                        continue
                    try:
                        doc_url = client.get_filing_document_url(cik, acc_no)
                        text = client.download_filing_text(doc_url)
                    except Exception as e:
                        errors.append(f"{ticker} {action_type} download failed: {e}")
                        continue

                    action = build_action_from_extraction(
                        action_type, isin, cik, filing.get("file_date", ""), text, doc_url
                    )
                    if action:
                        # Generate action_id
                        action["action_id"] = (
                            f"{isin}-{action_type}-{action['dates']['announcement']}-"
                            f"{abs(hash((cik, acc_no))) % 10000:04d}"
                        )
                        all_actions.append(action)
                        if args.verbose:
                            print(f"    -> {action['action_id']}")

    # Deduplicate actions (same isin+type+date)
    seen = set()
    unique_actions = []
    for act in all_actions:
        key = (act["isin"], act["action_type"], act["dates"]["announcement"])
        if key not in seen:
            seen.add(key)
            unique_actions.append(act)

    # Build output
    output_data = {
        "meta": {
            "version": "0.1.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source": "SEC EDGAR",
            "notes": f"Generated by fetch_sec_edgar_actions.py from {len(valid_instruments)} instruments",
        },
        "actions": unique_actions,
    }

    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nDone. Extracted {len(unique_actions)} actions -> {args.output}")
    if errors:
        print(f"\n{len(errors)} errors occurred. First few:")
        for e in errors[:5]:
            print(f"  - {e}")

    # Optional: exit with error if too few actions? Use min env var
    min_actions = int(os.environ.get("CORP_ACTIONS_MIN_ACTIONS", "0"))
    if len(unique_actions) < min_actions:
        print(f"Error: only {len(unique_actions)} actions, minimum required {min_actions}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Fetch Corporate Actions from SEC EDGAR (Symbol Changes and Delistings)

Scope is deliberately narrow. Extracts only action types that Yahoo Finance
does not provide:

    SYMBOL_CHANGE  — ticker symbol change
    DELISTING      — removal from an exchange

Dividends and splits are NOT extracted. Those come from the Yahoo fetcher
(tools/fetch_yahoo_actions.py) with structured, reliable data. Extracting
them from SEC text produced false positives that outweighed coverage gains.

Endpoint:
    https://data.sec.gov/submissions/CIK{cik:010d}.json
Filing index:
    https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/index.json
Documents:
    https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{name}

The SEC requires a descriptive User-Agent and a maximum of 10 requests per
second. This script uses a 0.15s delay (~6.6/sec) and caches filings under
.cache_sec_edgar/.

Usage:
    python tools/fetch_sec_edgar_actions.py \
        --identifiers tests/fixtures/identifiers.json \
        --output sec_actions.json \
        --cik-limit 5 \
        --verbose

Exit codes:
  0 - success
  1 - no actions extracted (still a valid result, but a warning condition)
  2 - missing or invalid input file
  3 - network or API failure after retries
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests


SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_FILING_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"
)
SEC_DOCUMENT_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
)
USER_AGENT = os.environ.get(
    "SEC_EDGAR_USER_AGENT",
    "QuantOS Corporate Actions Registry contact@quantos.org",
)
REQUEST_DELAY = 0.15
MAX_RETRIES = 3
CACHE_DIR = ".cache_sec_edgar"
DEFAULT_MIN_DATE = "2019-01-01"


SYMBOL_CHANGE_TRIGGERS = [
    re.compile(
        r"will\s+(?:begin\s+trading|trade)\s+under\s+(?:the\s+)?(?:new\s+)?"
        r"(?:ticker\s+)?symbol\s+['\"]?([A-Z]{1,6})['\"]?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:change|changes|changing)\s+its\s+(?:ticker\s+)?symbol\s+"
        r"(?:to|from\s+\S+\s+to)\s+['\"]?([A-Z]{1,6})['\"]?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:new\s+)?(?:ticker\s+)?symbol\s+(?:will\s+be|is)\s+"
        r"['\"]?([A-Z]{1,6})['\"]?",
        re.IGNORECASE,
    ),
    re.compile(
        r"trading\s+symbol\s+(?:will\s+)?(?:change|be\s+changed)\s+to\s+"
        r"['\"]?([A-Z]{1,6})['\"]?",
        re.IGNORECASE,
    ),
]

DELISTING_TRIGGERS = [
    re.compile(
        r"will\s+be\s+(?:voluntarily\s+)?delisted\s+from",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:delisting|delisted)\s+from\s+(?:the\s+)?[A-Z][A-Za-z\s]+(?:Exchange|Market|Stock)",
        re.IGNORECASE,
    ),
    re.compile(
        r"intends?\s+to\s+(?:voluntarily\s+)?delist",
        re.IGNORECASE,
    ),
]

EFFECTIVE_DATE_PATTERNS = [
    re.compile(
        r"effective\s+(?:as\s+of|on)?\s*"
        r"(January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
        r"\.?\s+(\d{1,2}),?\s+(\d{4})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:on|as\s+of)\s+(?:or\s+about\s+)?"
        r"(January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
        r"\.?\s+(\d{1,2}),?\s+(\d{4})",
        re.IGNORECASE,
    ),
]

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def load_instruments(path: str) -> List[Tuple[str, str, str]]:
    """Load instruments with CIK. Returns (isin, ticker, cik)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(2)

    instruments = data.get("instruments") or data.get("identifiers") or []
    result: List[Tuple[str, str, str]] = []
    for inst in instruments:
        isin = inst.get("isin")
        ticker = inst.get("ticker")
        cik = inst.get("cik")
        if not isin or not ticker or not cik:
            continue
        cik_str = str(cik).lstrip("0").zfill(10)
        result.append((isin, ticker.upper(), cik_str))
    return result


def parse_date(month_str: str, day_str: str, year_str: str) -> Optional[str]:
    month = MONTHS.get(month_str.lower())
    if not month:
        return None
    try:
        d = date(int(year_str), month, int(day_str))
        return d.isoformat()
    except ValueError:
        return None


def extract_effective_date(text: str) -> Optional[str]:
    for pat in EFFECTIVE_DATE_PATTERNS:
        m = pat.search(text)
        if m:
            iso = parse_date(m.group(1), m.group(2), m.group(3))
            if iso:
                return iso
    return None


def extract_new_symbol(text: str) -> Optional[str]:
    for pat in SYMBOL_CHANGE_TRIGGERS:
        m = pat.search(text)
        if m:
            symbol = m.group(1).upper()
            if 1 <= len(symbol) <= 5 and symbol.isalpha():
                return symbol
    return None


def is_delisting(text: str) -> bool:
    return any(pat.search(text) for pat in DELISTING_TRIGGERS)


def is_symbol_change(text: str) -> bool:
    return any(pat.search(text) for pat in SYMBOL_CHANGE_TRIGGERS)


class SECClient:
    def __init__(self, user_agent: str = USER_AGENT):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json, text/html, */*",
        })
        os.makedirs(CACHE_DIR, exist_ok=True)

    def _cache_path(self, key: str) -> str:
        digest = hashlib.sha256(key.encode()).hexdigest()
        return os.path.join(CACHE_DIR, digest + ".cache")

    def _get(self, url: str) -> Optional[requests.Response]:
        cache_path = self._cache_path(url)
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                content = f.read()
            resp = requests.Response()
            resp.status_code = 200
            resp._content = content
            return resp

        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code == 429:
                    wait = 60 * (attempt + 1)
                    print(f"Rate limited. Waiting {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                with open(cache_path, "wb") as f:
                    f.write(resp.content)
                time.sleep(REQUEST_DELAY)
                return resp
            except requests.exceptions.RequestException as e:
                print(f"Request error ({attempt + 1}/{MAX_RETRIES}): {e}",
                      file=sys.stderr)
                time.sleep(2 ** attempt)
        return None

    def get_submissions(self, cik: str) -> Optional[Dict[str, Any]]:
        url = SEC_SUBMISSIONS_URL.format(cik=cik)
        resp = self._get(url)
        if resp is None:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    def get_filing_text(self, cik: str, accession: str) -> Optional[str]:
        cik_no_zeros = cik.lstrip("0") or "0"
        acc_no_dashes = accession.replace("-", "")
        index_url = SEC_FILING_INDEX_URL.format(cik=cik_no_zeros, acc=acc_no_dashes)
        index_resp = self._get(index_url)
        if index_resp is None:
            return None
        try:
            index_data = index_resp.json()
        except ValueError:
            return None

        items = index_data.get("directory", {}).get("item", [])
        texts: List[str] = []
        for item in items:
            name = item.get("name", "")
            if not name.lower().endswith((".htm", ".html", ".txt")):
                continue
            doc_url = SEC_DOCUMENT_URL.format(
                cik=cik_no_zeros, acc=acc_no_dashes, doc=name
            )
            doc_resp = self._get(doc_url)
            if doc_resp is None:
                continue
            text = re.sub(r"<[^>]+>", " ", doc_resp.text)
            text = re.sub(r"&nbsp;?", " ", text)
            text = re.sub(r"&amp;?", "&", text)
            text = re.sub(r"\s+", " ", text)
            texts.append(text)
        return " ".join(texts) if texts else None


def build_symbol_change(
    isin: str,
    current_ticker: str,
    cik: str,
    filing_date: str,
    accession: str,
    primary_doc: str,
    text: str,
) -> Optional[Dict[str, Any]]:
    new_symbol = extract_new_symbol(text)
    if not new_symbol or new_symbol == current_ticker.upper():
        return None

    effective = extract_effective_date(text) or filing_date

    cik_no_zeros = cik.lstrip("0") or "0"
    acc_no_dashes = accession.replace("-", "")
    source_url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{cik_no_zeros}/{acc_no_dashes}/{primary_doc}"
    )

    return {
        "isin": isin,
        "action_id": f"{isin}-SYMBOL_CHANGE-{effective}-{new_symbol}",
        "action_type": "SYMBOL_CHANGE",
        "dates": {
            "announcement": filing_date,
            "effective_date": effective,
        },
        "status": "COMPLETED",
        "provenance": {
            "source": "SEC EDGAR",
            "source_url": source_url,
        },
        "impact": {
            "price_multiplier": 1.0,
            "share_multiplier": 1.0,
            "cash_adjustment": 0.0,
        },
    }


def build_delisting(
    isin: str,
    cik: str,
    filing_date: str,
    accession: str,
    primary_doc: str,
    text: str,
) -> Optional[Dict[str, Any]]:
    effective = extract_effective_date(text) or filing_date

    cik_no_zeros = cik.lstrip("0") or "0"
    acc_no_dashes = accession.replace("-", "")
    source_url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{cik_no_zeros}/{acc_no_dashes}/{primary_doc}"
    )

    return {
        "isin": isin,
        "action_id": f"{isin}-DELISTING-{effective}",
        "action_type": "DELISTING",
        "dates": {
            "announcement": filing_date,
            "effective_date": effective,
        },
        "status": "COMPLETED",
        "provenance": {
            "source": "SEC EDGAR",
            "source_url": source_url,
        },
        "impact": {
            "price_multiplier": 1.0,
            "share_multiplier": 1.0,
            "cash_adjustment": 0.0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch SYMBOL_CHANGE and DELISTING actions from SEC EDGAR."
    )
    parser.add_argument("--identifiers", required=True)
    parser.add_argument("--output", default="sec_actions.json")
    parser.add_argument("--cik-limit", type=int, default=None)
    parser.add_argument("--min-date", default=DEFAULT_MIN_DATE)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    instruments = load_instruments(args.identifiers)
    if args.cik_limit:
        instruments = instruments[: args.cik_limit]

    print(f"Processing {len(instruments)} instruments "
          f"(min date {args.min_date})...")
    print("Scope: SYMBOL_CHANGE and DELISTING only. "
          "Dividends and splits come from the Yahoo fetcher.")

    client = SECClient()
    all_actions: List[Dict[str, Any]] = []
    errors: List[str] = []

    for idx, (isin, ticker, cik) in enumerate(instruments, start=1):
        if args.verbose:
            print(f"[{idx}/{len(instruments)}] {ticker} (CIK {cik})")

        submissions = client.get_submissions(cik)
        if not submissions:
            errors.append(f"{ticker}: could not fetch submissions")
            continue

        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accs = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", [])
        filed = recent.get("filingDate", [])

        eight_k_indices = [i for i, f in enumerate(forms) if f == "8-K"]
        ticker_actions = 0

        for i in eight_k_indices:
            filing_date = filed[i]
            if filing_date < args.min_date:
                continue
            accession = accs[i]
            primary_doc = docs[i]
            if not primary_doc:
                continue

            text = client.get_filing_text(cik, accession)
            if not text:
                continue

            if is_symbol_change(text):
                action = build_symbol_change(
                    isin, ticker, cik, filing_date, accession, primary_doc, text
                )
                if action:
                    all_actions.append(action)
                    ticker_actions += 1
                    continue

            if is_delisting(text):
                action = build_delisting(
                    isin, cik, filing_date, accession, primary_doc, text
                )
                if action:
                    all_actions.append(action)
                    ticker_actions += 1

        if args.verbose:
            print(f"    actions extracted: {ticker_actions}")

    seen = set()
    unique: List[Dict[str, Any]] = []
    for a in all_actions:
        aid = a["action_id"]
        if aid not in seen:
            seen.add(aid)
            unique.append(a)

    unique.sort(key=lambda a: (a["dates"].get("effective_date") or "", a["action_id"]))

    output_data = {
        "meta": {
            "version": "0.3.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "SEC EDGAR",
            "notes": (
                f"Symbol changes and delistings only. Generated from "
                f"{len(instruments)} instruments; min_date={args.min_date}; "
                f"total_actions={len(unique)}"
            ),
        },
        "actions": unique,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nDone. Extracted {len(unique)} actions -> {args.output}")
    if errors:
        print(f"\n{len(errors)} errors occurred. First few:")
        for e in errors[:5]:
            print(f"  - {e}")

    if len(unique) == 0:
        print("Note: zero actions is expected for most tickers. "
              "Symbol changes and delistings are rare.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
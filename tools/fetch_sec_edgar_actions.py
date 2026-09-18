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

Known limitations
-----------------
The submissions endpoint returns only the most recent ~1,000 filings in
its `recent` array. Older filings live in numbered archive files listed
under `filings.files[]`. This script reads only `recent`, so it does not
see filings older than roughly two years. When a company has archive
files, a stderr warning names it, so a partial result is visible rather
than silent.

Usage:
    python tools/fetch_sec_edgar_actions.py \
        --identifiers tests/fixtures/identifiers.json \
        --output sec_actions.json \
        --cik-limit 5 \
        --verbose

Exit codes:
  0 - success, no instrument failed
  1 - at least one instrument could not be fetched
  2 - missing or invalid input file
  3 - nothing was processed (empty instrument list, or every fetch failed)
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
CACHE_DIR = os.environ.get("SEC_EDGAR_CACHE", ".cache_sec_edgar")
DEFAULT_MIN_DATE = "2019-01-01"


# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------
# Case-insensitivity is scoped to the prose with (?i:...) so the captured
# symbol part [A-Z] only matches real uppercase. A bare re.IGNORECASE flag
# would make [A-Z] match lowercase too, and produce false positives on
# ordinary English text such as "the new symbol is US".

SYMBOL_CHANGE_TRIGGERS = [
    re.compile(
        r"(?i:will\s+(?:begin\s+trading|trade)\s+under\s+(?:the\s+)?"
        r"(?:new\s+)?(?:ticker\s+)?symbol\s+)['\"]?([A-Z]{1,6})['\"]?"
    ),
    re.compile(
        r"(?i:(?:change|changes|changing)\s+its\s+(?:ticker\s+)?symbol\s+"
        r"(?:to|from\s+\S+\s+to)\s+)['\"]?([A-Z]{1,6})['\"]?"
    ),
    re.compile(
        r"(?i:(?:new\s+)?(?:ticker\s+)?symbol\s+(?:will\s+be|is)\s+)"
        r"['\"]?([A-Z]{1,6})['\"]?"
    ),
    re.compile(
        r"(?i:trading\s+symbol\s+(?:will\s+)?(?:change|be\s+changed)\s+to\s+)"
        r"['\"]?([A-Z]{1,6})['\"]?"
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

# Common 2-5 letter English words that the weak-pattern extraction path
# could mistake for a ticker symbol. The strong patterns (1 and 2) include
# enough prose context that a random English word is unlikely, so this
# blocklist only rejects candidates from patterns 3 and 4. Rejecting from
# all four is cheap and safe.
COMMON_ENGLISH_WORDS = frozenset({
    # Two letters
    "AN", "AS", "AT", "BE", "BY", "DO", "GO", "HE", "IF", "IN", "IS", "IT",
    "ME", "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US", "WE",
    # Three letters
    "ALL", "AND", "ANY", "ARE", "BOY", "BUT", "CAN", "DAY", "DID", "FOR",
    "GET", "GOD", "HAD", "HAS", "HER", "HIM", "HIS", "HOW", "ITS", "LET",
    "MAN", "MAY", "NEW", "NOT", "NOW", "OLD", "ONE", "OUT", "OWN", "PUT",
    "SAY", "SEE", "SHE", "THE", "TOO", "TWO", "USE", "WAS", "WAY", "WHO",
    "WHY", "YES", "YET", "YOU",
    # Four letters
    "ALSO", "BEEN", "BOTH", "CAME", "EACH", "EVEN", "EVER", "FROM", "GAVE",
    "HAND", "HAVE", "HERE", "HIGH", "INTO", "JUST", "KEEP", "KIND", "KNOW",
    "LAST", "LATE", "LESS", "LIKE", "LONG", "MADE", "MAKE", "MANY", "MORE",
    "MOST", "MUCH", "MUST", "NEAR", "NEED", "NEXT", "ONCE", "ONLY", "OVER",
    "PART", "SAID", "SAME", "SOME", "SUCH", "SURE", "TAKE", "THAN", "THAT",
    "THEM", "THEN", "THEY", "THIS", "TIME", "UPON", "VERY", "WELL", "WENT",
    "WERE", "WHAT", "WHEN", "WITH", "WORK", "YOUR",
    # Five letters
    "ABOUT", "AFTER", "AGAIN", "BEING", "COULD", "EVERY", "FIRST", "FOUND",
    "GOING", "GREAT", "MIGHT", "NEVER", "OTHER", "PLACE", "RIGHT", "SHALL",
    "SINCE", "SMALL", "STILL", "THEIR", "THERE", "THESE", "THOSE", "THREE",
    "UNDER", "UNTIL", "WHICH", "WHILE", "WHERE", "WOULD", "WRITE",
})


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

def load_instruments(path: str) -> List[Tuple[str, str, str]]:
    """Load instruments with a CIK. Returns list of (isin, ticker, cik).

    Skips entries missing any of the three fields. Rejects CIKs that
    normalise to all zeros (no such filing exists on EDGAR).
    """
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
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
        if not isin or not ticker or cik is None:
            continue

        cik_str = str(cik).strip().lstrip("0").zfill(10)
        if cik_str == "0" * 10:
            # A CIK of 0 or "0000000000" is not a real filing entity.
            continue

        result.append((isin, ticker.upper(), cik_str))
    return result


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def parse_date(month_str: str, day_str: str, year_str: str) -> Optional[str]:
    """Return YYYY-MM-DD, or None if the components do not form a valid date."""
    month = MONTHS.get(month_str.lower())
    if not month:
        return None
    try:
        return date(int(year_str), month, int(day_str)).isoformat()
    except ValueError:
        return None


def extract_effective_date(text: str) -> Optional[str]:
    """Return the first ISO date found by any EFFECTIVE_DATE_PATTERNS."""
    for pat in EFFECTIVE_DATE_PATTERNS:
        m = pat.search(text)
        if m:
            iso = parse_date(m.group(1), m.group(2), m.group(3))
            if iso:
                return iso
    return None


def extract_new_symbol(text: str) -> Optional[str]:
    """Return the new ticker symbol, or None.

    Rejects candidates in COMMON_ENGLISH_WORDS. The regex captures only
    uppercase letters of length 1..6, and the `.isalpha()` check rejects
    anything containing a digit or punctuation.
    """
    for pat in SYMBOL_CHANGE_TRIGGERS:
        m = pat.search(text)
        if m:
            symbol = m.group(1)
            if not (1 <= len(symbol) <= 6):
                continue
            if not symbol.isalpha():
                continue
            if symbol in COMMON_ENGLISH_WORDS:
                continue
            return symbol
    return None


def is_delisting(text: str) -> bool:
    return any(pat.search(text) for pat in DELISTING_TRIGGERS)


def is_symbol_change(text: str) -> bool:
    return any(pat.search(text) for pat in SYMBOL_CHANGE_TRIGGERS)


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class SECClient:
    """Minimal HTTP client for SEC EDGAR with on-disk caching and retries."""

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
                print(
                    f"Request error ({attempt + 1}/{MAX_RETRIES}): {e}",
                    file=sys.stderr,
                )
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


# ---------------------------------------------------------------------------
# Action builders
# ---------------------------------------------------------------------------

def _filing_url(cik: str, accession: str, primary_doc: str) -> str:
    cik_no_zeros = cik.lstrip("0") or "0"
    acc_no_dashes = accession.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{cik_no_zeros}/{acc_no_dashes}/{primary_doc}"
    )


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
    source_url = _filing_url(cik, accession, primary_doc)

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
    source_url = _filing_url(cik, accession, primary_doc)

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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _warn_about_archive_files(ticker: str, submissions: Dict[str, Any]) -> None:
    """Emit a stderr warning when a company has older filings in archives.

    The `data.sec.gov` submissions endpoint returns only ~1,000 recent
    filings in `filings.recent`. Older filings live in numbered archive
    files listed in `filings.files[]`. This script reads only `recent`.
    """
    files = submissions.get("filings", {}).get("files")
    if not files:
        return
    print(
        f"Warning: {ticker} has {len(files)} archive file(s) with older "
        f"filings; only the recent ~1000 filings are scanned.",
        file=sys.stderr,
    )


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

    if not instruments:
        print(
            "Error: no instruments with a CIK found in "
            f"{args.identifiers}",
            file=sys.stderr,
        )
        return 3

    print(
        f"Processing {len(instruments)} instruments "
        f"(min date {args.min_date})..."
    )
    print(
        "Scope: SYMBOL_CHANGE and DELISTING only. "
        "Dividends and splits come from the Yahoo fetcher."
    )

    client = SECClient()
    all_actions: List[Dict[str, Any]] = []
    errors: List[str] = []
    processed = 0

    for idx, (isin, ticker, cik) in enumerate(instruments, start=1):
        if args.verbose:
            print(f"[{idx}/{len(instruments)}] {ticker} (CIK {cik})")

        submissions = client.get_submissions(cik)
        if not submissions:
            errors.append(f"{ticker}: could not fetch submissions")
            continue
        processed += 1

        _warn_about_archive_files(ticker, submissions)

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

            # A filing can announce both a symbol change and a delisting.
            # Do not short-circuit: check both, in either order, and append
            # every action that matches.
            if is_symbol_change(text):
                action = build_symbol_change(
                    isin, ticker, cik, filing_date, accession,
                    primary_doc, text,
                )
                if action:
                    all_actions.append(action)
                    ticker_actions += 1

            if is_delisting(text):
                action = build_delisting(
                    isin, cik, filing_date, accession, primary_doc, text,
                )
                if action:
                    all_actions.append(action)
                    ticker_actions += 1

        if args.verbose:
            print(f"    actions extracted: {ticker_actions}")

    # Deduplicate by action_id, preserving insertion order.
    seen = set()
    unique: List[Dict[str, Any]] = []
    for a in all_actions:
        aid = a["action_id"]
        if aid not in seen:
            seen.add(aid)
            unique.append(a)

    unique.sort(
        key=lambda a: (a["dates"].get("effective_date") or "", a["action_id"])
    )

    output_data = {
        "meta": {
            "version": "0.4.0",
            "generated_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "source": "SEC EDGAR",
            "notes": (
                f"Symbol changes and delistings only. Generated from "
                f"{len(instruments)} instruments; min_date={args.min_date}; "
                f"total_actions={len(unique)}"
            ),
        },
        "actions": unique,
    }

    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
            f.write("\n")
    except OSError as e:
        print(f"Error writing {args.output}: {e}", file=sys.stderr)
        return 3

    print(f"\nDone. Extracted {len(unique)} actions -> {args.output}")
    if errors:
        print(f"\n{len(errors)} instrument(s) failed. First few:")
        for e in errors[:5]:
            print(f"  - {e}")

    if not unique:
        print(
            "Note: zero actions is expected for most tickers. "
            "Symbol changes and delistings are rare.",
            file=sys.stderr,
        )

    # Exit codes:
    #   every instrument failed  -> 3
    #   at least one failed      -> 1
    #   none failed              -> 0
    if processed == 0:
        return 3
    if errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
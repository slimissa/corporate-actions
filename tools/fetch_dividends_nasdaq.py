#!/usr/bin/env python3
"""
Fetch Dividend Actions from Nasdaq API

Reads Asset Identifiers registry (identifiers.json) and for each instrument
with a US ticker, queries Nasdaq's dividend history endpoint. It then builds
corporate action entries of type DIVIDEND (or SPECIAL_DIVIDEND if a "special"
flag is detected) and writes them to dividends_actions.json.

Usage:
    python tools/fetch_dividends_nasdaq.py \
        --identifiers ../asset-identifiers/identifiers.json \
        --output dividends_actions.json \
        --start 2019-01-01 --end 2024-12-31

The script respects Nasdaq's rate limits with a delay between requests and
caches responses to avoid refetching. It never overwrites the main
actions.json; it only creates a new file.

Exit codes:
  0 - success
  1 - too few actions extracted (see --min-actions)
  2 - usage error or missing input
  3 - network/API failure after retries
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
NASDAQ_API_BASE = "https://api.nasdaq.com/api/quote"
NASDAQ_DIVIDENDS_PATH = "/dividends"
NASDAQ_ASSET_CLASS = "stocks"
REQUEST_DELAY = 0.6                # seconds between API calls
MAX_RETRIES = 3
CACHE_DIR = ".cache_nasdaq"
USER_AGENT = "QuantOS Corporate Actions Fetcher/1.0 (contact@quantos.org)"

# Minimum number of dividend actions to consider success (set via env)
DEFAULT_MIN_ACTIONS = 0


class NasdaqClient:
    """Minimal Nasdaq API client with caching and polite request handling."""

    def __init__(self, user_agent: str = USER_AGENT):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/",
        })
        os.makedirs(CACHE_DIR, exist_ok=True)

    def _get_cache_path(self, url: str) -> str:
        key = hashlib.sha256(url.encode()).hexdigest()
        return os.path.join(CACHE_DIR, key + ".json")

    def _request(self, url: str) -> Optional[Dict[str, Any]]:
        """GET with retries and caching."""
        cache_path = self._get_cache_path(url)
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)

        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, timeout=15)
                if resp.status_code == 429:
                    wait = 60 * (attempt + 1)
                    print(f"Rate limited. Waiting {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                # Cache successful response
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                time.sleep(REQUEST_DELAY)
                return data
            except requests.exceptions.RequestException as e:
                print(f"Request error (attempt {attempt+1}): {e}", file=sys.stderr)
                time.sleep(2 ** attempt)
        return None

    def get_dividends(self, ticker: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch dividend history for a ticker."""
        url = (f"{NASDAQ_API_BASE}/{ticker}{NASDAQ_DIVIDENDS_PATH}"
               f"?assetclass={NASDAQ_ASSET_CLASS}")
        data = self._request(url)
        if not data:
            return None
        # The response structure may vary; we try common fields.
        # Usually: data.dividends.rows (list) or data.dividends (list)
        div_data = data.get("data", {})
        dividends = None
        if isinstance(div_data, dict):
            dividends = div_data.get("dividends", None)
        if dividends is None and isinstance(data.get("data"), dict):
            # Fallback: look for rows
            dividends = data["data"].get("rows")
        if dividends is None:
            # Sometimes the API returns a list directly under data
            if isinstance(data.get("data"), list):
                dividends = data["data"]
        return dividends if isinstance(dividends, list) else None


def parse_date(date_str: Optional[str]) -> Optional[str]:
    """Convert Nasdaq date strings (e.g., '05/16/2024') to ISO format."""
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def build_dividend_action(
    isin: str,
    ticker: str,
    record: Dict[str, Any],
    source_url: str
) -> Optional[Dict[str, Any]]:
    """
    Convert a Nasdaq dividend record into a corporate action dict.
    Returns None if required fields are missing.
    """
    # Extract dates and amount
    ex_date = parse_date(record.get("exDate") or record.get("ex_date"))
    record_date = parse_date(record.get("recordDate") or record.get("record_date"))
    payment_date = parse_date(record.get("paymentDate") or record.get("payment_date"))
    amount_str = record.get("amount") or record.get("cashAmount") or record.get("dividend")
    if amount_str is None:
        return None
    try:
        amount = float(str(amount_str).replace("$", "").replace(",", ""))
    except ValueError:
        return None
    if amount <= 0:
        return None

    # Announcement date is not provided; set to ex_date to satisfy temporal rules.
    # This is a simplification; if you have an announcement date source, replace this.
    announcement = ex_date

    if not ex_date:
        # Ex-date is essential for backtesting; skip if missing
        return None

    # Determine if special dividend (if flag exists)
    action_type = "DIVIDEND"
    special_flag = record.get("special") or record.get("isSpecial")
    if special_flag:
        action_type = "SPECIAL_DIVIDEND"

    # Build action_id: ISIN-ACTIONTYPE-EFFECTIVE_DATE-UNIQUE
    effective = payment_date or record_date or ex_date
    action_id = f"{isin}-{action_type}-{effective}-{abs(hash((ticker, ex_date, amount))) % 100000:05d}"

    return {
        "isin": isin,
        "action_id": action_id,
        "action_type": action_type,
        "amount": amount,
        "currency": "USD",   # Nasdaq dividends are USD
        "dates": {
            "announcement": announcement,
            "ex_date": ex_date,
            "record_date": record_date,
            "effective_date": effective,
        },
        "status": "COMPLETED",
        "provenance": {
            "source": "Nasdaq",
            "source_url": source_url,
            "verification_source": None,
        },
        "impact": {
            "cash_adjustment": amount,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch dividends from Nasdaq")
    parser.add_argument("--identifiers", required=True, help="Path to identifiers.json")
    parser.add_argument("--output", default="dividends_actions.json", help="Output file")
    parser.add_argument("--start", default="2019-01-01", help="Start date (unused for now)")
    parser.add_argument("--end", default="2024-12-31", help="End date (unused for now)")
    parser.add_argument("--min-actions", type=int, default=DEFAULT_MIN_ACTIONS,
                        help="Minimum number of actions to consider success")
    parser.add_argument("--ticker-limit", type=int, default=None,
                        help="Limit processing to first N tickers (for testing)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Load identifiers
    try:
        with open(args.identifiers, "r") as f:
            id_data = json.load(f)
    except Exception as e:
        print(f"Error loading identifiers: {e}", file=sys.stderr)
        sys.exit(2)

    # Extract instruments list (handles common structures)
    instruments = id_data.get("instruments") or id_data.get("identifiers")
    if not instruments:
        print("Error: no instruments found in identifiers.json", file=sys.stderr)
        sys.exit(2)

    # Filter to instruments with a US ticker and ISIN
    valid_instruments = []
    for inst in instruments:
        isin = inst.get("isin")
        ticker = inst.get("ticker")
        if isin and ticker:
            valid_instruments.append((isin, ticker.upper()))

    if args.ticker_limit:
        valid_instruments = valid_instruments[:args.ticker_limit]

    print(f"Processing {len(valid_instruments)} instruments...")

    client = NasdaqClient()
    all_actions = []
    errors = []

    for idx, (isin, ticker) in enumerate(valid_instruments, start=1):
        if args.verbose:
            print(f"[{idx}/{len(valid_instruments)}] {ticker}")

        dividends = client.get_dividends(ticker)
        if dividends is None:
            errors.append(f"{ticker}: failed to fetch dividends")
            continue

        source_url = f"https://www.nasdaq.com/market-activity/stocks/{ticker.lower()}/dividend-history"

        for record in dividends:
            action = build_dividend_action(isin, ticker, record, source_url)
            if action:
                all_actions.append(action)
                if args.verbose:
                    print(f"    -> {action['action_id']} ({action['amount']})")

    # Deduplicate (same isin+type+ex_date+amount)
    seen = set()
    unique_actions = []
    for act in all_actions:
        key = (act["isin"], act["action_type"], act["dates"]["ex_date"], act["amount"])
        if key not in seen:
            seen.add(key)
            unique_actions.append(act)

    # Write output
    output_data = {
        "meta": {
            "version": "0.1.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source": "Nasdaq",
            "notes": f"Generated by fetch_dividends_nasdaq.py from {len(valid_instruments)} instruments",
        },
        "actions": unique_actions,
    }

    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nDone. Extracted {len(unique_actions)} dividend actions -> {args.output}")
    if errors:
        print(f"\n{len(errors)} errors occurred. First few:")
        for e in errors[:5]:
            print(f"  - {e}")

    if len(unique_actions) < args.min_actions:
        print(f"Error: only {len(unique_actions)} actions, minimum required {args.min_actions}",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
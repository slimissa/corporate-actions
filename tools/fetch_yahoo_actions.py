#!/usr/bin/env python3
"""
Fetch Corporate Actions from Yahoo Finance

Reads Asset Identifiers registry (identifiers.json) and for each instrument
with a ticker, queries Yahoo Finance's chart API for dividend and split events.
It then builds corporate action entries and writes them to yahoo_actions.json.

Usage:
    python tools/fetch_yahoo_actions.py \
        --identifiers ../asset-identifiers/identifiers.json \
        --output yahoo_actions.json \
        --ticker-limit 10 \
        --verbose

The script respects rate limits, caches responses, and never overwrites
actions.json. It only creates a new file.

Exit codes:
  0 - success
  1 - too few actions extracted
  2 - missing input file
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
REQUEST_DELAY = 0.5          # seconds between requests
MAX_RETRIES = 3
CACHE_DIR = ".cache_yahoo"
CACHE_TTL_HOURS = 24        # cache entries older than this will be refreshed
DEFAULT_RANGE = "10y"        # fetch last 10 years of events

# ----------------------------------------------------------------------


def timestamp_to_iso(ts: int) -> str:
    """Convert Unix timestamp (seconds) to ISO date string (YYYY-MM-DD)."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def load_instruments(path: str) -> List[Tuple[str, str, str]]:
    """
    Load instruments from identifiers.json, return list of (isin, ticker, currency).
    Handles common structures: { "instruments": [...] } or { "identifiers": [...] }
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(2)

    instruments = data.get("instruments") or data.get("identifiers")
    if not instruments:
        print("Error: no instruments found", file=sys.stderr)
        sys.exit(2)

    result = []
    for inst in instruments:
        isin = inst.get("isin")
        ticker = inst.get("ticker")
        if isin and ticker:
            # Determine currency: prefer inst['currency'], else infer from listings
            currency = inst.get("currency")
            if not currency:
                # Try to get from listings (if present)
                listings = inst.get("listings")
                if listings and isinstance(listings, list) and listings:
                    # Use the primary listing's currency
                    for listing in listings:
                        if listing.get("status") == "PRIMARY" and listing.get("currency"):
                            currency = listing["currency"]
                            break
                    # fallback to first listing currency
                    if not currency:
                        currency = listings[0].get("currency")
            if not currency:
                currency = "USD"  # default
            result.append((isin, ticker.upper(), currency))
    return result


class YahooClient:
    """Minimal Yahoo Finance client with caching and TTL."""

    def __init__(self, cache_dir: str = CACHE_DIR, cache_ttl_hours: int = CACHE_TTL_HOURS):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.cache_dir = cache_dir
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        os.makedirs(self.cache_dir, exist_ok=True)

    def _cache_path(self, ticker: str) -> str:
        return os.path.join(self.cache_dir, f"{ticker}.json")

    def _is_cache_valid(self, cache_path: str) -> bool:
        """Return True if cache file exists and is younger than TTL."""
        if not os.path.exists(cache_path):
            return False
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_path), tz=timezone.utc)
        return datetime.now(timezone.utc) - mtime < self.cache_ttl

    def fetch_events(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fetch raw events (dividends/splits) from Yahoo, return dict or None."""
        cache_path = self._cache_path(ticker)
        if self._is_cache_valid(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)

        url = f"{YAHOO_CHART_URL}/{ticker}"
        params = {
            "range": DEFAULT_RANGE,
            "interval": "1d",
            "events": "div,splits",
        }
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, params=params, timeout=15)
                if resp.status_code == 429:
                    wait = 60 * (attempt + 1)
                    print(f"Rate limited for {ticker}. Waiting {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                # Save to cache
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                time.sleep(REQUEST_DELAY)
                return data
            except requests.exceptions.RequestException as e:
                print(f"Request error for {ticker} (attempt {attempt+1}): {e}", file=sys.stderr)
                time.sleep(2 ** attempt)
        return None


def make_action_id(isin: str, action_type: str, ex_date: str, extra: str = "") -> str:
    """
    Generate a deterministic, unique action_id.
    Format: ISIN-ACTIONTYPE-EXDATE-EXTRA
    extra is used to distinguish multiple events on the same day.
    """
    base = f"{isin}-{action_type}-{ex_date}"
    if extra:
        return f"{base}-{extra}"
    return base


def extract_actions(isin: str, ticker: str, currency: str, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert Yahoo events to corporate action dicts."""
    actions = []
    try:
        result = raw_data["chart"]["result"][0]
        events = result.get("events", {})
    except (KeyError, IndexError):
        return actions

    # Dividends
    dividends = events.get("dividends", {})
    for ts_str, div in dividends.items():
        ts = int(ts_str)
        ex_date = timestamp_to_iso(div.get("date", ts))
        amount = div.get("amount")
        if amount is None:
            continue

        # Use amount formatted to 4 decimals as extra to ensure uniqueness
        extra = f"{amount:.4f}"
        action_id = make_action_id(isin, "DIVIDEND", ex_date, extra)

        actions.append({
            "isin": isin,
            "action_id": action_id,
            "action_type": "DIVIDEND",
            "amount": amount,
            "currency": currency,
            "dates": {
                "announcement": ex_date,      # approximation; Yahoo lacks announcement date
                "ex_date": ex_date,
                "record_date": None,
                "effective_date": ex_date,    # approximation; payment date not provided
            },
            "status": "COMPLETED",
            "provenance": {
                "source": "Yahoo Finance",
                "source_url": f"https://finance.yahoo.com/quote/{ticker}/history",
                "verification_source": None,
            },
            "impact": {
                "cash_adjustment": amount,
                "price_multiplier": 1.0,
                "share_multiplier": 1.0,
            },
        })

    # Splits
    splits = events.get("splits", {})
    for ts_str, split in splits.items():
        ts = int(ts_str)
        ex_date = timestamp_to_iso(split.get("date", ts))
        ratio = split.get("splitRatio") or f"{int(split.get('numerator', 1))}:{int(split.get('denominator', 1))}"
        extra = ratio.replace(":", "-")
        action_id = make_action_id(isin, "SPLIT", ex_date, extra)

        actions.append({
            "isin": isin,
            "action_id": action_id,
            "action_type": "SPLIT",
            "ratio": ratio,
            "dates": {
                "announcement": ex_date,
                "ex_date": ex_date,
                "record_date": None,
                "effective_date": ex_date,
            },
            "status": "COMPLETED",
            "provenance": {
                "source": "Yahoo Finance",
                "source_url": f"https://finance.yahoo.com/quote/{ticker}/history",
                "verification_source": None,
            },
            "impact": {},  # will be filled by derive_impacts.py
        })

    return actions


def main():
    parser = argparse.ArgumentParser(description="Fetch corporate actions from Yahoo Finance")
    parser.add_argument("--identifiers", required=True, help="Path to identifiers.json")
    parser.add_argument("--output", default="yahoo_actions.json", help="Output file")
    parser.add_argument("--ticker-limit", type=int, default=None, help="Limit processing to first N tickers")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--refresh-cache", action="store_true", help="Ignore cache and refetch all data")
    args = parser.parse_args()

    instruments = load_instruments(args.identifiers)
    if args.ticker_limit:
        instruments = instruments[:args.ticker_limit]

    print(f"Processing {len(instruments)} instruments...")

    # If refresh flag is set, delete cache files to force refetch
    if args.refresh_cache:
        import shutil
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
        os.makedirs(CACHE_DIR, exist_ok=True)

    client = YahooClient()
    all_actions = []
    errors = []

    for idx, (isin, ticker, currency) in enumerate(instruments, start=1):
        if args.verbose:
            print(f"[{idx}/{len(instruments)}] {ticker}")

        raw = client.fetch_events(ticker)
        if raw is None:
            errors.append(f"{ticker}: failed to fetch")
            continue

        actions = extract_actions(isin, ticker, currency, raw)
        all_actions.extend(actions)

        if args.verbose and actions:
            for a in actions:
                print(f"    -> {a['action_id']} ({a['action_type']})")

    # Deduplicate (same action_id)
    seen = set()
    unique_actions = []
    for act in all_actions:
        if act["action_id"] not in seen:
            seen.add(act["action_id"])
            unique_actions.append(act)

    # Write output
    output_data = {
        "meta": {
            "version": "0.2.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "Yahoo Finance",
            "notes": f"Generated by fetch_yahoo_actions.py from {len(instruments)} instruments",
        },
        "actions": unique_actions,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nDone. Extracted {len(unique_actions)} actions -> {args.output}")
    if errors:
        print(f"\n{len(errors)} errors occurred. First few:")
        for e in errors[:5]:
            print(f"  - {e}")

    if len(unique_actions) == 0:
        print("Error: no actions extracted", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
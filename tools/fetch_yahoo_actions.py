#!/usr/bin/env python3
"""
Fetch Corporate Actions from Yahoo Finance using yfinance.

Uses the yfinance library, which manages Yahoo's session, cookies, and
CRUMB token automatically. This avoids the HTTP 429 rate-limiting that
affects naive HTTP requests.

Reads Asset Identifiers registry (identifiers.json) and for each
instrument with a ticker, fetches dividend and split events via
yfinance. Converts them to corporate action entries and writes them
to the output file.

Usage:
    python tools/fetch_yahoo_actions.py \
        --identifiers "$LAS_DATA_HOME/identifiers.json" \
        --output yahoo_actions.json \
        --ticker-limit 50 \
        --min-date 2000-01-01 \
        --verbose

Dependencies:
    yfinance, pandas (both installed via pip install yfinance)

Exit codes:
  0 - success
  1 - no actions extracted
  2 - missing input file
  3 - missing dependency
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple

try:
    import yfinance as yf
except ImportError:
    print("Error: yfinance is required. Install with: pip install yfinance", file=sys.stderr)
    sys.exit(3)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def load_instruments(path: str) -> List[Tuple[str, str, str]]:
    """
    Load instruments from identifiers.json.
    Returns list of (isin, ticker, currency).
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
        print("Error: no instruments found in identifiers file", file=sys.stderr)
        sys.exit(2)

    result = []
    for inst in instruments:
        isin = inst.get("isin")
        ticker = inst.get("ticker")
        if not isin or not ticker:
            continue
        # Determine currency: prefer inst['currency'], else listings[PRIMARY]
        currency = inst.get("currency")
        if not currency:
            listings = inst.get("listings")
            if isinstance(listings, list):
                for listing in listings:
                    if listing.get("status") == "PRIMARY" and listing.get("currency"):
                        currency = listing["currency"]
                        break
                if not currency and listings:
                    currency = listings[0].get("currency")
        if not currency:
            currency = "USD"
        result.append((isin, ticker.upper(), currency))
    return result


def ratio_to_string(ratio: float) -> Optional[str]:
    """
    Convert a yfinance split ratio (float) to "N:M" string format.
    Examples:
        4.0   -> "4:1"
        0.5   -> "1:2"
        0.125 -> "1:8"
        2.5   -> "5:2"
    Returns None if ratio cannot be expressed with small denominator.
    """
    if ratio is None or ratio <= 0:
        return None
    try:
        frac = Fraction(ratio).limit_denominator(100)
        num = frac.numerator
        den = frac.denominator
        if num <= 0 or den <= 0:
            return None
        return f"{num}:{den}"
    except (ValueError, OverflowError):
        return None


def timestamp_to_iso(ts) -> Optional[str]:
    """Convert a pandas Timestamp (or similar) to ISO date string YYYY-MM-DD."""
    if ts is None:
        return None
    try:
        # pandas Timestamp has .date() method
        return ts.date().isoformat()
    except AttributeError:
        try:
            # fallback for datetime
            return ts.strftime("%Y-%m-%d")
        except Exception:
            return None


# ----------------------------------------------------------------------
# Action builders
# ----------------------------------------------------------------------

def build_dividend_action(
    isin: str,
    ticker: str,
    currency: str,
    date_str: str,
    amount: float,
) -> Dict[str, Any]:
    """Build a DIVIDEND corporate action entry."""
    action_id = f"{isin}-DIVIDEND-{date_str}-{amount:.4f}"
    return {
        "isin": isin,
        "action_id": action_id,
        "action_type": "DIVIDEND",
        "amount": round(float(amount), 6),
        "currency": currency,
        "dates": {
            "announcement": date_str,   # approximation (Yahoo lacks announcement date)
            "ex_date": date_str,
            "record_date": None,
            "effective_date": date_str,
        },
        "status": "COMPLETED",
        "provenance": {
            "source": "Yahoo Finance (yfinance)",
            "source_url": f"https://finance.yahoo.com/quote/{ticker}/history",
        },
        "impact": {
            "cash_adjustment": round(float(amount), 6),
            "price_multiplier": 1.0,
            "share_multiplier": 1.0,
        },
    }


def build_split_action(
    isin: str,
    ticker: str,
    date_str: str,
    ratio_str: str,
) -> Dict[str, Any]:
    """Build a SPLIT corporate action entry."""
    action_id = f"{isin}-SPLIT-{date_str}-{ratio_str.replace(':', '-')}"
    # Derive impact multipliers from ratio (for consistency)
    num, den = ratio_str.split(":")
    num_i, den_i = int(num), int(den)
    return {
        "isin": isin,
        "action_id": action_id,
        "action_type": "SPLIT",
        "ratio": ratio_str,
        "dates": {
            "announcement": date_str,
            "ex_date": date_str,
            "effective_date": date_str,
        },
        "status": "COMPLETED",
        "provenance": {
            "source": "Yahoo Finance (yfinance)",
            "source_url": f"https://finance.yahoo.com/quote/{ticker}/history",
        },
        "impact": {
            "price_multiplier": den_i / num_i,
            "share_multiplier": num_i / den_i,
            "cash_adjustment": 0.0,
        },
    }


# ----------------------------------------------------------------------
# Fetching
# ----------------------------------------------------------------------

def fetch_actions_for_ticker(
    isin: str,
    ticker: str,
    currency: str,
    min_date: Optional[str] = None,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """
    Fetch dividend and split events for a ticker via yfinance.
    Returns a list of action dicts (may be empty).
    """
    actions: List[Dict[str, Any]] = []
    try:
        t = yf.Ticker(ticker)
        divs = t.dividends
        splits = t.splits
    except Exception as e:
        if verbose:
            print(f"    yfinance error for {ticker}: {e}", file=sys.stderr)
        return actions

    # Dividends
    if divs is not None and len(divs) > 0:
        for ts, amount in divs.items():
            date_str = timestamp_to_iso(ts)
            if not date_str:
                continue
            if min_date and date_str < min_date:
                continue
            actions.append(
                build_dividend_action(isin, ticker, currency, date_str, float(amount))
            )

    # Splits
    if splits is not None and len(splits) > 0:
        for ts, ratio in splits.items():
            date_str = timestamp_to_iso(ts)
            if not date_str:
                continue
            if min_date and date_str < min_date:
                continue
            ratio_str = ratio_to_string(float(ratio))
            if ratio_str is None:
                if verbose:
                    print(f"    Skipping split with unresolvable ratio: {ratio}", file=sys.stderr)
                continue
            actions.append(
                build_split_action(isin, ticker, date_str, ratio_str)
            )

    return actions


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fetch corporate actions from Yahoo Finance using yfinance"
    )
    parser.add_argument("--identifiers", required=True, help="Path to identifiers.json")
    parser.add_argument("--output", default="yahoo_actions.json", help="Output file")
    parser.add_argument("--ticker-limit", type=int, default=None, help="Limit to first N tickers")
    parser.add_argument("--min-date", default="2000-01-01",
                        help="Only include actions with date >= this (YYYY-MM-DD)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    instruments = load_instruments(args.identifiers)
    if args.ticker_limit:
        instruments = instruments[:args.ticker_limit]

    print(f"Processing {len(instruments)} instruments (min date {args.min_date})...")

    all_actions: List[Dict[str, Any]] = []
    errors: List[str] = []

    for idx, (isin, ticker, currency) in enumerate(instruments, start=1):
        if args.verbose:
            print(f"[{idx}/{len(instruments)}] {ticker} ({currency})")

        try:
            actions = fetch_actions_for_ticker(
                isin, ticker, currency, min_date=args.min_date, verbose=args.verbose
            )
        except Exception as e:
            errors.append(f"{ticker}: {e}")
            continue

        if not actions:
            if args.verbose:
                print(f"    no actions found")
            continue

        all_actions.extend(actions)
        if args.verbose:
            divs = sum(1 for a in actions if a["action_type"] == "DIVIDEND")
            splits = sum(1 for a in actions if a["action_type"] == "SPLIT")
            print(f"    {divs} dividends, {splits} splits")

    # Deduplicate by action_id
    seen = set()
    unique_actions: List[Dict[str, Any]] = []
    for act in all_actions:
        aid = act["action_id"]
        if aid not in seen:
            seen.add(aid)
            unique_actions.append(act)

    # Sort by ex_date for stable output
    unique_actions.sort(key=lambda a: (a["dates"].get("ex_date") or "", a["action_id"]))

    output_data = {
        "meta": {
            "version": "0.2.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "Yahoo Finance (yfinance)",
            "notes": (
                f"Generated by fetch_yahoo_actions.py from {len(instruments)} instruments; "
                f"min_date={args.min_date}; total_actions={len(unique_actions)}"
            ),
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
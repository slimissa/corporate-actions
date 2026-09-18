#!/usr/bin/env python3
"""
Fetch Corporate Actions from Yahoo Finance using yfinance.

Uses the yfinance library, which manages Yahoo's session, cookies, and
CRUMB token automatically. This avoids the HTTP 429 rate-limiting that
affects naive HTTP requests.

Reads the Asset Identifiers registry and, for each instrument with a
ticker, fetches dividend and split events via yfinance. Converts them
to corporate action entries and writes them to the output file.

Announcement-date approximation
-------------------------------
Yahoo does not expose the announcement date for a dividend, so it is
set equal to the ex-date. This passes temporal validation but is not
historically accurate. The same is true for the payment date: the
registry stores the ex-date in the effective_date field, which is a
documented approximation.

Split-adjusted amounts
----------------------
yfinance returns dividend amounts adjusted for subsequent splits. A
dividend paid before a 10:1 split is reported at the post-split
equivalent amount. This is intentional for backtesting; see
docs/data_sources.md for the full note.

Retries
-------
Transient failures (429, timeout, DNS) are retried up to MAX_RETRIES
times with exponential backoff and jitter. A ticker that fails on
every attempt is recorded in the errors list and does not abort the
run; the process exits 1 at the end to signal partial failure.

Usage:
    python tools/fetch_yahoo_actions.py \
        --identifiers "$LAS_DATA_HOME/identifiers.json" \
        --output yahoo_actions.json \
        --ticker-limit 50 \
        --min-date 2000-01-01 \
        --verbose

Dependencies:
    yfinance (pulls in pandas)

Exit codes:
  0 - success, no ticker failed (0 actions is a valid result)
  1 - at least one ticker failed after retries
  2 - missing or invalid input file, or bad --min-date
  3 - missing dependency, no instruments, or every ticker failed
"""

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple

try:
    import yfinance as yf
except ImportError:
    print(
        "Error: yfinance is required. Install with: pip install yfinance",
        file=sys.stderr,
    )
    sys.exit(3)


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------

DEFAULT_MIN_DATE = "2000-01-01"
MAX_RETRIES = 3
BASE_RETRY_DELAY = 2.0
MAX_RETRY_DELAY = 30.0


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def load_instruments(path: str) -> List[Tuple[str, str, str]]:
    """Load instruments from identifiers.json.

    Returns a list of (isin, ticker, currency) triples. Entries missing
    isin or ticker are skipped. A missing currency falls back to the
    PRIMARY listing's currency, then to 'USD'.

    Exits 2 on file or parse errors.
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
    if not instruments:
        print(f"Error: no instruments found in {path}", file=sys.stderr)
        sys.exit(2)

    result: List[Tuple[str, str, str]] = []
    for inst in instruments:
        if not isinstance(inst, dict):
            continue
        isin = inst.get("isin")
        ticker = inst.get("ticker")
        if not isin or not ticker:
            continue

        currency = inst.get("currency")
        if not currency:
            listings = inst.get("listings")
            if isinstance(listings, list):
                for listing in listings:
                    if (
                        isinstance(listing, dict)
                        and listing.get("status") == "PRIMARY"
                        and listing.get("currency")
                    ):
                        currency = listing["currency"]
                        break
                if not currency and listings:
                    first = listings[0]
                    if isinstance(first, dict):
                        currency = first.get("currency")
        if not currency:
            currency = "USD"

        result.append((isin, str(ticker).upper(), str(currency)))

    return result


def validate_min_date(value: str) -> str:
    """Return value unchanged if it is a valid YYYY-MM-DD date.

    Exits 2 with a clear message otherwise. Without this, an invalid
    value becomes a string that fails every lexicographic comparison
    silently, dropping all events.
    """
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        print(
            f"Error: --min-date must be YYYY-MM-DD, got {value!r}",
            file=sys.stderr,
        )
        sys.exit(2)
    return value


def ratio_to_string(ratio: float) -> Optional[str]:
    """Convert a yfinance split ratio (float) to "N:M" string format.

    Examples:
        4.0   -> "4:1"
        0.5   -> "1:2"
        0.125 -> "1:8"
        2.5   -> "5:2"

    Returns None if the ratio cannot be expressed with denominator at
    most 100, or if it is zero or negative. The denominator cap rejects
    floats produced by rounding errors that would otherwise translate
    into an unreadable ratio.
    """
    if ratio is None or ratio <= 0:
        return None
    try:
        frac = Fraction(ratio).limit_denominator(100)
    except (ValueError, OverflowError):
        return None
    num = frac.numerator
    den = frac.denominator
    if num <= 0 or den <= 0:
        return None
    return f"{num}:{den}"


def timestamp_to_iso(ts: Any) -> Optional[str]:
    """Convert a pandas Timestamp (or datetime) to YYYY-MM-DD.

    Returns None if the value is missing or cannot be converted.
    """
    if ts is None:
        return None
    # pandas Timestamp has a .date() method that returns datetime.date.
    date_method = getattr(ts, "date", None)
    if callable(date_method):
        try:
            return date_method().isoformat()
        except (AttributeError, ValueError):
            pass
    # Plain datetime.date or datetime.datetime.
    try:
        return ts.strftime("%Y-%m-%d")
    except (AttributeError, ValueError):
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
    """Build a DIVIDEND corporate action entry.

    The action_id uses the amount formatted with 4 decimal places, the
    canonical discriminator for dividend entries. The stored value uses
    6 decimal places to avoid losing precision for small dividends.
    """
    return {
        "isin": isin,
        "action_id": f"{isin}-DIVIDEND-{date_str}-{amount:.4f}",
        "action_type": "DIVIDEND",
        "amount": round(float(amount), 6),
        "currency": currency,
        "dates": {
            # Yahoo does not expose the announcement date. Setting it to
            # the ex-date passes temporal validation but is an
            # approximation documented in docs/data_sources.md.
            "announcement": date_str,
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
            "price_multiplier": 1.0,
            "share_multiplier": 1.0,
            "cash_adjustment": round(float(amount), 6),
        },
    }


def build_split_action(
    isin: str,
    ticker: str,
    date_str: str,
    ratio_str: str,
) -> Dict[str, Any]:
    """Build a SPLIT corporate action entry.

    Impact multipliers are derived from the ratio here so that the
    entry is self-consistent even before derive_impacts.py runs.
    """
    num, den = ratio_str.split(":")
    num_i, den_i = int(num), int(den)
    return {
        "isin": isin,
        "action_id": f"{isin}-SPLIT-{date_str}-{num_i}-{den_i}",
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

def _fetch_events(ticker: str, verbose: bool) -> Tuple[Any, Any]:
    """Fetch (dividends, splits) for a ticker, with retries.

    Raises the final exception if every attempt fails.
    """
    last_exc: Optional[BaseException] = None
    for attempt in range(MAX_RETRIES):
        try:
            t = yf.Ticker(ticker)
            divs = t.dividends
            splits = t.splits
            return divs, splits
        except Exception as e:  # yfinance raises bare Exception subclasses
            last_exc = e
            if attempt + 1 < MAX_RETRIES:
                delay = min(
                    BASE_RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1.0),
                    MAX_RETRY_DELAY,
                )
                if verbose:
                    print(
                        f"    retry {attempt + 1}/{MAX_RETRIES} for "
                        f"{ticker} in {delay:.1f}s: {e}",
                        file=sys.stderr,
                    )
                time.sleep(delay)
    # Exhausted retries.
    assert last_exc is not None
    raise last_exc


def fetch_actions_for_ticker(
    isin: str,
    ticker: str,
    currency: str,
    min_date: Optional[str] = None,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch dividend and split events for one ticker.

    Returns a list of action dicts, possibly empty. Raises if the
    underlying yfinance call fails on every retry.
    """
    divs, splits = _fetch_events(ticker, verbose)
    actions: List[Dict[str, Any]] = []

    if divs is not None and len(divs) > 0:
        for ts, amount in divs.items():
            date_str = timestamp_to_iso(ts)
            if not date_str:
                continue
            if min_date and date_str < min_date:
                continue
            try:
                amount_f = float(amount)
            except (TypeError, ValueError):
                if verbose:
                    print(
                        f"    skipping dividend with non-numeric "
                        f"amount {amount!r} for {ticker}",
                        file=sys.stderr,
                    )
                continue
            if amount_f <= 0:
                continue
            actions.append(
                build_dividend_action(
                    isin, ticker, currency, date_str, amount_f,
                )
            )

    if splits is not None and len(splits) > 0:
        for ts, ratio in splits.items():
            date_str = timestamp_to_iso(ts)
            if not date_str:
                continue
            if min_date and date_str < min_date:
                continue
            try:
                ratio_f = float(ratio)
            except (TypeError, ValueError):
                if verbose:
                    print(
                        f"    skipping split with non-numeric ratio "
                        f"{ratio!r} for {ticker}",
                        file=sys.stderr,
                    )
                continue
            ratio_str = ratio_to_string(ratio_f)
            if ratio_str is None:
                if verbose:
                    print(
                        f"    skipping split with unresolvable ratio "
                        f"{ratio!r} for {ticker}",
                        file=sys.stderr,
                    )
                continue
            actions.append(
                build_split_action(isin, ticker, date_str, ratio_str)
            )

    return actions


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch corporate actions from Yahoo Finance using yfinance"
    )
    parser.add_argument(
        "--identifiers", required=True, help="Path to identifiers.json"
    )
    parser.add_argument(
        "--output", default="yahoo_actions.json",
        help="Output file (default: yahoo_actions.json)",
    )
    parser.add_argument(
        "--ticker-limit", type=int, default=None,
        help="Only process the first N tickers",
    )
    parser.add_argument(
        "--min-date", default=DEFAULT_MIN_DATE,
        help=f"Only include actions with date >= this "
             f"(YYYY-MM-DD, default: {DEFAULT_MIN_DATE})",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print per-ticker progress and retry messages",
    )
    args = parser.parse_args()

    min_date = validate_min_date(args.min_date)
    instruments = load_instruments(args.identifiers)

    if args.ticker_limit is not None:
        if args.ticker_limit <= 0:
            print(
                "Error: --ticker-limit must be a positive integer",
                file=sys.stderr,
            )
            return 2
        instruments = instruments[: args.ticker_limit]

    if not instruments:
        print(
            f"Error: no instruments with a ticker found in "
            f"{args.identifiers}",
            file=sys.stderr,
        )
        return 3

    print(
        f"Processing {len(instruments)} instruments "
        f"(min date {min_date})..."
    )

    all_actions: List[Dict[str, Any]] = []
    errors: List[str] = []
    processed = 0

    for idx, (isin, ticker, currency) in enumerate(instruments, start=1):
        if args.verbose:
            print(f"[{idx}/{len(instruments)}] {ticker} ({currency})")

        try:
            actions = fetch_actions_for_ticker(
                isin, ticker, currency,
                min_date=min_date, verbose=args.verbose,
            )
        except Exception as e:
            errors.append(f"{ticker}: {e}")
            if args.verbose:
                print(f"    FAILED: {e}", file=sys.stderr)
            continue

        processed += 1

        if not actions:
            if args.verbose:
                print("    no actions found")
            continue

        all_actions.extend(actions)
        if args.verbose:
            divs = sum(1 for a in actions if a["action_type"] == "DIVIDEND")
            splits = sum(1 for a in actions if a["action_type"] == "SPLIT")
            print(f"    {divs} dividends, {splits} splits")

    # Deduplicate by action_id, preserving insertion order.
    seen = set()
    unique_actions: List[Dict[str, Any]] = []
    for act in all_actions:
        aid = act["action_id"]
        if aid not in seen:
            seen.add(aid)
            unique_actions.append(act)

    # Sort by (ex_date, action_id) for stable output.
    unique_actions.sort(
        key=lambda a: (a["dates"].get("ex_date") or "", a["action_id"])
    )

    output_data = {
        "meta": {
            "version": "0.3.0",
            "generated_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "source": "Yahoo Finance (yfinance)",
            "notes": (
                f"Generated by fetch_yahoo_actions.py from "
                f"{len(instruments)} instruments; "
                f"min_date={min_date}; "
                f"total_actions={len(unique_actions)}"
            ),
        },
        "actions": unique_actions,
    }

    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
            f.write("\n")
    except OSError as e:
        print(f"Error writing {args.output}: {e}", file=sys.stderr)
        return 3

    print(f"\nDone. Extracted {len(unique_actions)} actions -> {args.output}")
    if errors:
        print(f"\n{len(errors)} ticker(s) failed. First few:")
        for e in errors[:5]:
            print(f"  - {e}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more")

    if not unique_actions:
        # A legitimate empty result. Not an error.
        print(
            "Note: no actions found in the requested window. This is "
            "normal for tickers without dividends or splits since "
            f"{min_date}.",
            file=sys.stderr,
        )

    # Exit codes:
    #   every ticker failed     -> 3
    #   at least one failed     -> 1
    #   none failed (0 actions) -> 0
    if processed == 0:
        return 3
    if errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
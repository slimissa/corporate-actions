#!/usr/bin/env python3
"""
Backtest Adjustment Example: Why Corporate Actions Matter

This example demonstrates how to use the Corporate Actions Registry to
adjust historical prices before computing backtest P&L. Without adjustment,
any strategy that holds a stock through a split or dividend produces
incorrect returns.

The example:
  1. Loads the Corporate Actions Registry via the Python wrapper.
  2. Fetches historical prices for a ticker via yfinance.
3. Computes P&L two ways:
   a. Price return  — yfinance's Close series, already split-adjusted
   b. Total return  — price return plus dividends paid in the window
  4. Prints the difference for the same holding period.

Prerequisites:
  - Python wrapper installed (pip install wrappers/python)
  - yfinance installed (pip install yfinance)
  - Ticker→ISIN resolution requires the Asset Identifiers registry.
    Set LAS_DATA_HOME to the directory containing identifiers.json, or
    pass --isin explicitly to skip ticker resolution.

Run:
  python examples/backtest_adjustment.py --ticker NVDA --start 2024-01-02 --end 2024-07-01
  python examples/backtest_adjustment.py --ticker AAPL --start 2020-01-02 --end 2021-01-02
  python examples/backtest_adjustment.py --ticker MSFT --start 2020-01-02 --end 2024-01-02
  python examples/backtest_adjustment.py --ticker JPM --exchange XNYS --start 2020-01-02 --end 2024-01-02
  python examples/backtest_adjustment.py --isin US67066G1040 --ticker NVDA --start 2024-01-02 --end 2024-07-01
"""

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

# ----------------------------------------------------------------------
# Imports with friendly fallbacks
# ----------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]

# Corporate Actions wrapper
try:
    from corporate_actions_registry import CorporateActionsRegistry
except ImportError:
    sys.path.insert(0, str(REPO_ROOT / "wrappers" / "python"))
    from corporate_actions_registry import CorporateActionsRegistry

# Ticker → ISIN index lives in tools/validate.py
sys.path.insert(0, str(REPO_ROOT))
try:
    from tools.validate import load_ticker_isin_index, RegistryLoadError
except ImportError as e:
    print(f"Error: could not import ticker index from tools.validate: {e}",
          file=sys.stderr)
    print("       Run this example from the repository root.", file=sys.stderr)
    sys.exit(3)

# Price data
try:
    import yfinance as yf
except ImportError:
    print("Error: yfinance is required. Install with: pip install yfinance",
          file=sys.stderr)
    sys.exit(3)


# ----------------------------------------------------------------------
# Path resolution
# ----------------------------------------------------------------------
def find_actions_file(cli_path: str = None) -> Path:
    if cli_path:
        p = Path(cli_path)
        if not p.exists():
            print(f"Error: file not found: {p}", file=sys.stderr)
            sys.exit(2)
        return p
    cwd_file = Path.cwd() / "actions.json"
    if cwd_file.exists():
        return cwd_file
    repo_file = REPO_ROOT / "actions.json"
    if repo_file.exists():
        return repo_file
    print("Error: could not find actions.json. Use --actions PATH.",
          file=sys.stderr)
    sys.exit(2)


# ----------------------------------------------------------------------
# Date helpers
# ----------------------------------------------------------------------
def to_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def in_range(d: str, start: date, end: date) -> bool:
    """Return True if ISO date string d is within [start, end]."""
    if not d:
        return False
    try:
        dd = to_date(d)
        return start <= dd <= end
    except ValueError:
        return False


# ----------------------------------------------------------------------
# P&L calculations
# ----------------------------------------------------------------------
def compute_price_return(first_price: float, last_price: float) -> float:
    """Percentage change from first to last, using the prices as returned.

    The prices from yfinance are already split-adjusted. No further
    adjustment is applied here.
    """
    return (last_price / first_price - 1.0) * 100.0


def compute_total_return(
    first_price: float,
    last_price: float,
    actions,
    start: date,
    end: date,
) -> float:
    """Price return plus dividends paid in [start, end].

    Dividends are added to the final price before computing the return.
    This is an approximation: it does not model reinvestment or the
    timing of dividend payments within the window.
    """
    cash = 0.0
    for action in actions:
        if action.action_type not in ("DIVIDEND", "SPECIAL_DIVIDEND"):
            continue
        ex_date_str = action.dates.ex_date if action.dates else None
        if not ex_date_str:
            continue
        if not in_range(ex_date_str, start, end):
            continue
        if action.amount:
            cash += action.amount
    total_end = last_price + cash
    return (total_end / first_price - 1.0) * 100.0


def dedupe_actions(actions):
    """Remove duplicate actions with same (action_type, ex_date, ratio/amount)."""
    seen = set()
    result = []
    for a in actions:
        if not a.dates or not a.dates.ex_date:
            result.append(a)
            continue
        key = (
            a.action_type,
            a.dates.ex_date,
            a.ratio or "",
            round(a.amount or 0.0, 6),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(a)
    return result


# ----------------------------------------------------------------------
# ISIN resolution
# ----------------------------------------------------------------------
def resolve_isin(ticker: str, exchange: str, explicit_isin: str = None):
    """
    Resolve a ticker+exchange pair to an ISIN.

    Priority:
      1. Explicit ISIN argument (skip lookup entirely).
      2. Ticker→ISIN index built from the Asset Identifiers registry.

    Returns the ISIN, or exits with a clear error.
    """
    if explicit_isin:
        return explicit_isin

    try:
        index = load_ticker_isin_index()
    except RegistryLoadError as e:
        print(f"Error loading ticker→ISIN index: {e}", file=sys.stderr)
        print("", file=sys.stderr)
        print("The index requires the Asset Identifiers registry.",
              file=sys.stderr)
        print("Set LAS_DATA_HOME to the directory containing identifiers.json:",
              file=sys.stderr)
        print("    export LAS_DATA_HOME=\"$HOME/Documents/asset-identifiers-data\"",
              file=sys.stderr)
        print("", file=sys.stderr)
        print("Or pass --isin <ISIN> to skip ticker resolution.",
              file=sys.stderr)
        sys.exit(2)

    key = (ticker.upper(), exchange.upper())
    try:
        return index[key]
    except KeyError:
        # Give a helpful hint if the ticker exists on a different exchange.
        other_exchanges = sorted(
            exch for (t, exch) in index if t == ticker.upper()
        )
        if other_exchanges:
            print(f"Error: ticker '{ticker}' not found on exchange "
                  f"'{exchange}'.", file=sys.stderr)
            print(f"       It is listed on: {', '.join(other_exchanges)}",
                  file=sys.stderr)
            print(f"       Try --exchange {other_exchanges[0]}", file=sys.stderr)
        else:
            print(f"Error: ticker '{ticker}' not found in the Asset "
                  f"Identifiers registry.", file=sys.stderr)
            print("       Pass --isin <ISIN> if you know it directly.",
                  file=sys.stderr)
        sys.exit(2)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Demonstrate price adjustment for corporate actions."
    )
    parser.add_argument("--ticker", default="NVDA", help="Ticker symbol")
    parser.add_argument("--exchange", default="XNAS",
                        help="Exchange MIC for ticker resolution "
                             "(default: XNAS)")
    parser.add_argument("--isin", default=None,
                        help="ISIN to use directly (overrides ticker lookup)")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--actions", default=None, help="Path to actions.json")
    args = parser.parse_args()

    start_d = to_date(args.start)
    end_d = to_date(args.end)
    if start_d >= end_d:
        print("Error: start must be before end.", file=sys.stderr)
        return 2

    isin = resolve_isin(args.ticker, args.exchange, args.isin)

    actions_path = find_actions_file(args.actions)
    registry = CorporateActionsRegistry(str(actions_path))

    actions_for_ticker = dedupe_actions(registry.by_isin(isin))
    print(f"Ticker: {args.ticker}  Exchange: {args.exchange}  (ISIN {isin})")
    print(f"Registry: {actions_path}")
    print(f"Actions on record after dedup: {len(actions_for_ticker)}")

    if not actions_for_ticker:
        print()
        print("Note: no corporate actions found for this ISIN in the registry.")
        print("      All three return values will be identical.")
        print("      Try NVDA, AAPL, MSFT, GOOGL, or AMZN to see a difference.")

    print()
    print(f"Fetching prices for {args.ticker} from {args.start} to {args.end}...")
    try:
        ticker_obj = yf.Ticker(args.ticker)
        hist = ticker_obj.history(start=args.start, end=args.end,
                                  auto_adjust=False)
    except Exception as e:
        print(f"Error fetching prices: {e}", file=sys.stderr)
        return 1
    if hist.empty:
        print("No price data returned.")
        return 1

    prices = {ts.date(): float(row["Close"]) for ts, row in hist.iterrows()}
    first_price = prices[min(prices)]
    last_price = prices[max(prices)]

    price_ret = compute_price_return(first_price, last_price)
    total_ret = compute_total_return(
        first_price, last_price, actions_for_ticker, start_d, end_d,
    )

    print()
    print("=" * 60)
    print(f"Backtest return for {args.ticker}")
    print(f"  Holding period: {args.start} to {args.end}")
    print(f"  First price:    {first_price:.4f}  (as reported by yfinance)")
    print(f"  Last price:     {last_price:.4f}")
    print("=" * 60)
    print(f"  Price return:                     {price_ret:+7.2f}%")
    print(f"  Total return (price + dividends): {total_ret:+7.2f}%")
    print("=" * 60)

    splits_in_range = [
        a for a in actions_for_ticker
        if a.action_type in ("SPLIT", "REVERSE_SPLIT")
        and a.dates and in_range(a.dates.ex_date, start_d, end_d)
    ]
    dividends_in_range = [
        a for a in actions_for_ticker
        if a.action_type in ("DIVIDEND", "SPECIAL_DIVIDEND")
        and a.dates and in_range(a.dates.ex_date, start_d, end_d)
    ]
    print()
    if splits_in_range:
        print("Splits in holding period (deduplicated):")
        for a in splits_in_range:
            print(f"  {a.dates.ex_date}  ratio {a.ratio}")
    if dividends_in_range:
        total_cash = sum(a.amount for a in dividends_in_range if a.amount)
        print(f"Dividends in holding period: {len(dividends_in_range)} payments, "
              f"total cash per share {total_cash:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
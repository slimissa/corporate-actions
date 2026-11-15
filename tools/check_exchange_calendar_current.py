#!/usr/bin/env python3
"""
Check that the local Exchange Calendar snapshot matches the live upstream.

Usage:
    python3 tools/check_exchange_calendar_current.py             # default: strict
    python3 tools/check_exchange_calendar_current.py --advisory  # exit 0 on network failure
    python3 tools/check_exchange_calendar_current.py --strict    # fail on version drift or unreachable
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

SNAPSHOT = Path(__file__).parent / "exchange_calendar_snapshot.json"
UPSTREAM_URL = "https://raw.githubusercontent.com/slimissa/exchange-calendar/main/calendar.json"
HEADERS = {"User-Agent": "corporate-actions-registry research slimissabara@gmail.com"}


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Exchange Calendar snapshot against live upstream.")
    parser.add_argument("--strict", action="store_true", default=True,
                        help="Fail on version drift or unreachable upstream (default).")
    parser.add_argument("--advisory", action="store_true",
                        help="Exit 0 on network failure or version drift, print warnings.")
    args = parser.parse_args()

    if args.advisory:
        args.strict = False

    if not SNAPSHOT.exists():
        print(f"Error: snapshot not found at {SNAPSHOT}", file=sys.stderr)
        return 2

    snapshot = json.loads(SNAPSHOT.read_text())
    
    # Exchange calendar schema might store exchanges under 'exchanges' or 'calendar'
    snap_exchanges = snapshot.get("exchanges", snapshot.get("calendar", []))
    snap_mics = {e.get("mic") or e.get("code") for e in snap_exchanges if e.get("mic") or e.get("code")}
    
    snap_meta = snapshot.get("meta", {})
    snap_version = snap_meta.get("version", "unknown")

    try:
        live = fetch(UPSTREAM_URL)
    except Exception as e:
        msg = f"Error: could not fetch live upstream ({e})"
        if args.strict:
            print(msg, file=sys.stderr)
            return 1
        print(f"warning: {msg}", file=sys.stderr)
        return 0

    live_exchanges = live.get("exchanges", live.get("calendar", []))
    live_mics = {e.get("mic") or e.get("code") for e in live_exchanges if e.get("mic") or e.get("code")}
    
    live_meta = live.get("meta", {})
    live_version = live_meta.get("version", "unknown")

    version_drift = snap_version != live_version
    if version_drift:
        msg = f"version drift: snapshot={snap_version}, live={live_version}"
        if args.strict:
            print(f"Error: {msg}", file=sys.stderr)
        else:
            print(f"warning: {msg}")

    missing_in_snap = live_mics - snap_mics
    missing_in_live = snap_mics - live_mics

    has_errors = bool(missing_in_snap or missing_in_live or (version_drift and args.strict))

    if has_errors:
        print("\nMismatch between snapshot and live upstream:", file=sys.stderr)
        if missing_in_snap:
            print(f"  MICs in live but not in snapshot: {sorted(missing_in_snap)}", file=sys.stderr)
        if missing_in_live:
            print(f"  MICs in snapshot but not in live: {sorted(missing_in_live)}", file=sys.stderr)

        if args.strict:
            print("\nTo fix: regenerate the snapshot or update actions.json.", file=sys.stderr)
            return 1
        else:
            print("\nwarning: drift detected, but running in advisory mode.", file=sys.stderr)
            return 0

    print(f"OK: {len(snap_mics)} exchange MICs match the live upstream (version {snap_version}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

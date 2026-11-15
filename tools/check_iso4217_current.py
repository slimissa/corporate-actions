#!/usr/bin/env python3
"""
Check that the local ISO 4217 snapshot matches the live upstream.

Usage:
    python3 tools/check_iso4217_current.py             # default: strict
    python3 tools/check_iso4217_current.py --advisory  # exit 0 on network failure
    python3 tools/check_iso4217_current.py --strict    # fail on version drift or unreachable
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SNAPSHOT = Path(__file__).parent / "iso4217_snapshot.json"
UPSTREAM_URL = "https://raw.githubusercontent.com/slimissa/iso4217/main/iso4217.json"
HEADERS = {"User-Agent": "corporate-actions-registry research slimissabara@gmail.com"}


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check ISO 4217 snapshot against live upstream.")
    parser.add_argument("--strict", action="store_true", default=True,
                        help="Fail on version drift or unreachable upstream (default).")
    parser.add_argument("--advisory", action="store_true",
                        help="Exit 0 on network failure or version drift, print warnings.")
    args = parser.parse_args()

    # --advisory overrides --strict
    if args.advisory:
        args.strict = False

    if not SNAPSHOT.exists():
        print(f"Error: snapshot not found at {SNAPSHOT}", file=sys.stderr)
        return 2

    snapshot = json.loads(SNAPSHOT.read_text())
    snap_meta = snapshot.get("meta", {})
    snap_version = snap_meta.get("version", "unknown")
    snap_codes = {c["code"]: c for c in snapshot.get("currencies", {}).get("active", [])}

    try:
        live = fetch(UPSTREAM_URL)
    except Exception as e:
        msg = f"Error: could not fetch live upstream ({e})"
        if args.strict:
            print(msg, file=sys.stderr)
            return 1
        print(f"warning: {msg}", file=sys.stderr)
        return 0

    live_meta = live.get("meta", {})
    live_version = live_meta.get("version", "unknown")
    live_codes = {c["code"]: c for c in live.get("currencies", {}).get("active", [])}

    # 1. Check version
    version_drift = snap_version != live_version
    if version_drift:
        msg = f"version drift: snapshot={snap_version}, live={live_version}"
        if args.strict:
            print(f"Error: {msg}", file=sys.stderr)
            # Don't return yet, let code checks also run
        else:
            print(f"warning: {msg}")

    # 2. Check code set
    missing_in_snap = set(live_codes) - set(snap_codes)
    missing_in_live = set(snap_codes) - set(live_codes)

    # 3. Check field-level drift for codes that exist in both
    field_drift = []
    for code in set(snap_codes) & set(live_codes):
        s = snap_codes[code]
        l = live_codes[code]
        if s.get("minor_units") != l.get("minor_units"):
            field_drift.append(f"{code}: minor_units {s.get('minor_units')} != {l.get('minor_units')}")
        if s.get("numeric") != l.get("numeric"):
            field_drift.append(f"{code}: numeric {s.get('numeric')} != {l.get('numeric')}")

    has_errors = bool(missing_in_snap or missing_in_live or field_drift or (version_drift and args.strict))

    if has_errors:
        print("\nMismatch between snapshot and live upstream:", file=sys.stderr)
        if missing_in_snap:
            print(f"  Codes in live but not in snapshot: {sorted(missing_in_snap)}", file=sys.stderr)
        if missing_in_live:
            print(f"  Codes in snapshot but not in live: {sorted(missing_in_live)}", file=sys.stderr)
        if field_drift:
            print("  Field drift (first 5):", file=sys.stderr)
            for d in field_drift[:5]:
                print(f"    {d}", file=sys.stderr)
            if len(field_drift) > 5:
                print(f"    ... and {len(field_drift) - 5} more", file=sys.stderr)

        if args.strict:
            print("\nTo fix: regenerate the snapshot or update actions.json.", file=sys.stderr)
            return 1
        else:
            print("\nwarning: drift detected, but running in advisory mode.", file=sys.stderr)
            return 0

    print(f"OK: {len(snap_codes)} ISO 4217 codes match the live upstream (version {snap_version}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

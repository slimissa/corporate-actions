#!/usr/bin/env python3
"""Verify README ecosystem table matches tools/sibling_versions.json.

The README names each sibling registry and its version. The pin file
records what this repo expects. Drift between them means someone edited
one and forgot the other.

Why a separate pin: README is prose, JSON is data. When a sibling
releases a new version, update both in the same PR, and this check
forces them to agree.

Run:
    python3 tools/check_ecosystem_versions.py

Exit codes:
    0 - all versions agree
    1 - drift detected
    2 - README or pin missing/malformed
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
PIN = REPO_ROOT / "tools" / "sibling_versions.json"

# Each pattern matches a README ecosystem table row and captures the
# version cell. Adjust the row label if the README wording changes.
ROW_RE = {
    "iso4217": re.compile(
        r"\|\s*\[ISO 4217\][^|]*\|[^|]*\|\s*v?([\d.]+)\s*\|",
        re.IGNORECASE,
    ),
    "exchange_calendar": re.compile(
        r"\|\s*\[Exchange Calendar\][^|]*\|[^|]*\|\s*v?([\d.]+)\s*\|",
        re.IGNORECASE,
    ),
    "asset_identifiers_schema": re.compile(
        r"\|\s*\[Asset Identifiers\][^|]*\|[^|]*\|\s*(?:schema\s*)?v?([\d.]+)\s*\|",
        re.IGNORECASE,
    ),
}


def _normalize(version: str) -> str:
    return version.strip().lstrip("v")


def main() -> int:
    if not README.is_file():
        print(f"Error: {README} not found", file=sys.stderr)
        return 2
    if not PIN.is_file():
        print(f"Error: {PIN} not found", file=sys.stderr)
        return 2

    try:
        pinned = json.loads(PIN.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Error: {PIN} is not valid JSON: {e}", file=sys.stderr)
        return 2

    text = README.read_text(encoding="utf-8")

    drift = []
    for key, pattern in ROW_RE.items():
        if key not in pinned:
            print(f"Warning: {key} not in {PIN.name}", file=sys.stderr)
            continue
        m = pattern.search(text)
        if not m:
            drift.append((key, pinned[key], "(not found in README)"))
            continue
        readme_version = m.group(1)
        if _normalize(readme_version) != _normalize(pinned[key]):
            drift.append((key, pinned[key], readme_version))

    if drift:
        print("Ecosystem version drift:", file=sys.stderr)
        for key, want, got in drift:
            print(f"  {key}: pinned={want!r}, README={got!r}", file=sys.stderr)
        print()
        print("Fix by editing README.md or tools/sibling_versions.json "
              "so they agree.", file=sys.stderr)
        return 1

    print(f"OK: {len(pinned)} sibling version(s) agree between "
          f"README.md and tools/sibling_versions.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
    
#!/usr/bin/env python3
"""
Derive the `redistribution` field for every action in actions.json.

Reads the provenance.source of each action, maps it to a
redistribution category via redistribution_for(), and either:

  - writes the value back to actions.json (default), or
  - verifies the on-disk value matches the derived value (--check), or
  - prints what would change without writing (--dry-run), or
  - prints the mapping rules (--list-mappings).

The mapping is defined in redistribution_for() below and documented
in docs/redistribution.md. Any source that does not match a rule
returns 'restricted', which is a fail-safe: the tool refuses to write
actions.json if any action maps to it. Fix the mapping (add a rule)
rather than shipping a 'restricted' value.

Atomicity
---------
A single write via a temp file and rename. If any action maps to
'restricted', or if the structure of actions.json is invalid, the
file is not written at all.

Usage
-----
    python3 tools/derive_redistribution.py             # write
    python3 tools/derive_redistribution.py --check     # verify only
    python3 tools/derive_redistribution.py --dry-run   # show diff
    python3 tools/derive_redistribution.py --verbose   # per-action output
    python3 tools/derive_redistribution.py --list-mappings

Exit codes
----------
    0 - success
    1 - data error: a source maps to 'restricted', or --check found drift
    2 - usage error: missing/invalid actions.json structure
    3 - file not found, invalid JSON, or I/O error during write
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
ACTIONS_PATH = REPO_ROOT / "actions.json"

# The four closed categories. See docs/redistribution.md for definitions.
VALID_CATEGORIES = ("public-domain", "facts-only", "secondary-source", "restricted")


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

def redistribution_for(source: Optional[str]) -> str:
    """Return the redistribution category for a provenance.source value.

    Rules, in priority order:

      - None or empty                                -> restricted (fail-safe)
      - "SEC EDGAR"                                  -> public-domain
      - "Yahoo Finance*"                             -> secondary-source
      - contains "press release" (ci)                -> facts-only
      - contains "exchange" + "announcement" (ci)    -> facts-only
      - anything else                                -> restricted (fail-safe)

    The doc mirrors this function. If you change a rule here, update
    docs/redistribution.md's "Per-source mapping" table in the same PR.
    """
    if not source:
        return "restricted"
    if source == "SEC EDGAR":
        return "public-domain"
    if source.startswith("Yahoo Finance"):
        return "secondary-source"
    s = source.lower()
    if "press release" in s:
        return "facts-only"
    if "exchange" in s and "announcement" in s:
        return "facts-only"
    return "restricted"


def extract_source(action: Dict[str, Any]) -> Optional[str]:
    """Return the action's provenance.source, or None if absent/invalid."""
    prov = action.get("provenance")
    if not isinstance(prov, dict):
        return None
    src = prov.get("source")
    return src if isinstance(src, str) else None


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def _write_atomic(path: Path, payload: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def load_actions(path: Path) -> Dict[str, Any]:
    """Load actions.json, exiting 3 on any load failure."""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(3)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(3)


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def list_mappings() -> None:
    """Print the mapping rules, mirroring docs/redistribution.md."""
    print("Redistribution mapping rules, in priority order:")
    print()
    print(f"  {'source pattern':<45}  {'category'}")
    print(f"  {'-' * 45}  {'-' * 20}")
    print(f"  {'None or empty':<45}  restricted")
    print(f"  {'\"SEC EDGAR\"':<45}  public-domain")
    print(f"  {'\"Yahoo Finance*\"':<45}  secondary-source")
    print(f"  {'contains \"press release\" (ci)':<45}  facts-only")
    print(f"  {'contains \"exchange\" + \"announcement\"':<45}  facts-only")
    print(f"  {'(anything else)':<45}  restricted")
    print()
    print("See docs/redistribution.md for the full definitions.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Derive and check the redistribution field on every action."
    )
    parser.add_argument("--check", action="store_true",
                        help="Verify on-disk values match derived values. "
                             "Exit 1 on drift. Does not write.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would change. Does not write.")
    parser.add_argument("--verbose", action="store_true",
                        help="Print per-action classification.")
    parser.add_argument("--list-mappings", action="store_true",
                        help="Print the mapping rules and exit.")
    args = parser.parse_args()

    if args.list_mappings:
        list_mappings()
        return 0

    # Load
    doc = load_actions(ACTIONS_PATH)

    if not isinstance(doc, dict):
        print("Error: actions.json top level must be an object", file=sys.stderr)
        return 2
    actions = doc.get("actions")
    if not isinstance(actions, list):
        print("Error: actions.json has no 'actions' list", file=sys.stderr)
        return 2
    if not actions:
        print("Error: 'actions' is empty", file=sys.stderr)
        return 2

    # Pass 1 — compute every value
    computed: Dict[int, str] = {}
    restricted: List[Tuple[str, Optional[str]]] = []

    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            print(f"Error: action at index {i} is not an object", file=sys.stderr)
            return 2
        src = extract_source(action)
        cat = redistribution_for(src)
        computed[i] = cat
        if cat == "restricted":
            restricted.append((action.get("action_id", f"<index {i}>"), src))
        if args.verbose:
            print(f"  [{i:3d}] {action.get('action_id', '?'):<60}  "
                  f"{cat:<20}  (source={src!r})")

    # Pass 2 — refuse to proceed if any action maps to 'restricted'
    if restricted:
        print(f"Error: {len(restricted)} action(s) map to 'restricted'.",
              file=sys.stderr)
        print("Add a rule to redistribution_for() and a row to "
              "docs/redistribution.md,", file=sys.stderr)
        print("then re-run.", file=sys.stderr)
        print(file=sys.stderr)
        for aid, src in restricted[:20]:
            print(f"  {aid}: source={src!r}", file=sys.stderr)
        if len(restricted) > 20:
            print(f"  ... and {len(restricted) - 20} more", file=sys.stderr)
        return 1

    # --check mode
    if args.check:
        drift: List[Tuple[str, Optional[str], str]] = []
        for i, expected in computed.items():
            actual = actions[i].get("redistribution")
            if actual != expected:
                drift.append((actions[i].get("action_id", f"<index {i}>"),
                              actual, expected))
        if drift:
            print(f"Error: {len(drift)} action(s) have stale redistribution.",
                  file=sys.stderr)
            print("Regenerate with:", file=sys.stderr)
            print("  python3 tools/derive_redistribution.py", file=sys.stderr)
            print(file=sys.stderr)
            for aid, got, want in drift[:20]:
                print(f"  {aid}: have {got!r}, want {want!r}", file=sys.stderr)
            if len(drift) > 20:
                print(f"  ... and {len(drift) - 20} more", file=sys.stderr)
            return 1
        print(f"OK: all {len(actions)} redistribution values match.")
        return 0

    # --dry-run mode
    if args.dry_run:
        changes = 0
        for i, expected in computed.items():
            actual = actions[i].get("redistribution")
            if actual != expected:
                changes += 1
                print(f"  [{i:3d}] {actions[i].get('action_id', '?')}: "
                      f"{actual!r} -> {expected!r}")
        if changes == 0:
            print("No changes needed.")
        else:
            print(f"{changes} action(s) would change. (dry run)")
        return 0

    # Write mode
    changes = 0
    for i, expected in computed.items():
        if actions[i].get("redistribution") != expected:
            actions[i]["redistribution"] = expected
            changes += 1

    if changes == 0:
        print(f"No changes needed. All {len(actions)} values already match.")
        return 0

    payload = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    try:
        _write_atomic(ACTIONS_PATH, payload)
    except OSError as e:
        print(f"Error writing {ACTIONS_PATH}: {e}", file=sys.stderr)
        return 3

    counts = Counter(computed.values())
    print(f"Wrote redistribution for {changes} action(s) to {ACTIONS_PATH}.")
    print("Distribution:")
    for cat in VALID_CATEGORIES:
        if cat in counts:
            print(f"  {counts[cat]:4d}  {cat}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
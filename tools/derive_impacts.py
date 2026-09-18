#!/usr/bin/env python3
"""
Derive Impact Multipliers for Corporate Actions

Reads actions.json and for each action computes the "impact" object
(price_multiplier, share_multiplier, cash_adjustment) according to the
action type and its ratio or amount.

Impact definitions:
  - SPLIT / REVERSE_SPLIT:
        ratio = "new:old"  (e.g., 10:1 forward, 1:8 reverse)
        share_multiplier = new / old
        price_multiplier = old / new
        cash_adjustment  = 0.0
  - DIVIDEND / SPECIAL_DIVIDEND:
        amount = cash per share
        share_multiplier = 1.0
        price_multiplier = 1.0
        cash_adjustment  = amount
  - SYMBOL_CHANGE, DELISTING, SPINOFF, MERGER:
        No automatic calculation; all multipliers are set to 1.0 and
        cash_adjustment to 0.0. These types require manual intervention
        or are placeholders.

Atomicity
---------
If any action fails to derive, the file is not written at all. This
avoids a mixed state where some actions carry a fresh impact and others
keep a stale one. The tool exits 1 and prints each failing action id.

The output is written to a temp file and renamed, so a killed process
cannot leave a truncated actions.json.

Usage:
    python tools/derive_impacts.py [--actions actions.json]
                                   [--output actions.json]
                                   [--dry-run]

If --output is omitted, the file is updated in place.
Use --dry-run to preview changes without writing.

Exit codes:
  0 - success
  1 - one or more actions could not be processed (file not written)
  2 - file not found or invalid JSON
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# A canonical split ratio: positive integer, colon, positive integer.
# No whitespace, no decimal point, no sign. Matches validate_arithmetic
# in tools/validate.py, so a ratio that passes here also passes there.
RATIO_RE = re.compile(r"^\d+:\d+$")


def parse_ratio(ratio: str) -> Optional[Tuple[int, int]]:
    """Parse a split ratio of the form "new:old".

    Both parts must be positive integers with no sign, whitespace, or
    decimal point. Returns (new, old) or None if the ratio is invalid.
    """
    if not ratio or not isinstance(ratio, str):
        return None
    if not RATIO_RE.match(ratio):
        return None
    new_s, old_s = ratio.split(":")
    new, old = int(new_s), int(old_s)
    if new <= 0 or old <= 0:
        return None
    return new, old


def derive_impact(action: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Compute the impact object for a single action.

    Returns None if the action cannot be processed. Prints a warning
    naming the action_id and the reason to stderr.
    """
    action_id = action.get("action_id", "?")
    action_type = action.get("action_type")

    if not action_type:
        print(f"Warning: action_id {action_id} has no action_type", file=sys.stderr)
        return None

    impact = {
        "price_multiplier": 1.0,
        "share_multiplier": 1.0,
        "cash_adjustment": 0.0,
    }

    if action_type in ("SPLIT", "REVERSE_SPLIT"):
        ratio_str = action.get("ratio")
        if not ratio_str:
            print(f"Warning: {action_type} action {action_id} missing ratio",
                  file=sys.stderr)
            return None
        parsed = parse_ratio(ratio_str)
        if parsed is None:
            print(f"Warning: invalid ratio {ratio_str!r} for action {action_id}",
                  file=sys.stderr)
            return None
        new, old = parsed
        impact["share_multiplier"] = new / old
        impact["price_multiplier"] = old / new
        impact["cash_adjustment"] = 0.0

    elif action_type in ("DIVIDEND", "SPECIAL_DIVIDEND"):
        amount = action.get("amount")
        if amount is None:
            print(f"Warning: {action_type} action {action_id} missing amount",
                  file=sys.stderr)
            return None
        try:
            amount_float = float(amount)
        except (TypeError, ValueError):
            print(f"Warning: invalid amount {amount!r} for action {action_id}",
                  file=sys.stderr)
            return None
        if amount_float < 0:
            print(f"Warning: negative amount {amount_float} for action {action_id}",
                  file=sys.stderr)
            return None
        impact["cash_adjustment"] = amount_float

    elif action_type in ("SYMBOL_CHANGE", "DELISTING", "SPINOFF", "MERGER"):
        # No automatic derivation. The neutral multipliers are deliberate:
        # a consumer who needs a different treatment for DELISTING (for
        # example, share_multiplier = 0) is making a modelling choice that
        # the registry cannot make on its behalf.
        pass

    else:
        print(f"Warning: unknown action_type {action_type!r} for action {action_id}",
              file=sys.stderr)
        return None

    return impact


def _write_atomic(path: Path, payload: str) -> None:
    """Write payload to path via a temp file and rename.

    A killed process between the two steps leaves the original file
    untouched rather than truncated.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Derive impact multipliers for corporate actions"
    )
    parser.add_argument("--actions", default="actions.json",
                        help="Path to actions.json")
    parser.add_argument("--output", default=None,
                        help="Output file (defaults to overwrite input)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show changes but do not write")
    args = parser.parse_args()

    # Load.
    try:
        with open(args.actions, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {args.actions}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        return 2

    actions = data.get("actions")
    if not isinstance(actions, list):
        print("Error: 'actions' key missing or not a list", file=sys.stderr)
        return 1

    # Compute. On failure, do not mutate. The file must not change if
    # any action fails.
    computed: Dict[int, Dict[str, float]] = {}
    failures: List[Tuple[int, str]] = []
    for i, action in enumerate(actions):
        impact = derive_impact(action)
        if impact is None:
            failures.append((i, action.get("action_id", f"<index {i}>")))
        else:
            computed[i] = impact

    if failures:
        print(
            f"\nError: {len(failures)} action(s) could not be processed. "
            f"Refusing to write.",
            file=sys.stderr,
        )
        for _, aid in failures:
            print(f"  - {aid}", file=sys.stderr)
        return 1

    # Apply.
    for i, impact in computed.items():
        actions[i]["impact"] = impact

    if args.dry_run:
        print(json.dumps(data, indent=2))
        print(f"\nDry run: {len(computed)} actions would have impact derived; 0 errors.")
        return 0

    output_path = Path(args.output or args.actions)
    try:
        _write_atomic(output_path, json.dumps(data, indent=2) + "\n")
    except OSError as e:
        print(f"Error writing {output_path}: {e}", file=sys.stderr)
        return 2

    print(f"Derived impact for {len(computed)} actions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""
Derive Impact Multipliers for Corporate Actions

Reads actions.json and for each action computes the "impact" object
(price_multiplier, share_multiplier, cash_adjustment) according to the
action type and its ratio or amount. The results are written back to
the same file (or a new one) to ensure consistency across the registry.

Impact definitions:
  - SPLIT / REVERSE_SPLIT:
        ratio = "new:old"  (e.g., 10:1 forward, 1:8 reverse)
        share_multiplier = new / old
        price_multiplier = old / new
        cash_adjustment = 0.0
  - DIVIDEND / SPECIAL_DIVIDEND:
        amount = cash per share
        share_multiplier = 1.0
        price_multiplier = 1.0
        cash_adjustment = amount
  - SYMBOL_CHANGE, DELISTING, SPINOFF, MERGER:
        No automatic calculation; set all multipliers to 1.0 and
        cash_adjustment to 0.0 (or leave absent if preferred).
        These types require manual intervention or are placeholders.

Usage:
    python tools/derive_impacts.py [--actions actions.json] [--output actions.json] [--dry-run]

If --output is omitted, the file is updated in place.
Use --dry-run to preview changes without writing.

Exit codes:
  0 - success
  1 - validation errors (bad ratio, missing amount)
  2 - file not found or invalid JSON
"""

import argparse
import json
import sys
from typing import Dict, Any, Optional, Tuple


def parse_ratio(ratio: str) -> Optional[Tuple[float, float]]:
    """
    Parse a split ratio string of the form "new:old" and return (new, old).
    Returns None if the ratio is invalid.
    """
    if not ratio:
        return None
    parts = ratio.split(":")
    if len(parts) != 2:
        return None
    try:
        new = float(parts[0])
        old = float(parts[1])
        if new <= 0 or old <= 0:
            return None
        return new, old
    except ValueError:
        return None


def derive_impact(action: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """
    Compute the impact object for a single action.
    Returns None if the action cannot be processed (missing required data).
    """
    action_type = action.get("action_type")
    if not action_type:
        print(f"Warning: action_id {action.get('action_id', '?')} has no action_type; skipping impact", file=sys.stderr)
        return None

    impact = {
        "price_multiplier": 1.0,
        "share_multiplier": 1.0,
        "cash_adjustment": 0.0,
    }

    if action_type in ("SPLIT", "REVERSE_SPLIT"):
        ratio_str = action.get("ratio")
        if not ratio_str:
            print(f"Warning: {action_type} action {action.get('action_id', '?')} missing ratio; cannot derive impact", file=sys.stderr)
            return None
        ratio = parse_ratio(ratio_str)
        if ratio is None:
            print(f"Warning: invalid ratio '{ratio_str}' for action {action.get('action_id', '?')}", file=sys.stderr)
            return None
        new, old = ratio
        impact["share_multiplier"] = new / old
        impact["price_multiplier"] = old / new
        impact["cash_adjustment"] = 0.0

    elif action_type in ("DIVIDEND", "SPECIAL_DIVIDEND"):
        amount = action.get("amount")
        if amount is None:
            print(f"Warning: {action_type} action {action.get('action_id', '?')} missing amount; cannot derive impact", file=sys.stderr)
            return None
        try:
            amount_float = float(amount)
        except (TypeError, ValueError):
            print(f"Warning: invalid amount '{amount}' for action {action.get('action_id', '?')}", file=sys.stderr)
            return None
        if amount_float < 0:
            print(f"Warning: negative amount {amount_float} for action {action.get('action_id', '?')}", file=sys.stderr)
            return None
        impact["cash_adjustment"] = amount_float
        # price and share multipliers stay 1.0

    elif action_type in ("SYMBOL_CHANGE", "DELISTING", "SPINOFF", "MERGER"):
        # No automatic derivation; keep neutral multipliers.
        # For DELISTING, you might want share_multiplier = 0, but that is
        # a business decision best left to the consumer. We keep neutral.
        impact = {
            "price_multiplier": 1.0,
            "share_multiplier": 1.0,
            "cash_adjustment": 0.0,
        }
    else:
        print(f"Warning: unknown action_type '{action_type}' for action {action.get('action_id', '?')}; no impact derived", file=sys.stderr)
        return None

    return impact


def main():
    parser = argparse.ArgumentParser(description="Derive impact multipliers for corporate actions")
    parser.add_argument("--actions", default="actions.json", help="Path to actions.json")
    parser.add_argument("--output", default=None, help="Output file (defaults to overwrite input)")
    parser.add_argument("--dry-run", action="store_true", help="Show changes but do not write")
    args = parser.parse_args()

    # Load actions.json
    try:
        with open(args.actions, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {args.actions}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(2)

    actions = data.get("actions")
    if not isinstance(actions, list):
        print("Error: 'actions' key missing or not a list", file=sys.stderr)
        sys.exit(1)

    updated_count = 0
    error_count = 0

    for action in actions:
        impact = derive_impact(action)
        if impact is not None:
            action["impact"] = impact
            updated_count += 1
        else:
            error_count += 1

    # If errors occurred, we still output the partially updated file but exit with code 1
    if args.dry_run:
        # Print what would change
        print(json.dumps(data, indent=2))
        print(f"\nDry run: {updated_count} actions would have impact derived; {error_count} errors.")
        if error_count:
            sys.exit(1)
        sys.exit(0)

    output_path = args.output or args.actions
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Derived impact for {updated_count} actions.")
    if error_count:
        print(f"{error_count} actions could not be processed. See warnings above.", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
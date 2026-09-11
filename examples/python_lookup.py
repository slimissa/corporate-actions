#!/usr/bin/env python3
"""
Python Example: Querying the Corporate Actions Registry

This example demonstrates how to use the Python wrapper
(`corporate_actions_registry`) to load and query the Corporate Actions
Registry (actions.json).

Prerequisites:
    pip install corporate-actions-registry

    Or, from the repository root:
        pip install wrappers/python

Run:
    python examples/python_lookup.py
    python examples/python_lookup.py --isin US0378331005
    python examples/python_lookup.py --action-type DIVIDEND
    python examples/python_lookup.py --action-id US0378331005-DIVIDEND-2024-05-10-0.2500
    python examples/python_lookup.py --date-range 2020-01-01 2023-12-31

The script is intentionally verbose to show all lookup capabilities.
"""

import argparse
import os
import sys
from pathlib import Path

# Try to import the wrapper (installed) or add local path as fallback
try:
    from corporate_actions_registry import CorporateActionsRegistry
except ImportError:
    # Fallback: add wrappers/python to sys.path
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "wrappers" / "python"))
    from corporate_actions_registry import CorporateActionsRegistry


# ----------------------------------------------------------------------
# Locate actions.json
# ----------------------------------------------------------------------
def find_actions_file(cli_path: str = None) -> Path:
    """
    Resolve the path to actions.json.
    Priority:
      1. --actions CLI argument
      2. actions.json in the current working directory
      3. actions.json in the repository root (../actions.json)
    """
    if cli_path:
        p = Path(cli_path)
        if not p.exists():
            print(f"Error: file not found: {p}", file=sys.stderr)
            sys.exit(2)
        return p

    cwd_file = Path.cwd() / "actions.json"
    if cwd_file.exists():
        return cwd_file

    repo_file = Path(__file__).resolve().parents[1] / "actions.json"
    if repo_file.exists():
        return repo_file

    print("Error: could not find actions.json. Use --actions PATH.", file=sys.stderr)
    sys.exit(2)


# ----------------------------------------------------------------------
# Pretty printers
# ----------------------------------------------------------------------
def print_action(action) -> None:
    """Print a single action in a human-readable format."""
    print(f"  action_id:   {action.action_id}")
    print(f"  isin:        {action.isin}")
    print(f"  action_type: {action.action_type}")
    if action.ratio:
        print(f"  ratio:       {action.ratio}")
    if action.amount is not None:
        print(f"  amount:      {action.amount} {action.currency or ''}".rstrip())
    dates = action.dates
    if dates:
        if dates.announcement:
            print(f"  announced:   {dates.announcement}")
        if dates.ex_date:
            print(f"  ex_date:     {dates.ex_date}")
        if dates.record_date:
            print(f"  record_date: {dates.record_date}")
        if dates.effective_date:
            print(f"  effective:   {dates.effective_date}")
    if action.provenance and action.provenance.source_url:
        print(f"  source:      {action.provenance.source_url}")
    if action.impact:
        parts = []
        if action.impact.price_multiplier is not None:
            parts.append(f"price×{action.impact.price_multiplier}")
        if action.impact.share_multiplier is not None:
            parts.append(f"share×{action.impact.share_multiplier}")
        if action.impact.cash_adjustment is not None:
            parts.append(f"cash+{action.impact.cash_adjustment}")
        if parts:
            print(f"  impact:      {', '.join(parts)}")


def print_actions(actions, header: str) -> None:
    """Print a list of actions with a header."""
    if not actions:
        print(f"{header}: (none)")
        return
    print(f"{header}: {len(actions)} action(s)")
    for a in actions:
        print()
        print_action(a)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Query the Corporate Actions Registry using the Python wrapper."
    )
    parser.add_argument(
        "--actions",
        default=None,
        help="Path to actions.json (default: repo root actions.json)",
    )
    parser.add_argument(
        "--isin",
        default=None,
        help="Look up all actions for a given ISIN (e.g. US0378331005)",
    )
    parser.add_argument(
        "--action-id",
        default=None,
        help="Look up a single action by its unique action_id",
    )
    parser.add_argument(
        "--action-type",
        default=None,
        help="Filter by action type (SPLIT, DIVIDEND, SYMBOL_CHANGE, etc.)",
    )
    parser.add_argument(
        "--date-range",
        nargs=2,
        metavar=("START", "END"),
        default=None,
        help="Date range (inclusive) in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--date-field",
        default="ex_date",
        choices=["announcement", "ex_date", "record_date", "effective_date"],
        help="Which date field to filter on (default: ex_date)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print only counts, no details",
    )
    args = parser.parse_args()

    # Locate and load the registry
    actions_path = find_actions_file(args.actions)
    print(f"Loading registry from: {actions_path}")

    try:
        registry = CorporateActionsRegistry(str(actions_path))
    except Exception as e:
        print(f"Error loading registry: {e}", file=sys.stderr)
        return 1

    # Registry metadata
    meta = registry.meta
    print(f"  version:       {meta.version}")
    print(f"  source:        {meta.source}")
    print(f"  generated_at:  {meta.generated_at}")
    print(f"  total actions: {registry.count()}")
    print(f"  action types:  {', '.join(registry.all_action_types())}")
    print()

    # ------------------------------------------------------------------
    # If a specific query was requested, run it and exit.
    # ------------------------------------------------------------------
    if args.action_id:
        action = registry.by_action_id(args.action_id)
        if action is None:
            print(f"Action '{args.action_id}' not found.")
            return 0
        print_actions([action], f"Lookup by action_id '{args.action_id}'")
        return 0

    if args.isin:
        actions = registry.by_isin(args.isin)
        print_actions(actions, f"Lookup by ISIN '{args.isin}'")
        return 0

    if args.action_type:
        actions = registry.by_action_type(args.action_type)
        print_actions(actions, f"Lookup by action_type '{args.action_type}'")
        return 0

    if args.date_range:
        start, end = args.date_range
        actions = registry.by_date_range(start, end, args.date_field)
        print_actions(
            actions,
            f"Lookup by {args.date_field} between {start} and {end}",
        )
        return 0

    # ------------------------------------------------------------------
    # Default: print a summary of the registry
    # ------------------------------------------------------------------
    print("Registry summary by action type:")
    for action_type in registry.all_action_types():
        actions = registry.by_action_type(action_type)
        print(f"  {action_type}: {len(actions)}")

    print()
    print("First 3 actions (for illustration):")
    for action in registry.actions[:3]:
        print()
        print_action(action)

    if args.summary:
        return 0

    print()
    print("Use --isin, --action-id, --action-type, or --date-range for targeted queries.")
    print("Run with --help for full usage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""
Merge fetched corporate actions into actions.json.

Rejects three classes of additions:

  1. Exact duplicates — same (isin, action_type, ex_date, ratio, amount)
     as an action already in the registry.
  2. Deliberately removed actions — matched against the reject list
     (_removed_actions.json) by (isin, action_type_family, ex_date,
     amount), where action_type_family collapses DIVIDEND and
     SPECIAL_DIVIDEND (they describe the same cash event) and SPLIT and
     REVERSE_SPLIT.
  3. Semantic duplicates — same event under a different ID scheme,
     detected by tools.validate.validate_semantic_uniqueness.

The merge is atomic: if any error occurs, actions.json is not written.

Exit codes:
    0  merge succeeded (with or without additions)
    1  --strict mode and at least one action was rejected
    2  input or output error

Usage:
    python3 tools/merge_fetched.py \\
        --actions actions.json \\
        --fetched fetched_actions.json \\
        --removed _removed_actions.json \\
        [--strict] [--verbose] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The semantic-uniqueness layer lives in tools/validate.py. Import it
# if available; degrade to a no-op if the module is missing or broken,
# so this tool still works in isolation.
try:
    from tools.validate import validate_semantic_uniqueness
    _HAVE_SEMANTIC = True
except Exception:  # pragma: no cover - defensive
    _HAVE_SEMANTIC = False

    def validate_semantic_uniqueness(actions):  # type: ignore
        return []


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

def family(action_type: str | None) -> str:
    """Collapse related action types to a single family for matching.

    DIVIDEND and SPECIAL_DIVIDEND describe the same cash event; SPLIT
    and REVERSE_SPLIT describe the same share-count event. Any other
    type is its own family.
    """
    if action_type in ("DIVIDEND", "SPECIAL_DIVIDEND"):
        return "DIVIDEND"
    if action_type in ("SPLIT", "REVERSE_SPLIT"):
        return "SPLIT"
    return action_type or ""


def _amount(action: dict) -> float:
    """Return the action's amount as a rounded float, or 0.0."""
    raw = action.get("amount")
    if raw is None:
        return 0.0
    try:
        return round(float(raw), 4)
    except (TypeError, ValueError):
        raise SystemExit(
            f"Error: action {action.get('action_id', '?')} has "
            f"non-numeric amount {raw!r}"
        )


def fuzzy_key(action: dict) -> tuple:
    """Stable identity for an action across ID schemes."""
    dates = action.get("dates") or {}
    return (
        action.get("isin", ""),
        action.get("action_type", ""),
        dates.get("ex_date", ""),
        action.get("ratio") or "",
        _amount(action),
    )


def reject_key(action: dict) -> tuple:
    """Match key for the reject list. Uses the action-type family so a
    removed DIVIDEND and a re-fetched SPECIAL_DIVIDEND at the same
    (isin, ex_date, amount) are recognized as the same event."""
    dates = action.get("dates") or {}
    return (
        action.get("isin", ""),
        family(action.get("action_type")),
        dates.get("ex_date", ""),
        _amount(action),
    )


def reject_key_from_entry(entry: dict) -> tuple:
    """Build a reject key from a _removed_actions.json entry."""
    return (
        entry.get("isin", ""),
        family(entry.get("action_type")),
        entry.get("ex_date", ""),
        round(float(entry.get("amount") or 0.0), 4),
    )


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(2)


def load_reject_set(path: Path) -> set[tuple]:
    """Load the reject list. Missing or malformed file yields an empty
    set, since the reject list is optional."""
    if not path.is_file():
        return set()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(
            f"Warning: {path} is not valid JSON ({e}); "
            f"continuing without the reject list.",
            file=sys.stderr,
        )
        return set()
    removed = doc.get("removed")
    if not isinstance(removed, list):
        print(
            f"Warning: {path} has no 'removed' list; "
            f"continuing without the reject list.",
            file=sys.stderr,
        )
        return set()
    return {reject_key_from_entry(e) for e in removed if isinstance(e, dict)}


def _write_atomic(path: Path, payload: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def merge(
    current_actions: list[dict],
    fetched_actions: list[dict],
    reject_set: set[tuple],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (added, rejected_removed, rejected_semantic).

    Order of checks per candidate:
      1. exact-duplicate (fuzzy_key already seen)
      2. reject list
      3. semantic uniqueness against the growing accepted list
    """
    existing_keys = {fuzzy_key(a) for a in current_actions}
    added: list[dict] = []
    rejected_removed: list[dict] = []
    rejected_semantic: list[dict] = []

    working = list(current_actions)

    for candidate in fetched_actions:
        k = fuzzy_key(candidate)
        if k in existing_keys:
            continue

        rk = reject_key(candidate)
        if rk in reject_set:
            rejected_removed.append(candidate)
            continue

        # Semantic check: append candidate to a trial list and see if
        # the layer flags it against anything already accepted.
        if _HAVE_SEMANTIC and added:
            trial = working + [candidate]
            errors = validate_semantic_uniqueness(trial)
            if errors:
                rejected_semantic.append(candidate)
                continue

        working.append(candidate)
        existing_keys.add(k)
        added.append(candidate)

    return added, rejected_removed, rejected_semantic


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description="Merge fetched corporate actions into actions.json."
    )
    p.add_argument("--actions", required=True,
                   help="Path to actions.json")
    p.add_argument("--fetched", required=True,
                   help="Path to fetched_actions.json")
    p.add_argument("--removed", default="_removed_actions.json",
                   help="Path to the reject list "
                        "(default: _removed_actions.json)")
    p.add_argument("--strict", action="store_true",
                   help="Exit 1 if any fetched action was rejected")
    p.add_argument("--verbose", action="store_true",
                   help="Print each added and rejected action")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute the merge but do not write actions.json")
    args = p.parse_args()

    actions_path = Path(args.actions)
    fetched_path = Path(args.fetched)
    removed_path = Path(args.removed)

    current = load_json(actions_path)
    fetched = load_json(fetched_path)

    current_actions = current.get("actions")
    if not isinstance(current_actions, list):
        print(f"Error: {actions_path} has no 'actions' list",
              file=sys.stderr)
        return 2

    fetched_actions = fetched.get("actions")
    if not isinstance(fetched_actions, list):
        print(f"Error: {fetched_path} has no 'actions' list",
              file=sys.stderr)
        return 2

    reject_set = load_reject_set(removed_path)

    added, rejected_removed, rejected_semantic = merge(
        current_actions, fetched_actions, reject_set,
    )

    if args.verbose:
        for a in added[:20]:
            print(f"  + {a.get('action_id', '?')}")
        if len(added) > 20:
            print(f"  ... and {len(added) - 20} more added")
        for a in rejected_removed:
            print(f"  x rejected (reject list): {a.get('action_id', '?')}")
        for a in rejected_semantic:
            print(f"  x rejected (semantic dup): {a.get('action_id', '?')}")

    # Build the new registry document.
    if added:
        current["actions"] = current_actions + added
        current.setdefault("meta", {})["updated_at"] = (
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        )

    if not args.dry_run and added:
        _write_atomic(
            actions_path,
            json.dumps(current, indent=2, ensure_ascii=False) + "\n",
        )

    # Summary.
    verb = "would add" if args.dry_run else "added"
    print(f"{verb.capitalize()} {len(added)} action(s); "
          f"total {len(current.get('actions', current_actions))}.")
    if rejected_removed:
        print(f"Rejected {len(rejected_removed)} action(s) on the reject list.")
    if rejected_semantic:
        print(f"Rejected {len(rejected_semantic)} semantic duplicate(s).")

    if not _HAVE_SEMANTIC:
        print(
            "Note: semantic-uniqueness layer unavailable; only exact and "
            "reject-list checks ran.",
            file=sys.stderr,
        )

    if args.strict and (rejected_removed or rejected_semantic):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
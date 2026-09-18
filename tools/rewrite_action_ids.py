#!/usr/bin/env python3
"""
One-shot: rewrite every action_id in actions.json to the canonical format.

Canonical format
----------------
    {isin}-{action_type}-{effective_date}-{discriminator}

Discriminators, one per action type:

    SPLIT / REVERSE_SPLIT / SPINOFF : ratio with ':' replaced by '-'
                                       "10:1" -> "10-1"
                                       "1:8"  -> "1-8"
    DIVIDEND / SPECIAL_DIVIDEND     : amount as f"{amount:.4f}"
                                       0.25     -> "0.2500"
                                       0.001875 -> "0.0019"
    SYMBOL_CHANGE                   : literal "SYMBOL"
    DELISTING                       : literal "DELISTED"
    MERGER                          : rejected — must not appear in v1.0.0

Safety
------
* Refuses to write if any two actions would collide after rewriting.
  Collisions mean the source data contains semantic duplicates that
  must be resolved first. The script prints both sides of each collision
  with their old action_id, provenance.source, and
  provenance.verification_source, so the weaker entry is obvious.
* Writes a timestamped backup next to actions.json before overwriting.
* Idempotent: running twice is a no-op on the second run.
* Does not touch meta.updated_at. If you want the rewrite reflected in
  the registry's timestamp, bump it manually in the same commit.

Usage
-----
    python3 tools/rewrite_action_ids.py --dry-run
    python3 tools/rewrite_action_ids.py
    python3 tools/rewrite_action_ids.py --actions path/to/actions.json
    python3 tools/rewrite_action_ids.py --quiet

After a successful rewrite, run:

    python3 -m pytest tests/test_schema_full.py -v

Exit codes
----------
    0 — success, or no-op (all IDs already canonical)
    1 — collision detected, or invalid action content
    2 — file not found / unreadable / invalid JSON
    3 — write failed
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ACTIONS_PATH = REPO_ROOT / "actions.json"

# How many old -> new pairs to print before truncating. The full count is
# still reported. Set high enough that the AAPL-scale registry shows
# everything, low enough that a 5,000-action registry does not flood CI.
MAX_DIFF_SHOWN = 100

# Canonical ID shape, after rewrite. Used as a defensive check that the
# discriminator builder did not produce something unexpected.
CANONICAL_RE = re.compile(
    r"^"
    r"(?P<isin>[A-Z]{2}[A-Z0-9]{9}[0-9])"
    r"-"
    r"(?P<type>[A-Z_]+)"
    r"-"
    r"(?P<date>\d{4}-\d{2}-\d{2})"
    r"-"
    r"(?P<disc>.+)"
    r"$"
)


class RewriteError(Exception):
    """Raised when a single action cannot be canonicalized.

    Signals a content-level problem, not a file-system problem. The
    caller aborts the rewrite without writing anything.
    """


# ---------------------------------------------------------------------------
# Discriminator and ID construction
# ---------------------------------------------------------------------------

def discriminator(action: Dict[str, Any]) -> str:
    """Return the discriminator suffix for one action.

    Raises RewriteError if the action lacks the fields its type requires,
    or if the type is not supported in v1.0.0.
    """
    action_type = action.get("action_type")
    action_id = action.get("action_id", "<no action_id>")

    if action_type in ("SPLIT", "REVERSE_SPLIT", "SPINOFF"):
        ratio = action.get("ratio")
        if not isinstance(ratio, str) or ":" not in ratio:
            raise RewriteError(
                f"{action_id}: {action_type} requires a ratio of the form "
                f"N:M, got {ratio!r}"
            )
        num_s, _, den_s = ratio.partition(":")
        if not (num_s.isdigit() and den_s.isdigit()):
            raise RewriteError(
                f"{action_id}: ratio {ratio!r} is not two positive integers"
            )
        num, den = int(num_s), int(den_s)
        if num <= 0 or den <= 0:
            raise RewriteError(
                f"{action_id}: ratio parts must be positive, got {ratio!r}"
            )
        # Normalize leading zeros ("010:1" -> "10-1").
        return f"{num}-{den}"

    if action_type in ("DIVIDEND", "SPECIAL_DIVIDEND"):
        amount = action.get("amount")
        if amount is None:
            raise RewriteError(
                f"{action_id}: {action_type} requires an amount"
            )
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            raise RewriteError(
                f"{action_id}: amount must be numeric, got "
                f"{type(amount).__name__}"
            )
        # Four decimal places, matching the format produced by
        # tools/fetch_yahoo_actions.py. Keep this in sync if that
        # fetcher ever changes its formatting.
        return f"{float(amount):.4f}"

    if action_type == "SYMBOL_CHANGE":
        return "SYMBOL"

    if action_type == "DELISTING":
        return "DELISTED"

    if action_type == "MERGER":
        raise RewriteError(
            f"{action_id}: MERGER is rejected by the v1.0.0 validator and "
            f"must not appear in actions.json"
        )

    raise RewriteError(
        f"{action_id}: unsupported action_type {action_type!r}"
    )


def build_canonical_id(action: Dict[str, Any]) -> str:
    """Build the canonical action_id from an action's content.

    Raises RewriteError on any missing field or unsupported type.
    """
    action_id = action.get("action_id", "<no action_id>")

    isin = action.get("isin")
    if not isinstance(isin, str) or not isin:
        raise RewriteError(f"{action_id}: missing or invalid isin")

    action_type = action.get("action_type")
    if not isinstance(action_type, str) or not action_type:
        raise RewriteError(f"{action_id}: missing or invalid action_type")

    dates = action.get("dates")
    if not isinstance(dates, dict):
        raise RewriteError(
            f"{action_id}: dates must be an object, got "
            f"{type(dates).__name__}"
        )

    effective = dates.get("effective_date")
    if not isinstance(effective, str) or not effective:
        raise RewriteError(
            f"{action_id}: missing or invalid dates.effective_date"
        )

    new_id = f"{isin}-{action_type}-{effective}-{discriminator(action)}"

    # Defensive sanity check. If the discriminator builder drifts, this
    # catches it before we hand the value to the file.
    if not CANONICAL_RE.match(new_id):
        raise RewriteError(
            f"{action_id}: produced an id that does not match the "
            f"canonical shape: {new_id!r}"
        )

    return new_id


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def load_actions(path: Path) -> Dict[str, Any]:
    """Load and structurally check actions.json. Exits on failure."""
    if not path.is_file():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(2)

    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        print(f"Error: cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {path}: {exc}", file=sys.stderr)
        sys.exit(2)

    if not isinstance(data, dict) or not isinstance(data.get("actions"), list):
        print(
            f"Error: {path} must contain an object with an 'actions' array",
            file=sys.stderr,
        )
        sys.exit(2)

    return data


# ---------------------------------------------------------------------------
# Collision detection
# ---------------------------------------------------------------------------

def report_collisions(
    actions: List[Dict[str, Any]],
    new_ids: List[str],
) -> int:
    """Print any canonical-ID collisions. Returns the count.

    Two actions with the same ISIN, type, effective_date, and
    discriminator are semantic duplicates regardless of how their old
    IDs were spelled. That is the class of problem this function
    surfaces.
    """
    buckets: Dict[str, List[int]] = defaultdict(list)
    for i, aid in enumerate(new_ids):
        buckets[aid].append(i)

    collisions = {aid: idxs for aid, idxs in buckets.items() if len(idxs) > 1}

    if not collisions:
        return 0

    print(
        "Error: cannot rewrite — the following actions would collide.\n"
        "Resolve these in actions.json first, then re-run.\n"
        "The colliding entries are semantic duplicates: same isin,\n"
        "action_type, effective_date, and discriminator.\n",
        file=sys.stderr,
    )

    for aid in sorted(collisions):
        idxs = collisions[aid]
        print(f"  canonical id:  {aid}", file=sys.stderr)
        for i in idxs:
            action = actions[i]
            provenance = action.get("provenance") or {}
            source = provenance.get("source") or "(no source)"
            verification = provenance.get("verification_source")
            record_date = (action.get("dates") or {}).get("record_date")
            print(
                f"      [{i:3d}] old_id={action.get('action_id', '?')!r}",
                file=sys.stderr,
            )
            print(f"             source={source!r}", file=sys.stderr)
            print(
                f"             verification_source={verification!r}",
                file=sys.stderr,
            )
            print(
                f"             record_date={record_date!r}",
                file=sys.stderr,
            )
        print(file=sys.stderr)

    print(
        "To resolve: keep the entry with stronger provenance "
        "(a non-null verification_source, a primary-source URL, and a "
        "populated record_date), delete the other, and re-run this "
        "script.",
        file=sys.stderr,
    )
    return len(collisions)


# ---------------------------------------------------------------------------
# Main rewrite
# ---------------------------------------------------------------------------

def rewrite(
    actions_path: Path,
    *,
    dry_run: bool = False,
    quiet: bool = False,
) -> int:
    """Rewrite action_ids in the given file. Returns an exit code."""
    data = load_actions(actions_path)
    actions: List[Dict[str, Any]] = data["actions"]

    # Pass 1 — compute new IDs. Any content error aborts before we
    # touch the file.
    new_ids: List[str] = []
    for action in actions:
        try:
            new_ids.append(build_canonical_id(action))
        except RewriteError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    # Pass 2 — collision detection. Aborts before writing.
    if report_collisions(actions, new_ids):
        return 1

    # Pass 3 — compute the diff without mutating anything yet.
    changes: List[Tuple[int, str, str]] = []
    for i, action in enumerate(actions):
        old_id = action.get("action_id", "")
        new_id = new_ids[i]
        if old_id != new_id:
            changes.append((i, old_id, new_id))

    if not quiet:
        if not changes:
            print(
                f"No changes needed. "
                f"All {len(actions)} action_ids are already canonical."
            )
        else:
            shown = changes[:MAX_DIFF_SHOWN]
            for i, old, new in shown:
                print(f"  [{i:3d}] {old}")
                print(f"         -> {new}")
            if len(changes) > MAX_DIFF_SHOWN:
                print(
                    f"  ... and {len(changes) - MAX_DIFF_SHOWN} more "
                    f"(increase MAX_DIFF_SHOWN to see all)"
                )
            print()
            print(f"{len(changes)} of {len(actions)} action_ids changed.")

    if dry_run:
        print("Dry run — nothing written.")
        return 0

    if not changes:
        return 0

    # Backup before mutating.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = actions_path.with_name(actions_path.name + f".{stamp}.bak")
    try:
        shutil.copy2(actions_path, backup)
    except OSError as exc:
        print(f"Error: cannot write backup {backup}: {exc}", file=sys.stderr)
        return 3

    if not quiet:
        print(f"\nBackup written: {backup}")

    # Apply.
    for i, _, new_id in changes:
        actions[i]["action_id"] = new_id

    # Write atomically: temp file, then replace.
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp = actions_path.with_suffix(actions_path.suffix + ".tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(actions_path)
    except OSError as exc:
        print(f"Error: write failed: {exc}", file=sys.stderr)
        # Best-effort cleanup.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return 3

    print(f"Wrote {len(changes)} updated action_id(s) to {actions_path}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rewrite action_id values in actions.json to canonical form. "
            "The script aborts on collision and writes a timestamped "
            "backup before modifying the file."
        )
    )
    parser.add_argument(
        "--actions",
        type=Path,
        default=DEFAULT_ACTIONS_PATH,
        help=(
            f"Path to actions.json "
            f"(default: {DEFAULT_ACTIONS_PATH})"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the diff without modifying the file.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the per-action diff output. Errors still print.",
    )
    args = parser.parse_args(argv)

    return rewrite(
        args.actions.resolve(),
        dry_run=args.dry_run,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""One-shot: replace the two known duplicate pairs in actions.json.

Pair A — AAPL Q2 FY2024 dividend:
    Removes:
        US0378331005-DIVIDEND-2024-05-23-0.2500   (wrong ex_date)
        US0378331005-DIVIDEND-2024-05-10-0.2500   (wrong announcement/record)
    Adds:
        US0378331005-DIVIDEND-2024-05-16-0.2500   (corrected)

    Primary source:
    https://www.apple.com/newsroom/2024/05/apple-reports-second-quarter-results/

Pair B — MSFT Q4 2004 dual dividend:
    Removes:
        US5949181045-DIVIDEND-2004-11-15-3.0800   (Yahoo bundled 0.08+3.00)
        US5949181045-SPECIAL_DIVIDEND-2004-12-03-3.0000  (wrong payment date)
    Adds:
        US5949181045-DIVIDEND-2004-12-09-0.0800          (regular, corrected)
        US5949181045-SPECIAL_DIVIDEND-2004-12-02-3.0000  (special, corrected)

    Primary source:
    https://news.microsoft.com/2004/11/15/microsoft-declares-quarterly-dividend-and-special-dividend/

Run:
    python3 scripts/fix_duplicates.py

Writes a backup to actions.json.bak-<UTC timestamp> before overwriting.
Idempotent: safe to re-run, prints "already applied" and exits 0.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ACTIONS_PATH = REPO_ROOT / "actions.json"

REMOVE_IDS = {
    "US0378331005-DIVIDEND-2024-05-23-0.2500",
    "US0378331005-DIVIDEND-2024-05-10-0.2500",
    "US5949181045-DIVIDEND-2004-11-15-3.0800",
    "US5949181045-SPECIAL_DIVIDEND-2004-12-03-3.0000",
}

ADD_ENTRIES = [
    {
        "isin": "US0378331005",
        "action_id": "US0378331005-DIVIDEND-2024-05-16-0.2500",
        "action_type": "DIVIDEND",
        "amount": 0.25,
        "currency": "USD",
        "dates": {
            "announcement": "2024-05-02",
            "ex_date": "2024-05-10",
            "record_date": "2024-05-13",
            "effective_date": "2024-05-16",
        },
        "status": "COMPLETED",
        "provenance": {
            "source": "Apple Inc. press release",
            "source_url": "https://www.apple.com/newsroom/2024/05/apple-reports-second-quarter-results/",
            "verification_source": "SEC EDGAR 8-K",
            "verification_url": None,
        },
    },
    {
        "isin": "US5949181045",
        "action_id": "US5949181045-DIVIDEND-2004-12-09-0.0800",
        "action_type": "DIVIDEND",
        "amount": 0.08,
        "currency": "USD",
        "dates": {
            "announcement": "2004-11-15",
            "ex_date": "2004-11-15",
            "record_date": "2004-11-17",
            "effective_date": "2004-12-09",
        },
        "status": "COMPLETED",
        "provenance": {
            "source": "Microsoft press release",
            "source_url": "https://news.microsoft.com/2004/11/15/microsoft-declares-quarterly-dividend-and-special-dividend/",
            "verification_source": "SEC EDGAR 8-K",
            "verification_url": None,
        },
    },
    {
        "isin": "US5949181045",
        "action_id": "US5949181045-SPECIAL_DIVIDEND-2004-12-02-3.0000",
        "action_type": "SPECIAL_DIVIDEND",
        "amount": 3.00,
        "currency": "USD",
        "dates": {
            "announcement": "2004-11-15",
            "ex_date": "2004-11-17",
            "record_date": "2004-11-19",
            "effective_date": "2004-12-02",
        },
        "status": "COMPLETED",
        "provenance": {
            "source": "Microsoft press release",
            "source_url": "https://news.microsoft.com/2004/11/15/microsoft-declares-quarterly-dividend-and-special-dividend/",
            "verification_source": "SEC EDGAR 8-K",
            "verification_url": None,
        },
    },
]


def main() -> int:
    if not ACTIONS_PATH.is_file():
        print(f"Error: {ACTIONS_PATH} not found", file=sys.stderr)
        return 2

    doc = json.loads(ACTIONS_PATH.read_text(encoding="utf-8"))
    actions = doc.get("actions")
    if not isinstance(actions, list):
        print("Error: actions.json has no 'actions' list", file=sys.stderr)
        return 2

    before_count = len(actions)
    existing_ids = {a.get("action_id") for a in actions}

    # Idempotence: if every new entry already exists and no removed entry exists,
    # there is nothing to do.
    removed_present = REMOVE_IDS & existing_ids
    added_missing = [e for e in ADD_ENTRIES if e["action_id"] not in existing_ids]

    if not removed_present and not added_missing:
        print(f"Already applied. {before_count} actions, no changes needed.")
        return 0

    print(f"Before: {before_count} actions")
    print(f"  Removing {len(removed_present)} known-duplicate action(s):")
    for aid in sorted(removed_present):
        print(f"    - {aid}")
    print(f"  Adding {len(added_missing)} corrected action(s):")
    for entry in added_missing:
        print(f"    + {entry['action_id']}")

    # Backup
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = ACTIONS_PATH.with_name(f"actions.json.bak-{stamp}")
    shutil.copy2(ACTIONS_PATH, backup)
    print(f"  Backup: {backup.name}")

    # Apply: filter then extend
    new_actions = [a for a in actions if a.get("action_id") not in REMOVE_IDS]
    new_actions.extend(added_missing)

    doc["actions"] = new_actions
    ACTIONS_PATH.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"After:  {len(new_actions)} actions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
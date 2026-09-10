#!/usr/bin/env python3
"""
Build Distribution Artifacts for Corporate Actions Registry

Reads actions.json and generates:
  - actions.dist.json  (pretty-printed, with metadata)
  - actions.min.json   (minified, no extra whitespace)
  - actions.csv        (flat CSV of all actions)
  - actions.sql        (SQLite-compatible SQL dump)

All output files are written to the same directory as actions.json
or to a user-specified output directory.

Usage:
    python tools/build.py [--actions actions.json] [--output-dir dist/]

Exit codes:
  0 - success
  1 - validation errors (missing required fields, no actions)
  2 - file not found or invalid JSON
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def load_actions(path: str) -> Dict[str, Any]:
    """Load actions.json and return parsed dict."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(2)


def validate_actions_data(data: Dict[str, Any]) -> List[str]:
    """Basic structural validation before building artifacts."""
    errors = []
    if not isinstance(data, dict):
        errors.append("Top-level JSON must be an object")
        return errors

    if "actions" not in data:
        errors.append("Missing 'actions' key")
        return errors

    actions = data["actions"]
    if not isinstance(actions, list):
        errors.append("'actions' must be a list")
        return errors

    if len(actions) == 0:
        errors.append("'actions' list is empty")

    required_fields = ["isin", "action_id", "action_type", "dates"]
    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            errors.append(f"Action at index {i} is not an object")
            continue
        for field in required_fields:
            if field not in action:
                errors.append(f"Action {i} missing required field '{field}'")
        # Check dates object
        dates = action.get("dates")
        if isinstance(dates, dict):
            if "announcement" not in dates or "effective_date" not in dates:
                errors.append(f"Action {i} dates missing announcement or effective_date")
        else:
            errors.append(f"Action {i} 'dates' must be an object")
    return errors


def flatten_action(action: Dict[str, Any]) -> Dict[str, Any]:
    """Convert nested action dict to flat dict suitable for CSV/SQL."""
    flat = {}
    for key, value in action.items():
        if isinstance(value, dict):
            # Flatten nested dicts with underscore prefix
            for subkey, subvalue in value.items():
                flat[f"{key}_{subkey}"] = subvalue
        else:
            flat[key] = value
    return flat


def build_dist(data: Dict[str, Any], output_path: str) -> None:
    """Write pretty-printed distribution JSON."""
    dist_data = dict(data)
    # Add build metadata
    dist_data["meta"] = dict(dist_data.get("meta", {}))
    dist_data["meta"]["build_timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(dist_data, f, indent=2, ensure_ascii=False)
    print(f"Created {output_path}")


def build_minified(data: Dict[str, Any], output_path: str) -> None:
    """Write minified JSON."""
    min_data = dict(data)
    min_data["meta"] = dict(min_data.get("meta", {}))
    min_data["meta"]["build_timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(min_data, f, separators=(',', ':'), ensure_ascii=False)
    print(f"Created {output_path}")


def build_csv(data: Dict[str, Any], output_path: str) -> None:
    """Write CSV export (flattened actions)."""
    actions = data.get("actions", [])
    if not actions:
        print("No actions to export to CSV", file=sys.stderr)
        return

    # Get all possible columns from first few actions to maintain order
    all_keys = []
    for action in actions[:10]:
        flat = flatten_action(action)
        for key in flat.keys():
            if key not in all_keys:
                all_keys.append(key)

    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=all_keys, extrasaction='ignore')
        writer.writeheader()
        for action in actions:
            flat = flatten_action(action)
            writer.writerow(flat)
    print(f"Created {output_path}")


def build_sql(data: Dict[str, Any], output_path: str) -> None:
    """Write SQLite-compatible SQL dump."""
    actions = data.get("actions", [])
    if not actions:
        print("No actions to export to SQL", file=sys.stderr)
        return

    # Open SQLite in-memory to use proper escaping? Simpler to manually build.
    # We'll create a single table 'corporate_actions' with common columns.
    sql_lines = []
    sql_lines.append("-- Corporate Actions Registry SQL Dump")
    sql_lines.append(f"-- Generated: {datetime.now(timezone.utc).isoformat()}")
    sql_lines.append("BEGIN TRANSACTION;")
    sql_lines.append("DROP TABLE IF EXISTS corporate_actions;")
    sql_lines.append("""
CREATE TABLE corporate_actions (
    action_id TEXT PRIMARY KEY,
    isin TEXT NOT NULL,
    action_type TEXT NOT NULL,
    announcement_date TEXT,
    ex_date TEXT,
    record_date TEXT,
    effective_date TEXT,
    ratio TEXT,
    amount REAL,
    currency TEXT,
    status TEXT,
    source TEXT,
    source_url TEXT,
    verification_source TEXT,
    price_multiplier REAL,
    share_multiplier REAL,
    cash_adjustment REAL
);
""".strip())

    for action in actions:
        action_id = action.get("action_id", "")
        isin = action.get("isin", "")
        action_type = action.get("action_type", "")
        dates = action.get("dates", {})
        provenance = action.get("provenance", {})
        impact = action.get("impact", {})

        announcement = dates.get("announcement", "")
        ex_date = dates.get("ex_date", "")
        record_date = dates.get("record_date", "")
        effective_date = dates.get("effective_date", "")
        ratio = action.get("ratio", "")
        amount = action.get("amount", None)
        currency = action.get("currency", "")
        status = action.get("status", "")
        source = provenance.get("source", "")
        source_url = provenance.get("source_url", "")
        verification_source = provenance.get("verification_source", "")
        price_mult = impact.get("price_multiplier", None)
        share_mult = impact.get("share_multiplier", None)
        cash_adj = impact.get("cash_adjustment", None)

        # Escape single quotes
        def esc(val):
            if val is None:
                return "NULL"
            if isinstance(val, (int, float)):
                return str(val)
            return "'" + str(val).replace("'", "''") + "'"

        values = [
            esc(action_id), esc(isin), esc(action_type),
            esc(announcement), esc(ex_date), esc(record_date), esc(effective_date),
            esc(ratio), esc(amount), esc(currency), esc(status),
            esc(source), esc(source_url), esc(verification_source),
            esc(price_mult), esc(share_mult), esc(cash_adj)
        ]
        sql_lines.append("INSERT INTO corporate_actions VALUES (" + ", ".join(values) + ");")

    sql_lines.append("COMMIT;")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(sql_lines))
    print(f"Created {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Build distribution artifacts for Corporate Actions Registry")
    parser.add_argument("--actions", default="actions.json", help="Path to actions.json")
    parser.add_argument("--output-dir", default=None, help="Directory for output files (defaults to same dir as actions.json)")
    args = parser.parse_args()

    actions_path = args.actions
    data = load_actions(actions_path)

    # Validate basic structure
    errors = validate_actions_data(data)
    if errors:
        print("Validation errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    # Determine output directory
    if args.output_dir:
        out_dir = args.output_dir
        os.makedirs(out_dir, exist_ok=True)
    else:
        out_dir = os.path.dirname(os.path.abspath(actions_path)) or "."

    base = os.path.splitext(os.path.basename(actions_path))[0]  # "actions"

    dist_path = os.path.join(out_dir, f"{base}.dist.json")
    min_path = os.path.join(out_dir, f"{base}.min.json")
    csv_path = os.path.join(out_dir, f"{base}.csv")
    sql_path = os.path.join(out_dir, f"{base}.sql")

    build_dist(data, dist_path)
    build_minified(data, min_path)
    build_csv(data, csv_path)
    build_sql(data, sql_path)

    print("Build completed successfully.")


if __name__ == "__main__":
    main()
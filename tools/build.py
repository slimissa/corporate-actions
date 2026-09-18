#!/usr/bin/env python3
"""
Build Distribution Artifacts for Corporate Actions Registry

Reads actions.json and generates five artifacts:

  actions.dist.json       Pretty-printed JSON.
  actions.min.json        Minified JSON.
  actions.csv             Flat CSV, one row per action.
  actions.sql             SQLite-compatible SQL dump.
  actions.meta.json       Build metadata (timestamp only).

Determinism
-----------
The first four files are byte-identical across runs on identical input.
The only source of variation between runs is actions.meta.json, whose
build_timestamp changes per run. This makes the primary artifacts safe
to check into a repository or diff in CI.

Usage:
    python tools/build.py [--actions actions.json] [--output-dir dist/]

Exit codes:
  0 - success
  1 - structural validation error (missing required fields, empty list)
  2 - file not found, invalid JSON, or I/O error during write
"""

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def load_actions(path: str) -> Dict[str, Any]:
    """Load actions.json, tolerating a UTF-8 BOM.

    Exits 2 on any load failure.
    """
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(2)


def validate_actions_data(data: Dict[str, Any]) -> List[str]:
    """Structural validation before building artifacts.

    Returns a list of error strings. Does not exit.
    """
    errors: List[str] = []

    if not isinstance(data, dict):
        return ["top-level JSON must be an object"]

    if "actions" not in data:
        return ["missing 'actions' key"]

    actions = data["actions"]
    if not isinstance(actions, list):
        return ["'actions' must be a list"]

    if len(actions) == 0:
        errors.append("'actions' list is empty")

    required_fields = ("isin", "action_id", "action_type", "dates")
    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            errors.append(f"action at index {i} is not an object")
            continue
        for field in required_fields:
            if field not in action:
                errors.append(f"action {i} missing required field {field!r}")
        dates = action.get("dates")
        if not isinstance(dates, dict):
            errors.append(f"action {i} 'dates' must be an object")
        else:
            for required_date in ("announcement", "effective_date"):
                if required_date not in dates:
                    errors.append(
                        f"action {i} dates missing {required_date!r}"
                    )

    return errors


def flatten_action(action: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten a nested action dict to a flat dict for CSV.

    Nested dicts are flattened one level with an underscore separator:
        {"dates": {"ex_date": "..."}} -> {"dates_ex_date": "..."}

    A nested dict inside a nested dict, and any list value, raise
    ValueError. This is deliberate: a CSV cell cannot hold a structured
    value, and silently embedding Python repr() would produce a file that
    looks correct but is not round-trippable.
    """
    flat: Dict[str, Any] = {}
    for key, value in action.items():
        if isinstance(value, dict):
            for subkey, subvalue in value.items():
                if isinstance(subvalue, (dict, list)):
                    raise ValueError(
                        f"flatten_action: cannot flatten {key}.{subkey} "
                        f"(got {type(subvalue).__name__}); "
                        f"only one level of nesting is supported"
                    )
                flat[f"{key}_{subkey}"] = subvalue
        elif isinstance(value, list):
            raise ValueError(
                f"flatten_action: cannot flatten list at {key!r}; "
                f"lists are not representable in a flat CSV row"
            )
        else:
            flat[key] = value
    return flat


def _write_atomic(path: Path, payload: str) -> None:
    """Write payload to path via a temp file and rename.

    A killed process between the two steps leaves the original file
    untouched rather than truncated.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def build_dist(data: Dict[str, Any], output_path: Path) -> None:
    """Write pretty-printed distribution JSON.

    Deterministic: no timestamp is added here. See build_meta_sidecar.
    """
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    _write_atomic(output_path, payload)
    print(f"Created {output_path}")


def build_minified(data: Dict[str, Any], output_path: Path) -> None:
    """Write minified JSON. Deterministic."""
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n"
    _write_atomic(output_path, payload)
    print(f"Created {output_path}")


def build_csv(data: Dict[str, Any], output_path: Path) -> None:
    """Write a flat CSV, one row per action.

    Columns are collected from every action, then sorted alphabetically
    for deterministic ordering. Every key present on any action appears
    as a column; no key is silently dropped.
    """
    actions = data.get("actions", [])
    if not actions:
        print("No actions to export to CSV", file=sys.stderr)
        return

    flat_actions: List[Dict[str, Any]] = [flatten_action(a) for a in actions]
    columns = sorted({k for flat in flat_actions for k in flat.keys()})

    buf = io.StringIO()
    # lineterminator defaults to '\r\n', matching RFC 4180.
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="raise")
    writer.writeheader()
    for flat in flat_actions:
        writer.writerow(flat)

    _write_atomic(output_path, buf.getvalue())
    print(f"Created {output_path}")


def _sql_escape(value: Any) -> str:
    """Return a SQL literal for a scalar value."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        # SQLite has no boolean type; store as 0 or 1.
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def build_sql(data: Dict[str, Any], output_path: Path) -> None:
    """Write a SQLite-compatible SQL dump.

    The table has a fixed schema. A field present on an action but not
    in this table is not exported here; the CSV is the complete export.
    """
    actions = data.get("actions", [])
    if not actions:
        print("No actions to export to SQL", file=sys.stderr)
        return

    lines: List[str] = []
    lines.append("-- Corporate Actions Registry SQL Dump")
    lines.append("-- Generated by tools/build.py")
    lines.append("BEGIN TRANSACTION;")
    lines.append("DROP TABLE IF EXISTS corporate_actions;")
    lines.append(
        "CREATE TABLE corporate_actions (\n"
        "    action_id TEXT PRIMARY KEY,\n"
        "    isin TEXT NOT NULL,\n"
        "    action_type TEXT NOT NULL,\n"
        "    announcement_date TEXT,\n"
        "    ex_date TEXT,\n"
        "    record_date TEXT,\n"
        "    effective_date TEXT,\n"
        "    ratio TEXT,\n"
        "    amount REAL,\n"
        "    currency TEXT,\n"
        "    status TEXT,\n"
        "    source TEXT,\n"
        "    source_url TEXT,\n"
        "    verification_source TEXT,\n"
        "    price_multiplier REAL,\n"
        "    share_multiplier REAL,\n"
        "    cash_adjustment REAL\n"
        ");"
    )

    for action in actions:
        dates = action.get("dates") or {}
        provenance = action.get("provenance") or {}
        impact = action.get("impact") or {}
        values = [
            _sql_escape(action.get("action_id", "")),
            _sql_escape(action.get("isin", "")),
            _sql_escape(action.get("action_type", "")),
            _sql_escape(dates.get("announcement")),
            _sql_escape(dates.get("ex_date")),
            _sql_escape(dates.get("record_date")),
            _sql_escape(dates.get("effective_date")),
            _sql_escape(action.get("ratio")),
            _sql_escape(action.get("amount")),
            _sql_escape(action.get("currency")),
            _sql_escape(action.get("status")),
            _sql_escape(provenance.get("source")),
            _sql_escape(provenance.get("source_url")),
            _sql_escape(provenance.get("verification_source")),
            _sql_escape(impact.get("price_multiplier")),
            _sql_escape(impact.get("share_multiplier")),
            _sql_escape(impact.get("cash_adjustment")),
        ]
        lines.append(
            "INSERT INTO corporate_actions VALUES (" + ", ".join(values) + ");"
        )

    lines.append("COMMIT;")
    _write_atomic(output_path, "\n".join(lines) + "\n")
    print(f"Created {output_path}")


def build_meta_sidecar(output_path: Path) -> None:
    """Write a small metadata sidecar with the build timestamp.

    This is the only file whose contents change between runs on the same
    input. Everything else is deterministic.
    """
    meta = {
        "build_timestamp": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    }
    _write_atomic(output_path, json.dumps(meta, indent=2) + "\n")
    print(f"Created {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build distribution artifacts for the Corporate Actions Registry"
    )
    parser.add_argument("--actions", default="actions.json",
                        help="Path to actions.json")
    parser.add_argument("--output-dir", default=None,
                        help="Directory for output files "
                             "(defaults to the directory containing actions.json)")
    args = parser.parse_args()

    actions_path = Path(args.actions)
    data = load_actions(str(actions_path))

    errors = validate_actions_data(data)
    if errors:
        print("Validation errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        out_dir = actions_path.resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)

    base = actions_path.stem  # "actions" for actions.json

    try:
        build_dist(data, out_dir / f"{base}.dist.json")
        build_minified(data, out_dir / f"{base}.min.json")
        build_csv(data, out_dir / f"{base}.csv")
        build_sql(data, out_dir / f"{base}.sql")
        build_meta_sidecar(out_dir / f"{base}.meta.json")
    except (OSError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    print("Build completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
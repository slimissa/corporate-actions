#!/usr/bin/env python3
"""Verify that documentation matches docs/facts.json.

Reads the single source of truth for shared numeric facts
(`docs/facts.json`) and checks every doc that restates those facts.
Exits 1 on any mismatch.

The fact sheet is authoritative. Any number in a doc that restates a
fact must match the fact sheet. This script is deliberately narrow:
it checks only patterns listed in the CHECKS manifest below. It is
not a general-purpose doc parser.

Usage:
    python3 tools/check_doc_facts.py
    python3 tools/check_doc_facts.py --list
    python3 tools/check_doc_facts.py --quiet

Exit codes:
    0  every checked fact matches
    1  one or more mismatches
    2  fact sheet is missing, malformed, or inconsistent with the data
"""

# Exclude CHANGELOG from action_count: it records history, not current state.

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
FACTS_PATH = REPO_ROOT / "docs" / "facts.json"
ACTIONS_PATH = REPO_ROOT / "actions.json"


# ---------------------------------------------------------------------------
# The manifest
#
# Each entry: (doc_path, regex, fact_key, kind)
#
#   doc_path   path relative to REPO_ROOT
#   regex      a pattern with exactly one capture group; the group is
#              the value found in the doc
#   fact_key   dotted path into docs/facts.json, e.g. "sibling_versions.iso4217"
#   kind       "int"     compare as integers
#              "version" strip a leading "v" from both sides, then compare as strings
#              "string"  compare as strings
#
# Only add a pattern when the fact is already in the fact sheet. A
# pattern that matches nothing is fine; it means the doc currently
# does not restate that fact.
# ---------------------------------------------------------------------------
CHECKS: list[tuple[str, str, str, str]] = [

    # --- README.md ---------------------------------------------------------
    ("README.md", r"badge/actions-(\d+)-",            "action_count",     "int"),
    ("README.md", r"\*\*Actions\*\*:\s*(\d+)",        "action_count",     "int"),
    ("README.md", r"Validating\s+(\d+)\s+actions",    "action_count",     "int"),
    ("README.md", r"OK:\s*(\d+)\s+actions validated", "action_count",     "int"),
    ("README.md", r"\|\s*Actions\s*\|\s*(\d+)\s*\|",  "action_count",     "int"),
    ("README.md", r"\*\*Instruments\*\*:\s*(\d+)",    "instrument_count", "int"),
    ("README.md", r"badge/tests-(\d+)-",              "root_test_count",  "int"),
    ("README.md", r"\*\*Total tests\*\*:\s*(\d+)",    "root_test_count",  "int"),
    ("README.md", r"Python wrapper \| ✅ (\d+) tests",
        "wrapper_test_counts.python", "int"),
    ("README.md", r"JavaScript wrapper \| ✅ (\d+) tests",
        "wrapper_test_counts.javascript", "int"),
    ("README.md", r"Go wrapper \| ✅ (\d+) tests",
        "wrapper_test_counts.go", "int"),
    ("README.md", r"Rust wrapper \| ✅ (\d+) tests \+ \d+ doctest",
        "wrapper_test_counts.rust", "int"),
    ("README.md", r"\+ (\d+) \(Rust doctest\)",
        "wrapper_test_counts.rust_doctests", "int"),
    ("README.md", r"ISO 4217.*?v(\d+\.\d+\.\d+)",
        "sibling_versions.iso4217", "version"),
    ("README.md", r"Exchange Calendar.*?v(\d+\.\d+\.\d+)",
        "sibling_versions.exchange_calendar", "version"),
    ("README.md", r"Asset Identifiers.*?schema (\d+\.\d+\.\d+)",
        "sibling_versions.asset_identifiers_schema", "version"),

    # --- CONTRIBUTING.md ---------------------------------------------------
    ("CONTRIBUTING.md", r"OK:\s*(\d+)\s+actions validated", "action_count", "int"),
    ("CONTRIBUTING.md", r"Validating\s+(\d+)\s+actions",    "action_count", "int"),
    ("CONTRIBUTING.md", r"Tests:\s*`(\d+) passed",          "root_test_count", "int"),
    ("CONTRIBUTING.md", r"CORP_ACTIONS_MIN_ACTIONS.*?\| `?(\d+)`? \|",
        "min_actions_docs", "int"),

    # --- docs/data_sources.md ----------------------------------------------
    ("docs/data_sources.md", r"ISO 4217.*?\n.*?v(\d+\.\d+\.\d+)",
        "sibling_versions.iso4217", "version"),
    ("docs/data_sources.md", r"Exchange Calendar.*?\n.*?v(\d+\.\d+\.\d+)",
        "sibling_versions.exchange_calendar", "version"),

    # --- docs/roadmap.md ---------------------------------------------------
    ("docs/roadmap.md", r"\|\s*Actions\s*\|\s*(\d+)\s*\|",
        "action_count", "int"),

    # --- docs/validation_layers.md -----------------------------------------
    ("docs/validation_layers.md", r"OK:\s*(\d+)\s+actions validated",
        "action_count", "int"),
    ("docs/validation_layers.md", r"Validating\s+(\d+)\s+actions",
        "action_count", "int"),
    ("docs/validation_layers.md", r"Default:\s*`?(\d+)`?",
        "min_actions_docs", "int"),
]

# ---------------------------------------------------------------------------
# Scan mode: find every number in a doc that isn't sourced from facts.json
# ---------------------------------------------------------------------------

SCAN_KEYWORDS = [
    "actions", "instruments", "tests", "passed", "skipped", "deselected",
    "collected", "wrapper", "schema", "version", "default", "min-actions",
    "exchanges", "currencies", "action types", "doctest",
]

SCAN_DOCS = [
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
] + [f"docs/{p.name}" for p in (REPO_ROOT / "docs").glob("*.md")]

NUMBER_RE = re.compile(r"\b(\d+)\b")


def _all_fact_numbers(node) -> set[int]:
    """Collect every integer that appears anywhere in facts.json."""
    out: set[int] = set()
    def walk(n):
        if isinstance(n, dict):
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
        elif isinstance(n, int):
            out.add(n)
        elif isinstance(n, str):
            for m in NUMBER_RE.finditer(n):
                out.add(int(m.group(1)))
    walk(node)
    return out


def scan_docs(facts: dict, quiet: bool) -> int:
    """Report every number in a doc near a keyword that isn't in facts.json."""
    known = _all_fact_numbers(facts)
    problems = 0

    for doc_rel in SCAN_DOCS:
        doc_path = REPO_ROOT / doc_rel
        if not doc_path.is_file():
            continue
        lines = doc_path.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, start=1):
            # Skip code blocks and tables of contents
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("- ["):
                continue
            lower = line.lower()
            for kw in SCAN_KEYWORDS:
                if kw not in lower:
                    continue
                # Look for a number within 30 chars of the keyword
                kw_pos = lower.find(kw)
                window = lower[max(0, kw_pos - 30):kw_pos + len(kw) + 30]
                for m in NUMBER_RE.finditer(window):
                    n = int(m.group(1))
                    # Tiny numbers are line numbers, years, list indices
                    if n < 10:
                        continue
                    if n in known:
                        continue
                    problems += 1
                    if not quiet:
                        print(
                            f"{doc_rel}:{lineno}: number {n} near {kw!r} "
                            f"is not in facts.json: {stripped[:80]!r}"
                        )
    if problems and not quiet:
        print()
        print(f"{problems} number(s) not sourced from facts.json.")
        print("Either add the fact to docs/facts.json or remove the claim.")
    return 1 if problems else 0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_facts() -> dict[str, Any]:
    if not FACTS_PATH.is_file():
        print(f"Error: {FACTS_PATH} not found", file=sys.stderr)
        sys.exit(2)
    try:
        facts = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error: {FACTS_PATH} is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(facts, dict):
        print(f"Error: {FACTS_PATH} top level must be an object", file=sys.stderr)
        sys.exit(2)
    return facts


def lookup(facts: dict[str, Any], dotted_key: str) -> Any:
    """Walk a dotted key into a nested dict. Raises KeyError with a clear
    message if any segment is missing."""
    node: Any = facts
    for segment in dotted_key.split("."):
        if not isinstance(node, dict) or segment not in node:
            raise KeyError(dotted_key)
        node = node[segment]
    return node


def normalize(found: str, expected: Any, kind: str) -> bool:
    """Compare a value found in a doc to the expected fact value."""
    if kind == "int":
        try:
            return int(found) == int(expected)
        except (TypeError, ValueError):
            return False
    if kind == "version":
        a = found.lstrip("v")
        b = str(expected).lstrip("v")
        return a == b
    # "string"
    return found == str(expected)


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


# ---------------------------------------------------------------------------
# Self-check: the fact sheet must agree with the data
# ---------------------------------------------------------------------------

def self_check(facts: dict[str, Any]) -> bool:
    """Confirm facts.json is consistent with actions.json.

    Without this, a wrong fact sheet silently makes every downstream
    check agree with a wrong value.
    """
    if not ACTIONS_PATH.is_file():
        print(f"Error: {ACTIONS_PATH} not found", file=sys.stderr)
        return False

    actions_doc = json.loads(ACTIONS_PATH.read_text(encoding="utf-8"))
    actions = actions_doc.get("actions")
    if not isinstance(actions, list):
        print(f"Error: {ACTIONS_PATH} has no 'actions' array", file=sys.stderr)
        return False

    ok = True

    actual_actions = len(actions)
    declared_actions = facts.get("action_count")
    if declared_actions != actual_actions:
        print(
            f"FATAL: docs/facts.json says action_count={declared_actions}, "
            f"actions.json has {actual_actions}",
            file=sys.stderr,
        )
        ok = False

    actual_instruments = len({a.get("isin") for a in actions if a.get("isin")})
    declared_instruments = facts.get("instrument_count")
    if declared_instruments != actual_instruments:
        print(
            f"FATAL: docs/facts.json says instrument_count={declared_instruments}, "
            f"actions.json has {actual_instruments} unique ISINs",
            file=sys.stderr,
        )
        ok = False

    # Type counts: compare if the fact sheet declares them.
    declared_types = facts.get("action_type_counts")
    if isinstance(declared_types, dict):
        from collections import Counter
        actual_types = dict(Counter(a.get("action_type") for a in actions))
        for action_type, declared_count in declared_types.items():
            actual_count = actual_types.get(action_type, 0)
            if declared_count != actual_count:
                print(
                    f"FATAL: docs/facts.json says "
                    f"action_type_counts.{action_type}={declared_count}, "
                    f"actions.json has {actual_count}",
                    file=sys.stderr,
                )
                ok = False

    return ok


# ---------------------------------------------------------------------------
# Main check pass
# ---------------------------------------------------------------------------

def run_checks(facts: dict[str, Any], quiet: bool) -> int:
    mismatches = 0

    for doc_path_str, pattern, fact_key, kind in CHECKS:
        doc_path = REPO_ROOT / doc_path_str
        if not doc_path.is_file():
            # A missing doc is not a mismatch of this tool's concern.
            # Docs are added and removed; only existing ones are checked.
            continue

        try:
            expected = lookup(facts, fact_key)
        except KeyError:
            print(
                f"FATAL: check manifest references fact_key "
                f"{fact_key!r}, which is not in {FACTS_PATH.name}",
                file=sys.stderr,
            )
            return 2

        text = doc_path.read_text(encoding="utf-8")
        compiled = re.compile(pattern)

        for match in compiled.finditer(text):
            found = match.group(1)
            if normalize(found, expected, kind):
                continue
            mismatches += 1
            line = line_of(text, match.start())
            print(
                f"{doc_path_str}:{line}: {fact_key}: "
                f"fact sheet says {expected!r}, doc says {found!r}"
            )

    if mismatches and not quiet:
        print()
        print(f"{mismatches} mismatch(es) between docs and docs/facts.json.")
        print("Update the doc(s) or docs/facts.json, then re-run.")

    return 1 if mismatches else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify docs match docs/facts.json."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the check manifest and exit.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print individual mismatches, but not the summary line.",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Scan docs for numbers near known keywords that "
             "are not present in facts.json.",
    )
    parser.add_argument(
        "--skip-self-check",
        action="store_true",
        help="Do not verify that facts.json agrees with actions.json.",
    )
    args = parser.parse_args()

    if args.list:
        for doc, pattern, key, kind in CHECKS:
            print(f"{doc:35s} {pattern:50s} {key:40s} {kind}")
        return 0

    facts = load_facts()

    if args.scan:
        return scan_docs(facts, quiet=args.quiet)
    
    if not args.skip_self_check:
        if not self_check(facts):
            return 2

    return run_checks(facts, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
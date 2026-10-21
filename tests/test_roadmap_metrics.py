"""Verify every numeric cell in roadmap's 'Where we are now' table matches facts.json.

Catches drift that individual CHECKS entries miss: adding a new metric
row without adding a matching CHECKS pattern leaves that row unverified.
This test reads the whole table and fails on any cell that doesn't map
to a known fact.

The mapping is explicit — every numeric cell in the table has one of:
  - An exact key match (Actions → action_count)
  - A known alias (Root tests → root_test_count)
  - An exemption (row label indicates text, not number)

Adding a new numeric row requires adding a mapping entry here. That's
deliberate: it forces the author to say "this number is tracked."
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "docs" / "roadmap.md"
FACTS = ROOT / "docs" / "facts.json"

# Row label → fact key. Any numeric cell in "Where we are now" whose row
# label isn't here is an unmapped fact and fails the test.
ROW_MAP = {
    "Actions": "action_count",
    "Instruments covered": "instrument_count",
    "Root tests": "root_test_count",
}

# Rows whose value is text/enum, not a single number. Exempt from coverage.
TEXT_ROWS = {
    "Action types populated",
    "Action types accepted but unpopulated",
    "Action types rejected by validator",
    "Redistribution categories in use",
    "CI workflows",
    "Working fetchers",
    "SEC filing coverage",
    "SEC corpus",
    "Redistribution doc",
    "Sibling registries pinned",
    "Wrapper tests",  # has multiple numbers, verified by 4 CHECKS entries separately
}


def _parse_where_we_are_now() -> list[tuple[str, str]]:
    """Return [(row_label, value_cell)] from the 'Where we are now' table."""
    text = ROADMAP.read_text(encoding="utf-8")
    m = re.search(
        r"^## Where we are now\n(.*?)(?=\n## |\Z)",
        text, re.MULTILINE | re.DOTALL,
    )
    if not m:
        return []
    rows = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line or "| Metric" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2:
            rows.append((cells[0], cells[1]))
    return rows


def test_where_we_are_now_section_exists():
    rows = _parse_where_we_are_now()
    assert rows, "## Where we are now section not found or empty"


def test_every_numeric_row_is_mapped_or_exempt():
    """Any row whose value starts with a digit must be mapped or explicitly exempt."""
    rows = _parse_where_we_are_now()
    unmapped = []
    for label, value in rows:
        if label in TEXT_ROWS:
            continue
        if label in ROW_MAP:
            continue
        # Numeric-looking value without a mapping?
        if value and value[0].isdigit():
            unmapped.append(f"{label!r} = {value!r}")
    assert not unmapped, (
        "Numeric rows in 'Where we are now' without a fact mapping:\n"
        + "\n".join(f"  {u}" for u in unmapped)
        + "\nAdd to ROW_MAP or TEXT_ROWS in tests/test_roadmap_metrics.py."
    )


@pytest.mark.parametrize("label,fact_key", sorted(ROW_MAP.items()))
def test_mapped_row_matches_fact(label: str, fact_key: str):
    """Each mapped row's value must equal the corresponding fact."""
    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    for fact_path in [fact_key]:
        # Support dotted paths
        target = facts
        for part in fact_path.split("."):
            if not isinstance(target, dict):
                pytest.fail(f"fact {fact_path!r} not found in facts.json")
            target = target.get(part)
            if target is None:
                pytest.fail(f"fact {fact_path!r} not found in facts.json")

    rows = _parse_where_we_are_now()
    values = {lbl: val for lbl, val in rows}
    if label not in values:
        pytest.fail(f"row {label!r} not found in 'Where we are now' table")

    # Extract the leading integer from the cell
    m = re.match(r"^(\d+)", values[label])
    if not m:
        pytest.fail(f"row {label!r} value {values[label]!r} is not numeric")
    actual = int(m.group(1))

    assert actual == target, (
        f"roadmap {label!r} says {actual}, facts.json {fact_key!r} says {target}. "
        f"Run `python3 tools/update_facts.py` and fix the roadmap row."
    )

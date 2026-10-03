"""Documentation gate for the redistribution position.

Three properties must hold:

  1. Every action carries a `redistribution` value.
  2. No action's value is `restricted`. That category is a fail-safe
     and must never ship.
  3. Every source that appears in `actions.json` is named in
     `docs/redistribution.md`.

The first two are data properties. The third is a documentation
property: a source that ships without being mentioned in the doc is a
source that was added without a licensing decision.

Run:
    pytest tests/test_redistribution_doc.py -v
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ACTIONS_PATH = REPO_ROOT / "actions.json"
DOC_PATH = REPO_ROOT / "docs" / "redistribution.md"


@pytest.fixture(scope="module")
def actions() -> list:
    return json.loads(ACTIONS_PATH.read_text(encoding="utf-8"))["actions"]


@pytest.fixture(scope="module")
def doc_lower() -> str:
    return DOC_PATH.read_text(encoding="utf-8").lower()


# ---------------------------------------------------------------------------
# Data properties
# ---------------------------------------------------------------------------

class TestDataProperties:

    def test_every_action_has_redistribution(self, actions):
        """No action may be missing the field."""
        missing = [
            a.get("action_id", f"<index {i}>")
            for i, a in enumerate(actions)
            if not a.get("redistribution")
        ]
        assert not missing, (
            f"{len(missing)} action(s) missing redistribution:\n"
            + "\n".join(f"  {aid}" for aid in missing[:10])
        )

    def test_no_action_is_restricted(self, actions):
        """`restricted` is a fail-safe. It must never ship."""
        bad = [
            a.get("action_id", f"<index {i}>")
            for i, a in enumerate(actions)
            if a.get("redistribution") == "restricted"
        ]
        assert not bad, (
            f"{len(bad)} action(s) marked restricted:\n"
            + "\n".join(f"  {aid}" for aid in bad[:10])
            + "\nAdd a mapping rule for the source, then re-run "
              "tools/derive_redistribution.py."
        )

    def test_values_are_from_the_closed_enum(self, actions):
        """Every value is one of the four categories."""
        valid = {"public-domain", "facts-only", "secondary-source", "restricted"}
        bad = [
            (a.get("action_id"), a.get("redistribution"))
            for a in actions
            if a.get("redistribution") not in valid
        ]
        assert not bad, f"unknown redistribution values: {bad[:10]}"

    def test_distribution_is_non_trivial(self, actions):
        """At least one category is populated."""
        counts = Counter(a.get("redistribution") for a in actions)
        assert counts, "no redistribution values at all"


# ---------------------------------------------------------------------------
# Documentation property
# ---------------------------------------------------------------------------

class TestDocCoverage:

    def test_doc_exists(self):
        assert DOC_PATH.is_file(), f"missing {DOC_PATH}"

    def test_doc_mentions_every_source(self, actions, doc_lower):
        """Every source that ships is named in the doc."""
        sources = {
            a.get("provenance", {}).get("source", "")
            for a in actions
            if a.get("provenance", {}).get("source")
        }
        assert sources, "no sources found in actions.json"

        missing = []
        for src in sources:
            tokens = [src.lower(), src.split()[0].lower()]
            if "press release" in src.lower():
                tokens.append("press release")
            if "exchange" in src.lower() and "announcement" in src.lower():
                tokens.append("exchange announcement")
            if not any(t in doc_lower for t in tokens):
                missing.append(src)

        assert not missing, (
            f"doc does not mention these source(s): {missing}\n"
            "Add a row to the 'Per-source mapping' table in "
            "docs/redistribution.md."
        )

    def test_doc_declares_the_four_categories(self, doc_lower):
        for cat in ("public-domain", "facts-only", "secondary-source", "restricted"):
            assert cat in doc_lower, (
                f"doc does not mention the {cat!r} category"
            )

    def test_doc_names_the_mapping_tool(self, doc_lower):
        """The doc points at the source of truth for the mapping."""
        assert "derive_redistribution" in doc_lower, (
            "doc does not reference tools/derive_redistribution.py"
        )
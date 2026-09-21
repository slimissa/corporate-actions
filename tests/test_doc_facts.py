"""
Tests for tools/check_doc_facts.py.

Verifies that docs/facts.json is well-formed, consistent with
actions.json, and that the check manifest covers every fact restated in
any doc. Also runs the checker as a subprocess to confirm it exits 0 on
the current repo state and 1 on a deliberately corrupted doc.

Run:
    python3 -m pytest tests/test_doc_facts.py -v
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FACTS_PATH = REPO_ROOT / "docs" / "facts.json"
ACTIONS_PATH = REPO_ROOT / "actions.json"
CHECKER = REPO_ROOT / "tools" / "check_doc_facts.py"
README_PATH = REPO_ROOT / "README.md"
VALIDATOR_PATH = REPO_ROOT / "tools" / "validate.py"
LAYERS_PATH = REPO_ROOT / "docs" / "validation_layers.md"
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_update.sh"
SCRIPTS_README = REPO_ROOT / "scripts" / "README.md"

sys.path.insert(0, str(REPO_ROOT / "tools"))
import check_doc_facts as cdf  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def facts():
    assert FACTS_PATH.is_file(), f"{FACTS_PATH} not found"
    return json.loads(FACTS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def actions_doc():
    assert ACTIONS_PATH.is_file(), f"{ACTIONS_PATH} not found"
    return json.loads(ACTIONS_PATH.read_text(encoding="utf-8"))


def _run_checker(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
    )


def _leaf_keys(node, prefix=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaf_keys(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(node, list):
        yield prefix
    else:
        yield prefix


# Fact keys that legitimately have no numeric restatement in a doc.
# Every other leaf fact must have at least one manifest entry.
IGNORABLE_KEYS = {
    # Lists of strings restated in prose, not numbers
    "instruments", "currencies", "populated_types", "reserved_types",
    # Covered by the tool's self_check, not by a doc regex
    "action_type_counts", "action_type_counts.SPLIT",
    "action_type_counts.DIVIDEND", "action_type_counts.SPECIAL_DIVIDEND",
    "action_type_counts.SYMBOL_CHANGE",
    # Structural metadata, not numeric facts
    "historical_depth_start", "root_test_skipped",
    "root_test_network_deselected", "root_test_collected_total",
    "min_actions_roadmap_target", "sec_edgar_status", "sec_edgar_scope",
    "nasdaq_status", "format_date_enforcement",
    "state_file_timestamp_example", "webhook_timestamp_format",
    "min_actions_code",   
}


# ---------------------------------------------------------------------------
# facts.json structure
# ---------------------------------------------------------------------------

class TestFactsFile:

    def test_file_exists(self):
        assert FACTS_PATH.is_file()

    def test_is_json_object(self, facts):
        assert isinstance(facts, dict)

    def test_required_top_level_keys(self, facts):
        required = {
            "action_count", "instrument_count", "root_test_count",
            "wrapper_test_counts", "sibling_versions",
            "min_actions_code", "min_actions_docs",
        }
        missing = required - set(facts.keys())
        assert not missing, f"facts.json missing: {sorted(missing)}"

    def test_action_count_is_positive_int(self, facts):
        assert isinstance(facts["action_count"], int)
        assert facts["action_count"] > 0

    def test_wrapper_counts_all_non_negative_ints(self, facts):
        for lang, n in facts["wrapper_test_counts"].items():
            assert isinstance(n, int), f"{lang} not int"
            assert n >= 0, f"{lang} negative"

    def test_sibling_versions_are_semver(self, facts):
        for key, value in facts["sibling_versions"].items():
            assert isinstance(value, str)
            assert re.match(r"^v?\d+\.\d+\.\d+$", value), \
                f"sibling_versions.{key}={value!r} is not semver"


# ---------------------------------------------------------------------------
# facts.json vs actions.json
# ---------------------------------------------------------------------------

class TestFactsAgainstData:

    def test_action_count_matches_data(self, facts, actions_doc):
        assert facts["action_count"] == len(actions_doc["actions"])

    def test_instrument_count_matches_data(self, facts, actions_doc):
        actual = len({a["isin"] for a in actions_doc["actions"] if a.get("isin")})
        assert facts["instrument_count"] == actual

    def test_type_counts_match_data(self, facts, actions_doc):
        declared = facts.get("action_type_counts", {})
        if not declared:
            pytest.skip("facts.json has no action_type_counts")
        actual = Counter(a.get("action_type") for a in actions_doc["actions"])
        for t, n in declared.items():
            assert actual.get(t, 0) == n, \
                f"action_type_counts.{t}: facts={n}, data={actual.get(t, 0)}"

    def test_populated_types_subset_of_data(self, facts, actions_doc):
        declared = set(facts.get("populated_types", []))
        actual = {a["action_type"] for a in actions_doc["actions"]}
        assert declared <= actual, \
            f"claimed populated but absent from data: {sorted(declared - actual)}"

    def test_reserved_types_absent_from_data(self, facts, actions_doc):
        declared = set(facts.get("reserved_types", []))
        actual = {a["action_type"] for a in actions_doc["actions"]}
        overlap = declared & actual
        assert not overlap, f"reserved types present in data: {sorted(overlap)}"


# ---------------------------------------------------------------------------
# Manifest integrity
# ---------------------------------------------------------------------------

class TestManifest:

    def test_entries_are_4tuples(self):
        assert isinstance(cdf.CHECKS, list)
        for entry in cdf.CHECKS:
            assert isinstance(entry, tuple) and len(entry) == 4, \
                f"malformed entry: {entry!r}"

    def test_every_key_resolves_in_facts(self, facts):
        for doc, pattern, key, kind in cdf.CHECKS:
            try:
                cdf.lookup(facts, key)
            except KeyError:
                pytest.fail(f"manifest references missing key {key!r}")

    def test_every_non_ignorable_fact_key_is_covered(self, facts):
        declared = set(_leaf_keys(facts))
        covered = {k for _, _, k, _ in cdf.CHECKS}
        uncovered = declared - covered - IGNORABLE_KEYS
        assert not uncovered, \
            f"fact keys with no manifest check: {sorted(uncovered)}"

    def test_all_patterns_compile(self):
        for doc, pattern, key, kind in cdf.CHECKS:
            try:
                re.compile(pattern)
            except re.error as exc:
                pytest.fail(f"{doc}:{key} pattern does not compile: {exc}")

    def test_all_kinds_are_known(self):
        for doc, pattern, key, kind in cdf.CHECKS:
            assert kind in {"int", "version", "string"}, \
                f"{doc}:{key} has unknown kind {kind!r}"

    def test_manifest_covers_multiple_docs(self):
        docs = {doc for doc, _, _, _ in cdf.CHECKS}
        assert len(docs) >= 3, f"manifest covers only {sorted(docs)}"

    def test_manifest_has_expected_minimum_size(self):
        # If this grows, adjust. If it shrinks, a check was removed.
        assert len(cdf.CHECKS) >= 20, \
            f"manifest has only {len(cdf.CHECKS)} entries; expected at least 20"


# ---------------------------------------------------------------------------
# Behavioural: the tool exits 0 on clean state, 1 on drift
# ---------------------------------------------------------------------------

class TestCheckerBehaviour:

    def test_clean_repo_passes(self):
        result = _run_checker()
        assert result.returncode == 0, (
            f"check_doc_facts.py failed:\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    def test_list_mode_prints_one_line_per_check(self):
        result = _run_checker("--list")
        assert result.returncode == 0
        lines = [l for l in result.stdout.splitlines() if l.strip()]
        assert len(lines) == len(cdf.CHECKS)

    def test_detects_drift_in_copied_repo(self, tmp_path):
        """Copy the minimum layout, corrupt one number, expect exit 1."""
        (tmp_path / "tools").mkdir()
        (tmp_path / "docs").mkdir()
        shutil.copy2(CHECKER, tmp_path / "tools" / "check_doc_facts.py")
        shutil.copy2(FACTS_PATH, tmp_path / "docs" / "facts.json")
        shutil.copy2(ACTIONS_PATH, tmp_path / "actions.json")

        # README with a deliberately wrong action count
        (tmp_path / "README.md").write_text(
            "**Actions**: 999\n", encoding="utf-8"
        )

        result = subprocess.run(
            [sys.executable, str(tmp_path / "tools" / "check_doc_facts.py")],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert result.returncode == 1, (
            f"expected exit 1, got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "action_count" in result.stdout
        assert "999" in result.stdout

    def test_missing_facts_file_exits_2(self, tmp_path):
        (tmp_path / "tools").mkdir()
        shutil.copy2(CHECKER, tmp_path / "tools" / "check_doc_facts.py")
        result = subprocess.run(
            [sys.executable, str(tmp_path / "tools" / "check_doc_facts.py")],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert result.returncode == 2


# ---------------------------------------------------------------------------
# Cross-doc consistency checks the manifest cannot express as regexes
# ---------------------------------------------------------------------------

class TestReadmeCountsCiteFacts:

    def test_every_wrapper_count_in_readme_is_in_facts(self, facts):
        text = README_PATH.read_text(encoding="utf-8")
        allowed = set(facts["wrapper_test_counts"].values())
        for m in re.finditer(r"✅ (\d+) tests", text):
            n = int(m.group(1))
            assert n in allowed, (
                f"README claims {n} wrapper tests, "
                f"not in facts.wrapper_test_counts {sorted(allowed)}"
            )

    def test_readme_badge_matches_facts(self, facts):
        text = README_PATH.read_text(encoding="utf-8")
        m = re.search(r"badge/tests-(\d+)-", text)
        assert m, "README has no tests badge"
        assert int(m.group(1)) == facts["root_test_count"]


class TestScriptsReadmeSecStatus:

    def test_sec_status_matches_code(self):
        """If run_update.sh runs `sec`, scripts/README.md must not refuse it."""
        if not SCRIPT_PATH.is_file() or not SCRIPTS_README.is_file():
            pytest.skip("scripts files not present")
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        readme = SCRIPTS_README.read_text(encoding="utf-8")

        runs_sec = re.search(r"^\s*sec\)", script, re.MULTILINE) is not None
        if not runs_sec:
            pytest.skip("run_update.sh does not run the SEC fetcher")

        for phrase in ("`sec` refuses", "`sec` and `nasdaq` refuse",
                       "Only `yahoo` works today"):
            assert phrase not in readme, (
                f"scripts/README.md contains {phrase!r}, "
                f"but run_update.sh runs the SEC fetcher"
            )


class TestValidationLayersConsistency:

    def test_format_date_is_documented_as_enforced(self):
        if not VALIDATOR_PATH.is_file() or not LAYERS_PATH.is_file():
            pytest.skip("validator or layers doc not present")
        validator = VALIDATOR_PATH.read_text(encoding="utf-8")
        layers = LAYERS_PATH.read_text(encoding="utf-8")

        if "_FORMAT_CHECKER" not in validator:
            pytest.skip("validate.py has no FormatChecker")

        contradiction = "The validator does not validate that dates are real"
        assert contradiction not in layers, (
            "validation_layers.md says format: date is not enforced, "
            "but validate.py uses a FormatChecker"
        )

    def test_min_actions_default_matches_code(self):
        if not VALIDATOR_PATH.is_file() or not LAYERS_PATH.is_file():
            pytest.skip("validator or layers doc not present")
        validator = VALIDATOR_PATH.read_text(encoding="utf-8")
        m = re.search(r"DEFAULT_MIN_ACTIONS\s*=\s*(\d+)", validator)
        assert m, "validate.py has no DEFAULT_MIN_ACTIONS"
        code_value = int(m.group(1))

        layers = LAYERS_PATH.read_text(encoding="utf-8")
        for dm in re.finditer(r"Default:\s*`?(\d+)`?", layers):
            doc_value = int(dm.group(1))
            assert doc_value == code_value, (
                f"validation_layers.md says Default: {doc_value}, "
                f"code says {code_value}"
            )
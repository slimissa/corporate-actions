"""
Cross-language wrapper consistency and integration tests for the
Corporate Actions Registry.

This test suite verifies that the Python wrapper can load the production
`actions.json` file and that its behavior is consistent with the raw JSON
data. It also includes a placeholder for cross-language consistency checks
that can be extended to invoke the JavaScript, Go, and Rust wrappers.

The tests are designed to run from the repository root:
    pytest tests/test_wrappers.py
"""

import json
import os
import sys
from pathlib import Path

# Ensure repository root is on sys.path so we can import the Python wrapper
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wrappers" / "python"))

from corporate_actions_registry import CorporateActionsRegistry

# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
ACTIONS_PATH = REPO_ROOT / "actions.json"

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def load_raw_actions():
    """Load actions.json as plain dict/list for comparison."""
    with open(ACTIONS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def load_registry():
    """Load registry using the Python wrapper."""
    return CorporateActionsRegistry(str(ACTIONS_PATH))


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------
class TestWrapperLoadsProductionFile:
    def test_actions_file_exists(self):
        assert ACTIONS_PATH.exists(), "actions.json not found"

    def test_registry_loads_without_error(self):
        registry = load_registry()
        assert registry.count() >= 0

    def test_registry_count_matches_raw_actions_length(self):
        raw = load_raw_actions()
        registry = load_registry()
        assert registry.count() == len(raw["actions"])

    def test_meta_matches_raw_meta(self):
        raw = load_raw_actions()
        registry = load_registry()
        assert registry.meta.version == raw.get("meta", {}).get("version")
        assert registry.meta.source == raw.get("meta", {}).get("source")


class TestLookupConsistency:
    def test_by_isin_matches_raw_filtering(self):
        raw = load_raw_actions()
        registry = load_registry()
        # Test a known ISIN if present, else use first ISIN from raw
        isin = raw["actions"][0].get("isin")
        if isin:
            raw_matches = [a for a in raw["actions"] if a.get("isin") == isin]
            wrapper_matches = registry.by_isin(isin)
            assert len(raw_matches) == len(wrapper_matches)
            # Compare action_id sets
            raw_ids = {a.get("action_id") for a in raw_matches}
            wrapper_ids = {a.action_id for a in wrapper_matches}
            assert raw_ids == wrapper_ids

    def test_by_action_id_returns_correct_action(self):
        raw = load_raw_actions()
        registry = load_registry()
        if raw["actions"]:
            target_id = raw["actions"][0].get("action_id")
            if target_id:
                action = registry.by_action_id(target_id)
                assert action is not None
                assert action.action_id == target_id

    def test_by_action_type_matches_raw(self):
        raw = load_raw_actions()
        registry = load_registry()
        # Collect all unique action types from raw
        raw_types = {a.get("action_type") for a in raw["actions"] if a.get("action_type")}
        for action_type in raw_types:
            raw_matches = [a for a in raw["actions"] if a.get("action_type") == action_type]
            wrapper_matches = registry.by_action_type(action_type)
            assert len(raw_matches) == len(wrapper_matches)
            raw_ids = {a.get("action_id") for a in raw_matches}
            wrapper_ids = {a.action_id for a in wrapper_matches}
            assert raw_ids == wrapper_ids

    def test_by_date_range_returns_expected(self):
        raw = load_raw_actions()
        registry = load_registry()
        # Use a broad range to include all; just verify it doesn't crash
        all_actions = registry.by_date_range("2000-01-01", "2099-12-31", "ex_date")
        # Compare count to raw actions that have ex_date
        raw_with_ex = [a for a in raw["actions"] if a.get("dates", {}).get("ex_date")]
        assert len(all_actions) == len(raw_with_ex)

    def test_all_action_types_matches_raw(self):
        raw = load_raw_actions()
        registry = load_registry()
        raw_types = sorted({a.get("action_type") for a in raw["actions"] if a.get("action_type")})
        wrapper_types = registry.all_action_types()
        assert wrapper_types == raw_types


class TestSerializationRoundTrip:
    def test_to_dict_and_back(self):
        registry = load_registry()
        data = registry.to_dict()
        # Reload from the dict
        registry2 = CorporateActionsRegistry(actions_data=data)
        assert registry.count() == registry2.count()
        # Compare raw action IDs
        raw_ids = {a["action_id"] for a in load_raw_actions()["actions"]}
        wrapper_ids = {a.action_id for a in registry2.actions}
        assert raw_ids == wrapper_ids

    def test_save_and_reload(self, tmp_path):
        registry = load_registry()
        out_path = tmp_path / "out_actions.json"
        registry.save(str(out_path))
        registry2 = CorporateActionsRegistry(str(out_path))
        assert registry.count() == registry2.count()
        assert registry.meta.version == registry2.meta.version


class TestCrossLanguageConsistencyPlaceholder:
    """
    These tests would ideally verify that the JavaScript, Go, and Rust
    wrappers return identical results for the same actions.json.
    Because those wrappers are in separate subdirectories, they can be
    tested via their own test suites. For now, we at least verify that
    the raw JSON is valid and the Python wrapper is consistent.
    """

    def test_raw_json_is_valid(self):
        data = load_raw_actions()
        assert isinstance(data, dict)
        assert "actions" in data
        assert isinstance(data["actions"], list)

    def test_python_wrapper_does_not_mutate_raw(self):
        raw_before = load_raw_actions()
        _ = load_registry()
        raw_after = load_raw_actions()
        assert raw_before == raw_after
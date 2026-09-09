"""
Tests for uniqueness validation in the Corporate Actions Registry.

These tests verify that duplicate action_ids are correctly detected.

The function under test is `validate_uniqueness` from `tools.validate`.
It takes a list of action dictionaries and returns a list of error strings
for any duplicate `action_id`.

Note: If `validate_uniqueness` is not yet present in `tools.validate`,
add the following function to that module:

    def validate_uniqueness(actions):
        seen = set()
        errors = []
        for action in actions:
            action_id = action.get("action_id")
            if action_id is not None:
                if action_id in seen:
                    errors.append(f"Duplicate action_id: {action_id}")
                else:
                    seen.add(action_id)
        return errors
"""

import os
import sys

# Ensure repository root is on sys.path so we can import tools.validate
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.validate import validate_uniqueness


class TestUniqueness:
    def test_empty_actions(self):
        assert validate_uniqueness([]) == []

    def test_no_duplicates(self):
        actions = [
            {"action_id": "A"},
            {"action_id": "B"},
            {"action_id": "C"},
        ]
        assert validate_uniqueness(actions) == []

    def test_single_duplicate(self):
        actions = [
            {"action_id": "A"},
            {"action_id": "B"},
            {"action_id": "A"},
        ]
        errors = validate_uniqueness(actions)
        assert len(errors) == 1
        assert "Duplicate action_id: A" in errors[0]

    def test_multiple_duplicates(self):
        actions = [
            {"action_id": "A"},
            {"action_id": "B"},
            {"action_id": "A"},
            {"action_id": "B"},
            {"action_id": "C"},
        ]
        errors = validate_uniqueness(actions)
        # A appears twice -> one duplicate, B appears twice -> one duplicate
        assert len(errors) == 2
        assert any("Duplicate action_id: A" in e for e in errors)
        assert any("Duplicate action_id: B" in e for e in errors)

    def test_duplicate_three_times(self):
        actions = [
            {"action_id": "A"},
            {"action_id": "A"},
            {"action_id": "A"},
        ]
        errors = validate_uniqueness(actions)
        # Only two duplicate occurrences should be reported (the first is unique)
        assert len(errors) == 2

    def test_missing_action_id_is_ignored(self):
        actions = [
            {"action_id": "A"},
            {},
            {"action_id": "B"},
        ]
        assert validate_uniqueness(actions) == []

    def test_none_action_id_is_ignored(self):
        actions = [
            {"action_id": "A"},
            {"action_id": None},
            {"action_id": "B"},
        ]
        assert validate_uniqueness(actions) == []

    def test_duplicate_with_different_other_fields(self):
        actions = [
            {"action_id": "A", "isin": "US1"},
            {"action_id": "A", "isin": "US2"},
        ]
        errors = validate_uniqueness(actions)
        assert len(errors) == 1

    def test_case_sensitivity(self):
        # action_ids are case-sensitive; "A" and "a" are different
        actions = [
            {"action_id": "A"},
            {"action_id": "a"},
        ]
        assert validate_uniqueness(actions) == []

    def test_large_number_of_unique_actions(self):
        actions = [{"action_id": f"ID-{i}"} for i in range(1000)]
        assert validate_uniqueness(actions) == []

    def test_large_number_with_duplicates(self):
        actions = [{"action_id": f"ID-{i % 100}"} for i in range(1000)]
        errors = validate_uniqueness(actions)
        # 100 unique IDs, each repeated 10 times -> 100 * 9 = 900 duplicate errors
        assert len(errors) == 900
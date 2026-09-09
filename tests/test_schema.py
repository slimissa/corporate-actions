"""
Tests for JSON Schema validation of the Corporate Actions Registry.

These tests verify that the schema.json file is valid and correctly
enforces the required structure for actions.json.

The schema is expected to define:
- Top-level: "meta" and "actions" required
- Each action requires: isin, action_id, action_type, dates, provenance
- dates requires: announcement, effective_date
- provenance requires: source_url
- For SPLIT/REVERSE_SPLIT: ratio required
- For DIVIDEND/SPECIAL_DIVIDEND: amount and currency required
- action_type must be one of the 8 supported types
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure repository root is on sys.path (not strictly needed, but for consistency)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import jsonschema
from jsonschema import validate as schema_validate

# Paths relative to this test file
REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schema.json"
ACTIONS_PATH = REPO_ROOT / "actions.json"


@pytest.fixture(scope="module")
def schema():
    """Load the JSON Schema."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def action_schema(schema):
    """Extract the action item schema."""
    return schema["properties"]["actions"]["items"]


@pytest.fixture(scope="module")
def actions_data():
    """Load the actual actions.json file."""
    with open(ACTIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class TestSchemaStructure:
    def test_schema_exists(self):
        assert SCHEMA_PATH.exists()

    def test_schema_is_valid_json(self, schema):
        assert isinstance(schema, dict)
        assert "$schema" in schema

    def test_schema_requires_meta_and_actions(self, schema):
        assert "properties" in schema
        assert "meta" in schema["properties"]
        assert "actions" in schema["properties"]
        assert "required" in schema
        assert "meta" in schema["required"]
        assert "actions" in schema["required"]

    def test_action_schema_exists(self, action_schema):
        assert isinstance(action_schema, dict)
        assert "properties" in action_schema
        assert "required" in action_schema

    def test_action_required_fields(self, action_schema):
        required = action_schema["required"]
        assert "isin" in required
        assert "action_id" in required
        assert "action_type" in required
        assert "dates" in required
        assert "provenance" in required

    def test_action_type_enum(self, action_schema):
        action_type_prop = action_schema["properties"]["action_type"]
        assert "enum" in action_type_prop
        expected = [
            "SPLIT",
            "REVERSE_SPLIT",
            "DIVIDEND",
            "SPECIAL_DIVIDEND",
            "SYMBOL_CHANGE",
            "SPINOFF",
            "DELISTING",
            "MERGER",
        ]
        assert set(action_type_prop["enum"]) == set(expected)

    def test_dates_required_fields(self, action_schema):
        dates_schema = action_schema["properties"]["dates"]
        assert "required" in dates_schema
        assert "announcement" in dates_schema["required"]
        assert "effective_date" in dates_schema["required"]

    def test_provenance_required_fields(self, action_schema):
        prov_schema = action_schema["properties"]["provenance"]
        assert "required" in prov_schema
        assert "source_url" in prov_schema["required"]


class TestActionSchemaValidation:
    def test_valid_split_action(self, action_schema):
        action = {
            "isin": "US67066G1040",
            "action_id": "US67066G1040-SPLIT-2024-06-10-0001",
            "action_type": "SPLIT",
            "ratio": "10:1",
            "dates": {
                "announcement": "2024-05-22",
                "ex_date": "2024-06-10",
                "record_date": "2024-06-07",
                "effective_date": "2024-06-10",
            },
            "status": "COMPLETED",
            "provenance": {
                "source": "NVIDIA",
                "source_url": "https://example.com/nvda-split",
            },
            "impact": {
                "price_multiplier": 0.1,
                "share_multiplier": 10.0,
            },
        }
        schema_validate(action, action_schema)  # should not raise

    def test_valid_dividend_action(self, action_schema):
        action = {
            "isin": "US0378331005",
            "action_id": "US0378331005-DIVIDEND-2024-05-16-0002",
            "action_type": "DIVIDEND",
            "amount": 0.25,
            "currency": "USD",
            "dates": {
                "announcement": "2024-05-02",
                "ex_date": "2024-05-16",
                "record_date": "2024-05-17",
                "effective_date": "2024-05-23",
            },
            "status": "COMPLETED",
            "provenance": {
                "source": "Apple",
                "source_url": "https://example.com/aapl-div",
            },
        }
        schema_validate(action, action_schema)

    def test_valid_symbol_change_action(self, action_schema):
        action = {
            "isin": "US30303M1027",
            "action_id": "US30303M1027-SYMBOL_CHANGE-2022-06-09-0004",
            "action_type": "SYMBOL_CHANGE",
            "dates": {
                "announcement": "2022-06-09",
                "effective_date": "2022-06-09",
            },
            "status": "COMPLETED",
            "provenance": {
                "source": "Meta",
                "source_url": "https://example.com/meta-symbol",
            },
        }
        schema_validate(action, action_schema)

    def test_split_missing_ratio(self, action_schema):
        action = {
            "isin": "US67066G1040",
            "action_id": "US67066G1040-SPLIT-2024-06-10-0001",
            "action_type": "SPLIT",
            "dates": {
                "announcement": "2024-05-22",
                "effective_date": "2024-06-10",
            },
            "provenance": {"source_url": "https://example.com"},
        }
        with pytest.raises(jsonschema.ValidationError):
            schema_validate(action, action_schema)

    def test_dividend_missing_amount(self, action_schema):
        action = {
            "isin": "US0378331005",
            "action_id": "US0378331005-DIVIDEND-2024-05-16-0002",
            "action_type": "DIVIDEND",
            "dates": {
                "announcement": "2024-05-02",
                "effective_date": "2024-05-23",
            },
            "provenance": {"source_url": "https://example.com"},
        }
        with pytest.raises(jsonschema.ValidationError):
            schema_validate(action, action_schema)

    def test_missing_required_field_isin(self, action_schema):
        action = {
            "action_id": "ID-1",
            "action_type": "SPLIT",
            "dates": {"announcement": "2024-01-01", "effective_date": "2024-01-01"},
            "provenance": {"source_url": "https://example.com"},
        }
        with pytest.raises(jsonschema.ValidationError):
            schema_validate(action, action_schema)

    def test_invalid_action_type(self, action_schema):
        action = {
            "isin": "US67066G1040",
            "action_id": "ID-1",
            "action_type": "INVALID_TYPE",
            "dates": {"announcement": "2024-01-01", "effective_date": "2024-01-01"},
            "provenance": {"source_url": "https://example.com"},
        }
        with pytest.raises(jsonschema.ValidationError):
            schema_validate(action, action_schema)


class TestActualActionsFile:
    def test_actions_file_exists(self):
        assert ACTIONS_PATH.exists()

    def test_actions_file_has_required_keys(self, actions_data):
        assert "meta" in actions_data
        assert "actions" in actions_data
        assert isinstance(actions_data["actions"], list)

    def test_all_actions_pass_schema(self, actions_data, action_schema):
        for idx, action in enumerate(actions_data["actions"]):
            try:
                schema_validate(action, action_schema)
            except jsonschema.ValidationError as e:
                pytest.fail(f"Action at index {idx} failed schema validation: {e}")
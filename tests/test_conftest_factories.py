"""Prove conftest factories produce schema-valid actions.

Uses jsonschema directly — no CLI, no fixtures, no cross-reference.
Cross-reference and business-rule validation are tested elsewhere;
this test's job is: does the factory produce something the schema
accepts, and does a mutation break that acceptance.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from tests.conftest import (
    make_split_action,
    make_dividend_action,
    make_symbol_change_action,
)

REPO = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((REPO / "schema.json").read_text())

# Minimal meta block that satisfies the schema's `meta` requirements.
# The factory doesn't produce a meta block — it produces one action — so
# the test wraps it in whatever meta the schema demands.
META = {
    "version": "1.2.3",
    "generated_at": "2024-01-01T00:00:00Z",
    "source": "test",
    "notes": "",
    "updated_at": "2024-01-01T00:00:00Z",
}


def _validate(action: dict) -> None:
    """Raise jsonschema.ValidationError if the doc fails schema validation."""
    doc = {"meta": copy.deepcopy(META), "actions": [action]}
    jsonschema.validate(doc, SCHEMA)


@pytest.mark.parametrize("factory", [
    make_split_action, make_dividend_action, make_symbol_change_action,
])
def test_factory_output_passes_schema(factory):
    action = factory()
    try:
        _validate(action)
    except jsonschema.ValidationError as e:
        pytest.fail(
            f"{factory.__name__} produced a schema-invalid action: "
            f"{e.message} at path {list(e.path)}"
        )


@pytest.mark.parametrize("mutate,reason", [
    (lambda a: a.pop("action_id", None), "missing action_id"),
    (lambda a: a.pop("isin", None), "missing isin"),
    (lambda a: a.__setitem__("action_type", "NOT_A_TYPE"), "invalid type"),
    (lambda a: a.__setitem__("redistribution", "bogus-value"), "invalid redistribution"),
])
def test_factory_mutation_fails_schema(mutate, reason):
    action = make_dividend_action()
    mutate(action)
    with pytest.raises(jsonschema.ValidationError):
        _validate(action)


def test_factories_return_fresh_dicts():
    a, b = make_split_action(), make_split_action()
    assert a is not b
    a["isin"] = "CORRUPT"
    assert b["isin"] != "CORRUPT"

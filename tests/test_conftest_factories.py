"""Self-verifying tests for tests/conftest.py action factories.

Each factory must produce an action that passes every validation layer.
If a future schema change adds a required field, this test fails here —
before seven other test files fail in a confusing cascade.

Design:
  - test_factory_output_passes_full_validation: the whole point of the
    factory. Uses the real validator, not a mock.
  - test_mutations_are_rejected: negative tests — overriding a required
    field MUST produce a validation failure. Proves the factory's output
    is genuinely valid, not just accepted by a permissive validator.
  - test_factories_are_mutually_independent: each factory returns a new
    dict, not a shared reference.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tests.conftest import (
    make_split_action,
    make_dividend_action,
    make_symbol_change_action,
)
from tools.validate import validate_actions_data


# Canonical fixture context shared with the validator
IDENTIFIERS = str(Path(__file__).resolve().parent / "fixtures" / "identifiers.json")
ISO4217 = str(Path(__file__).resolve().parent / "fixtures" / "iso4217.json")
EXCHANGE_CAL = str(Path(__file__).resolve().parent / "fixtures" / "exchange_calendar.json")


def _validate(actions: list) -> list:
    """Run the real validator on a list of actions and return error list."""
    doc = {"meta": {}, "actions": actions}
    return validate_actions_data(
        doc,
        identifiers_path=IDENTIFIERS,
        iso4217_path=ISO4217,
        exchange_calendar_path=EXCHANGE_CAL,
    )


# ---------------------------------------------------------------------------
# Positive: each factory produces a validator-accepted action
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("factory,name", [
    (make_split_action, "make_split_action"),
    (make_dividend_action, "make_dividend_action"),
    (make_symbol_change_action, "make_symbol_change_action"),
])
def test_factory_output_passes_full_validation(factory, name):
    """The factory's output must survive every validation layer."""
    action = factory()
    errors = _validate([action])
    assert not errors, (
        f"{name}() produced an action the validator rejects:\n"
        + "\n".join(f"  {e}" for e in errors)
    )


# ---------------------------------------------------------------------------
# Negative: mutations of the factory output ARE rejected (proves validation is real)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mutation,reason", [
    # Required field removed
    (lambda a: a.pop("action_id", None), "missing action_id"),
    (lambda a: a.pop("isin", None), "missing isin"),
    (lambda a: a.pop("redistribution", None), "missing redistribution"),
    (lambda a: a.pop("provenance", None), "missing provenance"),
    (lambda a: a.pop("dates", None), "missing dates"),
    # Malformed values
    (lambda a: a.__setitem__("action_type", "NOT_A_TYPE"), "invalid action_type"),
    (lambda a: a.__setitem__("redistribution", "restricted"), "restricted redistribution"),
    # Temporal violation: ex_date before announcement
    (lambda a: a["dates"].__setitem__("ex_date", "2020-01-01"), "ex_date < announcement"),
])
def test_factory_mutation_is_rejected(mutation, reason):
    """A mutation of a factory-produced action must fail validation.

    If any of these pass, the validator is permissive enough that a broken
    factory would go unnoticed. This proves the factory's output is
    genuinely valid, not just "not obviously broken."
    """
    action = make_dividend_action()  # has all fields
    mutation(action)
    errors = _validate([action])
    assert errors, (
        f"validator accepted a mutated action ({reason}). "
        f"This means the factory's output is not actually being validated."
    )


# ---------------------------------------------------------------------------
# Independence: factories return fresh dicts, not shared references
# ---------------------------------------------------------------------------

def test_factories_are_mutually_independent():
    """Mutating one factory output must not affect another call."""
    a1 = make_split_action()
    a2 = make_split_action()
    a1["isin"] = "CORRUPT"
    assert a2["isin"] != "CORRUPT", "factories return the same underlying object"


def test_factory_return_value_is_a_fresh_dict():
    """Each call returns a new dict, not a module-level singleton."""
    a1 = make_split_action()
    a2 = make_split_action()
    assert a1 is not a2

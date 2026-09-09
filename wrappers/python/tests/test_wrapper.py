"""
Comprehensive tests for the Python wrapper of the Corporate Actions Registry.

These tests validate the CorporateActionsRegistry class and the data
models (Action, Dates, Provenance, Impact, RegistryMeta) using a small
in-memory sample dataset. They do not depend on the production actions.json,
so they are stable and repeatable.

Run from the repo root:
    pytest wrappers/python/tests/test_wrapper.py
or from wrappers/python:
    pytest tests/test_wrapper.py
"""

import json
import sys
from pathlib import Path

import pytest

# Ensure the wrapper package can be imported when running tests directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from corporate_actions_registry import CorporateActionsRegistry
from corporate_actions_registry.models import Action, Dates, Provenance, Impact, RegistryMeta


# ----------------------------------------------------------------------
# Sample data and fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def sample_actions_data():
    """A minimal but representative actions.json structure."""
    return {
        "meta": {
            "version": "1.0.0",
            "generated_at": "2026-09-09T12:00:00Z",
            "source": "Test",
            "notes": "Sample data for testing",
        },
        "actions": [
            {
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
                    "verification_source": "SEC EDGAR",
                },
                "impact": {
                    "price_multiplier": 0.1,
                    "share_multiplier": 10.0,
                },
            },
            {
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
                "impact": {
                    "cash_adjustment": 0.25,
                    "price_multiplier": 1.0,
                    "share_multiplier": 1.0,
                },
            },
            {
                "isin": "US0378331005",
                "action_id": "US0378331005-SPLIT-2020-08-31-0003",
                "action_type": "SPLIT",
                "ratio": "4:1",
                "dates": {
                    "announcement": "2020-07-30",
                    "ex_date": "2020-08-31",
                    "record_date": "2020-08-24",
                    "effective_date": "2020-08-31",
                },
                "status": "COMPLETED",
                "provenance": {
                    "source": "Apple",
                    "source_url": "https://example.com/aapl-split",
                },
                "impact": {
                    "price_multiplier": 0.25,
                    "share_multiplier": 4.0,
                },
            },
            {
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
                "impact": {},
            },
        ],
    }


@pytest.fixture
def registry(sample_actions_data):
    return CorporateActionsRegistry(actions_data=sample_actions_data)


@pytest.fixture
def registry_from_file(sample_actions_data, tmp_path):
    file_path = tmp_path / "actions.json"
    file_path.write_text(json.dumps(sample_actions_data), encoding="utf-8")
    return CorporateActionsRegistry(actions_path=str(file_path))


# ----------------------------------------------------------------------
# Tests for loading and basic attributes
# ----------------------------------------------------------------------

class TestLoading:
    def test_load_from_dict(self, registry):
        assert registry.count() == 4
        assert isinstance(registry.meta, RegistryMeta)
        assert registry.meta.version == "1.0.0"
        assert registry.meta.source == "Test"

    def test_load_from_file(self, registry_from_file):
        assert registry_from_file.count() == 4
        assert registry_from_file.meta.version == "1.0.0"

    def test_load_invalid_data_raises(self):
        with pytest.raises(ValueError):
            CorporateActionsRegistry(actions_data={"bad": "data"})

    def test_load_without_path_or_data_raises(self):
        with pytest.raises(ValueError):
            CorporateActionsRegistry()

    def test_repr(self, registry):
        assert repr(registry) == "<CorporateActionsRegistry actions=4>"


# ----------------------------------------------------------------------
# Tests for lookup methods
# ----------------------------------------------------------------------

class TestLookups:
    def test_by_isin_returns_correct_actions(self, registry):
        aapl = registry.by_isin("US0378331005")
        assert len(aapl) == 2
        assert all(a.isin == "US0378331005" for a in aapl)

    def test_by_isin_no_results(self, registry):
        assert registry.by_isin("US0000000000") == []

    def test_by_action_id_found(self, registry):
        action = registry.by_action_id("US67066G1040-SPLIT-2024-06-10-0001")
        assert action is not None
        assert action.action_type == "SPLIT"
        assert action.ratio == "10:1"

    def test_by_action_id_not_found(self, registry):
        assert registry.by_action_id("NONEXISTENT") is None

    def test_by_action_type(self, registry):
        splits = registry.by_action_type("SPLIT")
        assert len(splits) == 2
        for s in splits:
            assert s.action_type == "SPLIT"

    def test_by_action_type_no_results(self, registry):
        assert registry.by_action_type("MERGER") == []

    def test_by_date_range_on_ex_date(self, registry):
        # Should include actions with ex_date between 2020-01-01 and 2023-12-31
        actions = registry.by_date_range(start_date="2020-01-01", end_date="2023-12-31")
        # Only AAPL 2020 split is in that range
        assert len(actions) == 1
        assert actions[0].action_id == "US0378331005-SPLIT-2020-08-31-0003"

    def test_by_date_range_on_effective_date(self, registry):
        actions = registry.by_date_range(
            start_date="2024-01-01",
            end_date="2024-12-31",
            date_field="effective_date",
        )
        # NVDA split (2024-06-10), AAPL dividend (2024-05-23), AAPL split? no, that's 2020.
        # Symbol change 2022 not included. So two actions.
        assert len(actions) == 2

    def test_all_action_types(self, registry):
        types = registry.all_action_types()
        assert types == ["DIVIDEND", "SPLIT", "SYMBOL_CHANGE"]


# ----------------------------------------------------------------------
# Tests for serialization
# ----------------------------------------------------------------------

class TestSerialization:
    def test_to_dict_round_trip(self, registry):
        data = registry.to_dict()
        assert isinstance(data, dict)
        assert "meta" in data
        assert "actions" in data
        assert len(data["actions"]) == 4

    def test_save_and_reload(self, registry, tmp_path):
        out_path = tmp_path / "out_actions.json"
        registry.save(str(out_path))
        reloaded = CorporateActionsRegistry(actions_path=str(out_path))
        assert reloaded.count() == registry.count()
        assert reloaded.to_dict() == registry.to_dict()


# ----------------------------------------------------------------------
# Tests for data models
# ----------------------------------------------------------------------

class TestModels:
    def test_action_from_dict_complete(self):
        raw = {
            "isin": "US0378331005",
            "action_id": "ID-1",
            "action_type": "DIVIDEND",
            "amount": 0.25,
            "currency": "USD",
            "dates": {"announcement": "2024-01-01", "ex_date": "2024-01-15", "record_date": "2024-01-16", "effective_date": "2024-01-20"},
            "status": "COMPLETED",
            "provenance": {"source": "Test", "source_url": "https://example.com"},
            "impact": {"cash_adjustment": 0.25},
        }
        action = Action.from_dict(raw)
        assert action.isin == "US0378331005"
        assert action.action_type == "DIVIDEND"
        assert action.amount == 0.25
        assert action.dates.ex_date == "2024-01-15"
        assert action.provenance.source == "Test"
        assert action.impact.cash_adjustment == 0.25

    def test_action_from_dict_with_nulls(self):
        raw = {
            "isin": "US30303M1027",
            "action_id": "ID-2",
            "action_type": "SYMBOL_CHANGE",
            "dates": {"announcement": "2022-06-09", "effective_date": "2022-06-09"},
        }
        action = Action.from_dict(raw)
        assert action.amount is None
        assert action.ratio is None
        assert action.dates.ex_date is None
        assert action.provenance.source is None
        assert action.impact.price_multiplier is None

    def test_action_to_dict_round_trip(self):
        raw = {
            "isin": "US67066G1040",
            "action_id": "ID-3",
            "action_type": "SPLIT",
            "ratio": "10:1",
            "dates": {"announcement": "2024-05-22", "ex_date": "2024-06-10"},
            "provenance": {"source": "NVIDIA"},
            "impact": {"price_multiplier": 0.1, "share_multiplier": 10.0},
        }
        action = Action.from_dict(raw)
        out = action.to_dict()
        # Ensure None values are dropped from nested dicts but required fields remain
        assert "dates" in out
        assert out["dates"]["ex_date"] == "2024-06-10"
        assert "record_date" not in out["dates"]  # None dropped
        assert "source_url" not in out["provenance"]  # None dropped
        assert "cash_adjustment" not in out["impact"]  # None dropped

    def test_dates_model(self):
        d = Dates.from_dict({"announcement": "2024-01-01", "ex_date": "2024-01-15"})
        assert d.announcement == "2024-01-01"
        assert d.ex_date == "2024-01-15"
        assert d.record_date is None
        d2 = d.to_dict()
        assert "record_date" not in d2

    def test_provenance_model(self):
        p = Provenance.from_dict({"source": "Test", "source_url": "https://example.com"})
        assert p.source == "Test"
        assert p.verification_source is None
        assert "verification_source" not in p.to_dict()

    def test_impact_model(self):
        i = Impact.from_dict({"cash_adjustment": 0.25})
        assert i.cash_adjustment == 0.25
        assert i.price_multiplier is None
        assert "price_multiplier" not in i.to_dict()

    def test_meta_model(self):
        m = RegistryMeta.from_dict({"version": "1.0.0", "source": "Test"})
        assert m.version == "1.0.0"
        assert m.generated_at is None
        assert "generated_at" not in m.to_dict()
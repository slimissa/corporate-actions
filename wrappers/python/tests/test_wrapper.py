"""
Comprehensive tests for the Python wrapper of the Corporate Actions
Registry.

These tests validate both the registry class and the data models. They
run against a small in-memory dataset and against a temporary file, so
they do not depend on the production actions.json and are stable across
runs.

The tests encode the contract in docs/wrapper_contract.md. When a test
fails, either the wrapper has drifted from the contract or the contract
needs to change; both are visible from the failure message.

Run from the repo root:
    python -m pytest wrappers/python/tests/test_wrapper.py -v
or from wrappers/python:
    python -m pytest tests/test_wrapper.py -v
"""

import json
import sys
from pathlib import Path

import pytest

# Ensure the wrapper package can be imported when running tests directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from corporate_actions_registry import CorporateActionsRegistry
from corporate_actions_registry.models import (
    Action,
    Dates,
    Impact,
    Provenance,
    RegistryMeta,
)


# ----------------------------------------------------------------------
# Sample data and fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def sample_actions_data():
    """A minimal but representative actions.json structure.

    Four actions across three ISINs:

      - NVDA 10:1 split on 2024-06-10
      - AAPL dividend on 2024-05-16
      - AAPL 4:1 split on 2020-08-31
      - META symbol change on 2022-06-09

    The spread of dates and the presence of an action with no ex_date
    let the date-range tests exercise inclusive bounds, missing fields,
    and sorting.
    """
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
                "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
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
                "action_id": "US0378331005-DIVIDEND-2024-05-16-0.2500",
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
                "action_id": "US0378331005-SPLIT-2020-08-31-4-1",
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
                "action_id": "US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL",
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
    """A registry built from the in-memory fixture."""
    return CorporateActionsRegistry(actions_data=sample_actions_data)


@pytest.fixture
def registry_from_file(sample_actions_data, tmp_path):
    """A registry built from a file on disk."""
    file_path = tmp_path / "actions.json"
    file_path.write_text(json.dumps(sample_actions_data), encoding="utf-8")
    return CorporateActionsRegistry(actions_path=str(file_path))


@pytest.fixture
def tiebreak_data():
    """Two actions sharing the same ex_date, different action_ids.

    Used to prove that by_date_range breaks ties on action_id, not on
    insertion order.
    """
    return {
        "meta": {"version": "1.0.0", "generated_at": "2026-09-09T00:00:00Z",
                 "source": "Test"},
        "actions": [
            {
                "isin": "US0000000001",
                "action_id": "US0000000001-DIVIDEND-2024-05-16-0.2500",
                "action_type": "DIVIDEND",
                "dates": {"announcement": "2024-05-02",
                          "ex_date": "2024-05-16",
                          "effective_date": "2024-05-23"},
            },
            {
                "isin": "US0000000002",
                "action_id": "US0000000002-DIVIDEND-2024-05-16-0.3000",
                "action_type": "DIVIDEND",
                "dates": {"announcement": "2024-05-02",
                          "ex_date": "2024-05-16",
                          "effective_date": "2024-05-23"},
            },
        ],
    }


# ----------------------------------------------------------------------
# Loading
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

    def test_load_from_dict_takes_precedence_over_path(
        self, sample_actions_data, tmp_path,
    ):
        # Provide both; actions_data wins.
        file_path = tmp_path / "nonexistent.json"
        registry = CorporateActionsRegistry(
            actions_path=str(file_path),
            actions_data=sample_actions_data,
        )
        assert registry.count() == 4

    def test_load_without_path_or_data_raises(self):
        with pytest.raises(ValueError):
            CorporateActionsRegistry()

    def test_load_invalid_data_raises(self):
        with pytest.raises(ValueError):
            CorporateActionsRegistry(actions_data={"bad": "data"})

    def test_load_missing_actions_key_raises(self):
        with pytest.raises(ValueError, match="actions"):
            CorporateActionsRegistry(actions_data={"meta": {}})

    def test_load_actions_not_a_list_raises(self):
        with pytest.raises(ValueError):
            CorporateActionsRegistry(actions_data={"actions": "not a list"})

    def test_load_top_level_not_dict_raises(self):
        with pytest.raises(ValueError):
            CorporateActionsRegistry(actions_data=["not", "a", "dict"])

    def test_load_missing_file_raises_filenotfound(self, tmp_path):
        path = tmp_path / "nope.json"
        with pytest.raises(FileNotFoundError):
            CorporateActionsRegistry(actions_path=str(path))

    def test_load_invalid_json_raises(self, tmp_path):
        path = tmp_path / "actions.json"
        path.write_text("{ not valid json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            CorporateActionsRegistry(actions_path=str(path))

    def test_load_bom_prefixed_file(self, sample_actions_data, tmp_path):
        """A file saved through a Windows editor carries a UTF-8 BOM."""
        path = tmp_path / "actions.json"
        payload = json.dumps(sample_actions_data).encode("utf-8")
        path.write_bytes(b"\xef\xbb\xbf" + payload)
        registry = CorporateActionsRegistry(actions_path=str(path))
        assert registry.count() == 4

    def test_load_empty_actions_list(self):
        """An empty registry is valid; every lookup returns nothing."""
        registry = CorporateActionsRegistry(
            actions_data={"meta": {}, "actions": []},
        )
        assert registry.count() == 0
        assert registry.by_isin("US0378331005") == []
        assert registry.by_action_type("SPLIT") == []
        assert registry.all_action_types() == []

    def test_load_missing_meta_is_ok(self):
        """`meta` is optional; a missing one yields an empty RegistryMeta."""
        registry = CorporateActionsRegistry(actions_data={"actions": []})
        assert isinstance(registry.meta, RegistryMeta)
        assert registry.meta.version is None

    def test_load_non_object_action_raises(self):
        """An entry in the actions array that is not a JSON object is a
        structural error. See docs/wrapper_contract.md section 5.4."""
        with pytest.raises(ValueError, match="not an object"):
            CorporateActionsRegistry(
                actions_data={"actions": ["not an object"]},
            )

    def test_load_actions_is_dict_not_list_raises(self):
        """An actions value that is an object, not an array, is an error."""
        with pytest.raises(ValueError, match="must be a list"):
            CorporateActionsRegistry(
                actions_data={"actions": {"not": "a list"}},
            )

    def test_repr(self, registry):
        assert repr(registry) == "<CorporateActionsRegistry actions=4>"

    def test_len(self, registry):
        assert len(registry) == 4


# ----------------------------------------------------------------------
# by_isin
# ----------------------------------------------------------------------

class TestByIsin:

    def test_returns_correct_actions(self, registry):
        aapl = registry.by_isin("US0378331005")
        assert len(aapl) == 2
        assert all(a.isin == "US0378331005" for a in aapl)

    def test_unknown_isin_returns_empty(self, registry):
        assert registry.by_isin("US0000000000") == []

    def test_is_case_sensitive(self, registry):
        """ISINs are uppercase; a lowercase query returns nothing."""
        assert registry.by_isin("us0378331005") == []

    def test_returns_fresh_list(self, registry):
        """Mutating the returned list must not affect internal state."""
        first = registry.by_isin("US0378331005")
        first.clear()
        second = registry.by_isin("US0378331005")
        assert len(second) == 2

    def test_returns_actions_in_insertion_order(self, registry):
        """The index preserves the order actions appear in the file."""
        aapl = registry.by_isin("US0378331005")
        ids = [a.action_id for a in aapl]
        assert ids == [
            "US0378331005-DIVIDEND-2024-05-16-0.2500",
            "US0378331005-SPLIT-2020-08-31-4-1",
        ]


# ----------------------------------------------------------------------
# by_action_id
# ----------------------------------------------------------------------

class TestByActionId:

    def test_found(self, registry):
        action = registry.by_action_id("US67066G1040-SPLIT-2024-06-10-10-1")
        assert action is not None
        assert action.action_type == "SPLIT"
        assert action.ratio == "10:1"

    def test_not_found_returns_none(self, registry):
        assert registry.by_action_id("NONEXISTENT") is None

    def test_returns_deep_copy(self, registry):
        """Mutating the returned action must not affect internal state."""
        action = registry.by_action_id("US67066G1040-SPLIT-2024-06-10-10-1")
        action.ratio = "999:1"
        action.dates.ex_date = "1900-01-01"

        again = registry.by_action_id("US67066G1040-SPLIT-2024-06-10-10-1")
        assert again.ratio == "10:1"
        assert again.dates.ex_date == "2024-06-10"

    def test_dates_are_a_fresh_object(self, registry):
        action = registry.by_action_id("US0378331005-DIVIDEND-2024-05-16-0.2500")
        action.dates.record_date = "1970-01-01"
        again = registry.by_action_id("US0378331005-DIVIDEND-2024-05-16-0.2500")
        assert again.dates.record_date == "2024-05-17"

    def test_provenance_is_a_fresh_object(self, registry):
        action = registry.by_action_id("US0378331005-DIVIDEND-2024-05-16-0.2500")
        action.provenance.source = "mutated"
        again = registry.by_action_id("US0378331005-DIVIDEND-2024-05-16-0.2500")
        assert again.provenance.source == "Apple"

    def test_impact_is_a_fresh_object(self, registry):
        action = registry.by_action_id("US0378331005-DIVIDEND-2024-05-16-0.2500")
        action.impact.cash_adjustment = 999.0
        again = registry.by_action_id("US0378331005-DIVIDEND-2024-05-16-0.2500")
        assert again.impact.cash_adjustment == 0.25

    def test_repeated_calls_return_equal_but_distinct_objects(self, registry):
        a = registry.by_action_id("US67066G1040-SPLIT-2024-06-10-10-1")
        b = registry.by_action_id("US67066G1040-SPLIT-2024-06-10-10-1")
        assert a is not b
        assert a.action_id == b.action_id
        assert a.dates.ex_date == b.dates.ex_date


# ----------------------------------------------------------------------
# by_action_type
# ----------------------------------------------------------------------

class TestByActionType:

    def test_splits(self, registry):
        splits = registry.by_action_type("SPLIT")
        assert len(splits) == 2
        assert all(a.action_type == "SPLIT" for a in splits)

    def test_dividends(self, registry):
        divs = registry.by_action_type("DIVIDEND")
        assert len(divs) == 1
        assert divs[0].amount == 0.25

    def test_symbol_changes(self, registry):
        changes = registry.by_action_type("SYMBOL_CHANGE")
        assert len(changes) == 1

    def test_unknown_type_returns_empty(self, registry):
        assert registry.by_action_type("MERGER") == []

    def test_case_sensitive(self, registry):
        assert registry.by_action_type("split") == []

    def test_returns_fresh_list(self, registry):
        first = registry.by_action_type("SPLIT")
        first.clear()
        second = registry.by_action_type("SPLIT")
        assert len(second) == 2


# ----------------------------------------------------------------------
# by_date_range
# ----------------------------------------------------------------------

class TestByDateRange:
    """Rules from docs/wrapper_contract.md section 4.4."""

    # ---- Default field ------------------------------------------------

    def test_default_field_is_ex_date(self, registry):
        with_default = registry.by_date_range("2024-01-01", "2024-12-31")
        with_explicit = registry.by_date_range(
            "2024-01-01", "2024-12-31", "ex_date",
        )
        assert [a.action_id for a in with_default] == [
            a.action_id for a in with_explicit
        ]

    # ---- Valid fields -------------------------------------------------

    def test_ex_date(self, registry):
        result = registry.by_date_range("2020-01-01", "2023-12-31", "ex_date")
        assert len(result) == 1
        assert result[0].action_id == "US0378331005-SPLIT-2020-08-31-4-1"

    def test_effective_date(self, registry):
        result = registry.by_date_range(
            "2020-01-01", "2023-12-31", "effective_date",
        )
        assert len(result) == 2
        ids = [a.action_id for a in result]
        assert "US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL" in ids
        assert "US0378331005-SPLIT-2020-08-31-4-1" in ids

    def test_announcement(self, registry):
        result = registry.by_date_range(
            "2022-01-01", "2023-12-31", "announcement",
        )
        assert len(result) == 1
        assert result[0].action_id == "US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL"

    def test_record_date(self, registry):
        result = registry.by_date_range(
            "2020-01-01", "2024-12-31", "record_date",
        )
        # Three of the four have record_date; SYMBOL_CHANGE has none.
        assert len(result) == 3

    # ---- Invalid field ------------------------------------------------

    @pytest.mark.parametrize("bad_field", [
        "exdate",
        "ex-date",
        "effective",
        "Ex_Date",
        "EX_DATE",
        "ex_date ",
        " ex_date",
        "",
    ])
    def test_invalid_field_raises(self, registry, bad_field):
        with pytest.raises(ValueError, match="invalid date_field"):
            registry.by_date_range(None, None, bad_field)

    def test_error_message_names_the_offending_value(self, registry):
        with pytest.raises(ValueError, match="'exdate'"):
            registry.by_date_range(None, None, "exdate")

    def test_error_message_lists_valid_values(self, registry):
        with pytest.raises(ValueError) as exc_info:
            registry.by_date_range(None, None, "exdate")
        message = str(exc_info.value)
        for valid in ("announcement", "ex_date", "record_date", "effective_date"):
            assert valid in message

    # ---- Inclusive bounds ---------------------------------------------

    def test_start_bound_is_inclusive(self, registry):
        # 2024-05-16 is the ex_date of the AAPL dividend.
        result = registry.by_date_range("2024-05-16", "2024-12-31", "ex_date")
        ids = [a.action_id for a in result]
        assert "US0378331005-DIVIDEND-2024-05-16-0.2500" in ids

    def test_end_bound_is_inclusive(self, registry):
        result = registry.by_date_range("2020-01-01", "2024-05-16", "ex_date")
        ids = [a.action_id for a in result]
        assert "US0378331005-DIVIDEND-2024-05-16-0.2500" in ids

    def test_exact_single_date(self, registry):
        result = registry.by_date_range("2024-05-16", "2024-05-16", "ex_date")
        assert len(result) == 1
        assert result[0].action_id == "US0378331005-DIVIDEND-2024-05-16-0.2500"

    # ---- Open bounds --------------------------------------------------

    def test_open_start(self, registry):
        result = registry.by_date_range(None, "2024-01-01", "ex_date")
        # Both 2020 and 2022 actions; the 2024 ones are excluded.
        assert len(result) == 1
        assert result[0].action_id == "US0378331005-SPLIT-2020-08-31-4-1"

    def test_open_end(self, registry):
        result = registry.by_date_range("2024-01-01", None, "ex_date")
        assert len(result) == 2

    def test_both_bounds_open(self, registry):
        result = registry.by_date_range(None, None, "ex_date")
        # All actions with an ex_date: three of the four.
        assert len(result) == 3

    def test_empty_string_bound_is_open(self, registry):
        """An empty string is treated the same as None."""
        with_none = registry.by_date_range(None, None, "ex_date")
        with_empty = registry.by_date_range("", "", "ex_date")
        assert [a.action_id for a in with_none] == [
            a.action_id for a in with_empty
        ]

    # ---- Skipping actions without the field ---------------------------

    def test_actions_without_ex_date_are_skipped(self, registry):
        """SYMBOL_CHANGE has no ex_date; asking for ex_date excludes it."""
        result = registry.by_date_range(None, None, "ex_date")
        ids = [a.action_id for a in result]
        assert "US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL" not in ids

    def test_actions_without_record_date_are_skipped(self, registry):
        result = registry.by_date_range(None, None, "record_date")
        ids = [a.action_id for a in result]
        assert "US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL" not in ids

    # ---- Sorting ------------------------------------------------------

    def test_results_are_sorted_by_field(self, registry):
        result = registry.by_date_range(None, None, "ex_date")
        dates = [a.dates.ex_date for a in result]
        assert dates == sorted(dates)

    def test_results_are_sorted_by_effective_date(self, registry):
        result = registry.by_date_range(None, None, "effective_date")
        dates = [a.dates.effective_date for a in result]
        assert dates == sorted(dates)

    def test_tiebreak_on_action_id(self, tiebreak_data):
        registry = CorporateActionsRegistry(actions_data=tiebreak_data)
        result = registry.by_date_range(None, None, "ex_date")
        ids = [a.action_id for a in result]
        # Both have ex_date = 2024-05-16; sort by action_id.
        assert ids == [
            "US0000000001-DIVIDEND-2024-05-16-0.2500",
            "US0000000002-DIVIDEND-2024-05-16-0.3000",
        ]

    def test_sorted_regardless_of_input_order(self, sample_actions_data):
        # Reverse the actions in the input; the output must be the same.
        reversed_data = {
            "meta": sample_actions_data["meta"],
            "actions": list(reversed(sample_actions_data["actions"])),
        }
        reg = CorporateActionsRegistry(actions_data=reversed_data)
        result = reg.by_date_range(None, None, "ex_date")
        dates = [a.dates.ex_date for a in result]
        assert dates == sorted(dates)

    # ---- Fresh list ---------------------------------------------------

    def test_returns_fresh_list(self, registry):
        first = registry.by_date_range(None, None, "ex_date")
        first.clear()
        second = registry.by_date_range(None, None, "ex_date")
        assert len(second) == 3


# ----------------------------------------------------------------------
# all_action_types
# ----------------------------------------------------------------------

class TestAllActionTypes:

    def test_sorted_list(self, registry):
        types = registry.all_action_types()
        assert types == ["DIVIDEND", "SPLIT", "SYMBOL_CHANGE"]

    def test_unique_values(self, registry):
        types = registry.all_action_types()
        assert len(types) == len(set(types))

    def test_empty_registry(self):
        registry = CorporateActionsRegistry(
            actions_data={"actions": []},
        )
        assert registry.all_action_types() == []

    def test_reflects_only_present_types(self, registry):
        """Reserved types that are not in the data do not appear."""
        assert "MERGER" not in registry.all_action_types()
        assert "SPINOFF" not in registry.all_action_types()
        assert "REVERSE_SPLIT" not in registry.all_action_types()


# ----------------------------------------------------------------------
# count / len / repr
# ----------------------------------------------------------------------

class TestCount:

    def test_count(self, registry):
        assert registry.count() == 4

    def test_empty(self):
        registry = CorporateActionsRegistry(actions_data={"actions": []})
        assert registry.count() == 0

    def test_matches_len_of_actions_list(self, registry):
        assert registry.count() == len(registry.actions)

    def test_matches_len_builtin(self, registry):
        assert registry.count() == len(registry)


# ----------------------------------------------------------------------
# Serialization
# ----------------------------------------------------------------------

class TestSerialization:

    def test_to_dict_shape(self, registry):
        data = registry.to_dict()
        assert isinstance(data, dict)
        assert set(data.keys()) == {"meta", "actions"}
        assert len(data["actions"]) == 4

    def test_to_dict_preserves_meta(self, registry):
        data = registry.to_dict()
        assert data["meta"]["version"] == "1.0.0"
        assert data["meta"]["source"] == "Test"

    def test_to_dict_preserves_action_fields(self, registry):
        data = registry.to_dict()
        first = data["actions"][0]
        assert first["isin"] == "US67066G1040"
        assert first["action_type"] == "SPLIT"
        assert first["ratio"] == "10:1"
        assert first["dates"]["ex_date"] == "2024-06-10"

    def test_save_and_reload(self, registry, tmp_path):
        out_path = tmp_path / "out_actions.json"
        registry.save(str(out_path))
        reloaded = CorporateActionsRegistry(actions_path=str(out_path))
        assert reloaded.count() == registry.count()
        assert reloaded.to_dict() == registry.to_dict()

    def test_save_produces_valid_json(self, registry, tmp_path):
        out_path = tmp_path / "out_actions.json"
        registry.save(str(out_path))
        # Parse it standalone; if it is invalid, JSONDecodeError will fire.
        parsed = json.loads(out_path.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)
        assert "actions" in parsed

    def test_save_produces_utf8(self, registry, tmp_path):
        out_path = tmp_path / "out_actions.json"
        registry.save(str(out_path))
        # Readable as UTF-8 without error.
        out_path.read_text(encoding="utf-8")

    def test_save_no_bom_written(self, registry, tmp_path):
        """A file we wrote does not carry a BOM (so we do not introduce
        one when writing)."""
        out_path = tmp_path / "out_actions.json"
        registry.save(str(out_path))
        first_bytes = out_path.read_bytes()[:3]
        assert first_bytes != b"\xef\xbb\xbf"

    def test_empty_registry_round_trip(self, tmp_path):
        registry = CorporateActionsRegistry(
            actions_data={"meta": {}, "actions": []},
        )
        out_path = tmp_path / "empty.json"
        registry.save(str(out_path))
        reloaded = CorporateActionsRegistry(actions_path=str(out_path))
        assert reloaded.count() == 0


# ----------------------------------------------------------------------
# Data models
# ----------------------------------------------------------------------

class TestDatesModel:

    def test_from_dict_complete(self):
        d = Dates.from_dict({
            "announcement": "2024-01-01",
            "ex_date": "2024-01-15",
            "record_date": "2024-01-16",
            "effective_date": "2024-01-20",
        })
        assert d.announcement == "2024-01-01"
        assert d.ex_date == "2024-01-15"
        assert d.record_date == "2024-01-16"
        assert d.effective_date == "2024-01-20"

    def test_from_dict_partial(self):
        d = Dates.from_dict({"announcement": "2024-01-01"})
        assert d.announcement == "2024-01-01"
        assert d.ex_date is None

    def test_from_dict_none_returns_empty(self):
        d = Dates.from_dict(None)
        assert d.announcement is None
        assert d.ex_date is None

    def test_from_dict_non_dict_returns_empty(self):
        d = Dates.from_dict("not a dict")  # type: ignore[arg-type]
        assert d.announcement is None

    def test_to_dict_drops_none(self):
        d = Dates.from_dict({"announcement": "2024-01-01"})
        out = d.to_dict()
        assert out == {"announcement": "2024-01-01"}
        assert "ex_date" not in out
        assert "record_date" not in out
        assert "effective_date" not in out

    def test_to_dict_keeps_all_present(self):
        d = Dates(
            announcement="2024-01-01",
            ex_date="2024-01-15",
            record_date="2024-01-16",
            effective_date="2024-01-20",
        )
        assert d.to_dict() == {
            "announcement": "2024-01-01",
            "ex_date": "2024-01-15",
            "record_date": "2024-01-16",
            "effective_date": "2024-01-20",
        }


class TestProvenanceModel:

    def test_from_dict_complete(self):
        p = Provenance.from_dict({
            "source": "Test",
            "source_url": "https://example.com",
            "verification_source": "SEC",
            "verification_url": "https://sec.gov",
        })
        assert p.source == "Test"
        assert p.verification_source == "SEC"

    def test_from_dict_none(self):
        p = Provenance.from_dict(None)
        assert p.source is None

    def test_to_dict_drops_none(self):
        p = Provenance.from_dict({"source": "Test"})
        out = p.to_dict()
        assert out == {"source": "Test"}
        assert "source_url" not in out
        assert "verification_source" not in out
        assert "verification_url" not in out


class TestImpactModel:

    def test_from_dict_complete(self):
        i = Impact.from_dict({
            "price_multiplier": 0.1,
            "share_multiplier": 10.0,
            "cash_adjustment": 0.0,
        })
        assert i.price_multiplier == 0.1
        assert i.share_multiplier == 10.0
        assert i.cash_adjustment == 0.0

    def test_zero_values_are_preserved(self):
        """A zero multiplier is not the same as a missing one."""
        i = Impact.from_dict({"cash_adjustment": 0.0})
        assert i.cash_adjustment == 0.0
        assert "cash_adjustment" in i.to_dict()

    def test_to_dict_drops_none(self):
        i = Impact.from_dict({"cash_adjustment": 0.25})
        out = i.to_dict()
        assert out == {"cash_adjustment": 0.25}
        assert "price_multiplier" not in out
        assert "share_multiplier" not in out


class TestActionModel:

    def test_from_dict_complete(self):
        raw = {
            "isin": "US0378331005",
            "action_id": "ID-1",
            "action_type": "DIVIDEND",
            "amount": 0.25,
            "currency": "USD",
            "dates": {
                "announcement": "2024-01-01",
                "ex_date": "2024-01-15",
                "record_date": "2024-01-16",
                "effective_date": "2024-01-20",
            },
            "status": "COMPLETED",
            "provenance": {
                "source": "Test",
                "source_url": "https://example.com",
            },
            "impact": {"cash_adjustment": 0.25},
        }
        action = Action.from_dict(raw)
        assert action.isin == "US0378331005"
        assert action.action_type == "DIVIDEND"
        assert action.amount == 0.25
        assert action.currency == "USD"
        assert action.dates.ex_date == "2024-01-15"
        assert action.provenance.source == "Test"
        assert action.impact.cash_adjustment == 0.25

    def test_from_dict_minimal(self):
        action = Action.from_dict({
            "isin": "US30303M1027",
            "action_id": "ID-2",
            "action_type": "SYMBOL_CHANGE",
            "dates": {
                "announcement": "2022-06-09",
                "effective_date": "2022-06-09",
            },
        })
        assert action.amount is None
        assert action.ratio is None
        assert action.currency is None
        assert action.dates.ex_date is None
        assert action.provenance.source is None
        assert action.impact.price_multiplier is None

    def test_from_dict_non_dict_returns_empty(self):
        action = Action.from_dict("not a dict")  # type: ignore[arg-type]
        assert action.isin is None
        assert action.action_id is None

    def test_to_dict_drops_explicit_nulls(self):
        """The rename from test_action_to_dict_round_trip: to_dict()
        drops None, it does not preserve round-trip shape."""
        raw = {
            "isin": "US67066G1040",
            "action_id": "ID-3",
            "action_type": "SPLIT",
            "ratio": "10:1",
            "dates": {
                "announcement": "2024-05-22",
                "ex_date": "2024-06-10",
            },
            "provenance": {"source": "NVIDIA"},
            "impact": {"price_multiplier": 0.1, "share_multiplier": 10.0},
        }
        action = Action.from_dict(raw)
        out = action.to_dict()
        assert out["dates"]["ex_date"] == "2024-06-10"
        assert "record_date" not in out["dates"]
        assert "source_url" not in out["provenance"]
        assert "cash_adjustment" not in out["impact"]

    def test_to_dict_preserves_explicit_nulls_as_dropped(self):
        """The fixture stores record_date=None; to_dict drops it."""
        raw = {
            "isin": "US0378331005",
            "action_id": "ID-NULL",
            "action_type": "DIVIDEND",
            "dates": {
                "announcement": "2024-05-02",
                "ex_date": "2024-05-16",
                "record_date": None,
                "effective_date": "2024-05-23",
            },
        }
        action = Action.from_dict(raw)
        out = action.to_dict()
        assert "record_date" not in out["dates"]

    def test_equality_between_equal_actions(self):
        raw = {
            "isin": "US0378331005",
            "action_id": "ID-EQ",
            "action_type": "DIVIDEND",
            "dates": {"announcement": "2024-01-01", "effective_date": "2024-01-01"},
        }
        a = Action.from_dict(raw)
        b = Action.from_dict(raw)
        # Dataclasses provide __eq__ based on fields.
        assert a == b


class TestRegistryMetaModel:

    def test_from_dict_complete(self):
        m = RegistryMeta.from_dict({
            "version": "1.0.0",
            "generated_at": "2026-09-09T12:00:00Z",
            "source": "Test",
            "notes": "sample",
        })
        assert m.version == "1.0.0"
        assert m.source == "Test"
        assert m.notes == "sample"

    def test_from_dict_none(self):
        m = RegistryMeta.from_dict(None)
        assert m.version is None
        assert m.source is None

    def test_to_dict_drops_none(self):
        m = RegistryMeta.from_dict({"version": "1.0.0", "source": "Test"})
        out = m.to_dict()
        assert out == {"version": "1.0.0", "source": "Test"}
        assert "generated_at" not in out
        assert "notes" not in out


# ----------------------------------------------------------------------
# Cross-language contract fixture
# ----------------------------------------------------------------------

CONTRACT_FIXTURE = (
    Path(__file__).resolve().parents[3] / "tests" / "wrapper_contract.json"
)


@pytest.mark.skipif(
    not CONTRACT_FIXTURE.exists(),
    reason="tests/wrapper_contract.json not yet added (Session 3.5)",
)
class TestContractFixture:
    """Reads the shared fixture and asserts the same answers as the
    other three wrappers. See docs/wrapper_contract.md section 8.2."""

    @pytest.fixture(scope="class")
    def fixture(self):
        return json.loads(CONTRACT_FIXTURE.read_text(encoding="utf-8"))

    @pytest.fixture(scope="class")
    def registry(self, fixture):
        return CorporateActionsRegistry(
            actions_data={"meta": {}, "actions": fixture["actions"]},
        )

    def test_every_query_matches(self, fixture, registry):
        for query in fixture["queries"]:
            result = registry.by_date_range(
                query.get("start"),
                query.get("end"),
                query["date_field"],
            )
            ids = [a.action_id for a in result]
            assert ids == query["expected_action_ids"], (
                f"query {query!r} returned {ids}"
            )

    def test_every_invalid_field_raises(self, fixture, registry):
        for bad in fixture["invalid_date_fields"]:
            with pytest.raises(ValueError, match="invalid date_field"):
                registry.by_date_range(None, None, bad)

    
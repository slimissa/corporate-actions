"""
Tests for tools/build.py.

The build tool produces five artifacts from actions.json:

    actions.dist.json   Pretty-printed, deterministic.
    actions.min.json    Minified, deterministic.
    actions.csv         Flat CSV, one row per action.
    actions.sql         SQLite-compatible dump.
    actions.meta.json   Build metadata (timestamp only).

The first four files must be byte-identical for identical input. The
fifth is the only source of variation.

Run
---
    python -m pytest tests/test_build.py -v
"""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.build import (
    _sql_escape,
    _write_atomic,
    build_csv,
    build_dist,
    build_meta_sidecar,
    build_minified,
    build_sql,
    flatten_action,
    validate_actions_data,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _split_action(**overrides) -> dict:
    action = {
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
            "source": "NVIDIA Corp press release",
            "source_url": "https://example.com/nvda-split",
        },
        "impact": {
            "price_multiplier": 0.1,
            "share_multiplier": 10.0,
            "cash_adjustment": 0.0,
        },
    }
    action.update(overrides)
    return action


def _dividend_action(**overrides) -> dict:
    action = {
        "isin": "US0378331005",
        "action_id": "US0378331005-DIVIDEND-2024-05-23-0.2500",
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
            "source": "Apple Inc. press release",
            "source_url": "https://example.com/aapl-div",
        },
        "impact": {
            "price_multiplier": 1.0,
            "share_multiplier": 1.0,
            "cash_adjustment": 0.25,
        },
    }
    action.update(overrides)
    return action


def _sample_document() -> dict:
    return {
        "meta": {
            "version": "1.0.0",
            "generated_at": "2026-09-18T00:00:00Z",
            "source": "test",
        },
        "actions": [_split_action(), _dividend_action()],
    }


def _read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    return fields, rows


# ---------------------------------------------------------------------------
# flatten_action
# ---------------------------------------------------------------------------

class TestFlattenAction:

    def test_flat_input_unchanged(self):
        assert flatten_action({"a": 1, "b": "x"}) == {"a": 1, "b": "x"}

    def test_nested_dict_is_flattened_one_level(self):
        flat = flatten_action({"dates": {"ex_date": "2024-06-10", "record_date": None}})
        assert flat == {"dates_ex_date": "2024-06-10", "dates_record_date": None}

    def test_full_action_flattens_completely(self):
        flat = flatten_action(_split_action())
        for v in flat.values():
            assert not isinstance(v, (dict, list)), f"unflattened value: {v!r}"
        assert flat["isin"] == "US67066G1040"
        assert flat["action_type"] == "SPLIT"
        assert flat["dates_ex_date"] == "2024-06-10"
        assert flat["provenance_source_url"] == "https://example.com/nvda-split"
        assert flat["impact_share_multiplier"] == 10.0

    def test_all_three_nested_objects_flattened(self):
        flat = flatten_action(_split_action())
        assert "dates_announcement" in flat
        assert "provenance_source" in flat
        assert "impact_price_multiplier" in flat

    def test_rejects_dict_inside_dict(self):
        with pytest.raises(ValueError, match="flatten_action"):
            flatten_action({"dates": {"ex_date": {"nested": "value"}}})

    def test_rejects_nested_dict_inside_dates_and_names_the_path(self):
        with pytest.raises(ValueError, match="dates.bad"):
            flatten_action({"dates": {"bad": {"deep": "value"}}})

    def test_rejects_list_value(self):
        with pytest.raises(ValueError, match="list"):
            flatten_action({"listings": [{"exchange": "XNAS"}]})

    def test_rejects_nested_list_inside_dict(self):
        with pytest.raises(ValueError, match="flatten_action"):
            flatten_action({"dates": {"tags": ["x", "y"]}})

    def test_rejects_empty_list(self):
        with pytest.raises(ValueError, match="list"):
            flatten_action({"tags": []})

    def test_none_values_preserved(self):
        assert flatten_action({"a": None}) == {"a": None}

    def test_bool_values_preserved(self):
        assert flatten_action({"a": True, "b": False}) == {"a": True, "b": False}

    def test_numeric_values_untouched(self):
        flat = flatten_action({"n": 42, "f": 0.25, "z": 0})
        assert flat == {"n": 42, "f": 0.25, "z": 0}

    def test_empty_action_returns_empty_dict(self):
        assert flatten_action({}) == {}


# ---------------------------------------------------------------------------
# validate_actions_data
# ---------------------------------------------------------------------------

class TestValidateActionsData:

    def test_valid_document_produces_no_errors(self):
        assert validate_actions_data(_sample_document()) == []

    def test_top_level_not_a_dict(self):
        assert validate_actions_data([1, 2, 3]) == ["top-level JSON must be an object"]

    def test_top_level_string(self):
        assert validate_actions_data("oops") == ["top-level JSON must be an object"]

    def test_top_level_none(self):
        assert validate_actions_data(None) == ["top-level JSON must be an object"]

    def test_missing_actions_key(self):
        assert validate_actions_data({"meta": {}}) == ["missing 'actions' key"]

    def test_actions_not_a_list(self):
        assert validate_actions_data({"actions": "oops"}) == ["'actions' must be a list"]

    def test_actions_is_dict(self):
        assert validate_actions_data({"actions": {}}) == ["'actions' must be a list"]

    def test_empty_actions_list(self):
        errors = validate_actions_data({"actions": []})
        assert any("empty" in e for e in errors)

    def test_action_missing_required_fields(self):
        doc = {"actions": [{"isin": "US0000000001"}]}
        errors = validate_actions_data(doc)
        assert any("action_id" in e for e in errors)
        assert any("action_type" in e for e in errors)
        assert any("dates" in e for e in errors)

    def test_action_dates_missing_announcement(self):
        doc = {"actions": [{
            "isin": "US0000000001",
            "action_id": "A",
            "action_type": "SPLIT",
            "dates": {"effective_date": "2024-01-01"},
        }]}
        errors = validate_actions_data(doc)
        assert any("announcement" in e for e in errors)

    def test_action_dates_missing_effective_date(self):
        doc = {"actions": [{
            "isin": "US0000000001",
            "action_id": "A",
            "action_type": "SPLIT",
            "dates": {"announcement": "2024-01-01"},
        }]}
        errors = validate_actions_data(doc)
        assert any("effective_date" in e for e in errors)

    def test_dates_is_not_an_object(self):
        doc = {"actions": [{
            "isin": "US0000000001",
            "action_id": "A",
            "action_type": "SPLIT",
            "dates": "2024-01-01",
        }]}
        errors = validate_actions_data(doc)
        assert any("dates" in e and "object" in e for e in errors)

    def test_action_is_not_an_object(self):
        errors = validate_actions_data({"actions": ["not an object"]})
        assert any("index 0" in e for e in errors)

    def test_multiple_bad_actions_all_reported(self):
        doc = {"actions": [
            {"isin": "US0000000001"},
            {"isin": "US0000000002"},
            {"isin": "US0000000003"},
        ]}
        errors = validate_actions_data(doc)
        # Each action is missing action_id, action_type, dates: 9 errors minimum.
        assert len(errors) >= 9

    def test_error_messages_name_the_index(self):
        doc = {"actions": [
            _split_action(),
            {"isin": "US0000000001"},
        ]}
        errors = validate_actions_data(doc)
        assert any("action 1" in e for e in errors)


# ---------------------------------------------------------------------------
# _sql_escape
# ---------------------------------------------------------------------------

class TestSqlEscape:

    def test_none_becomes_null(self):
        assert _sql_escape(None) == "NULL"

    def test_true_becomes_1(self):
        assert _sql_escape(True) == "1"

    def test_false_becomes_0(self):
        assert _sql_escape(False) == "0"

    def test_int_unchanged(self):
        assert _sql_escape(42) == "42"

    def test_zero_unchanged(self):
        assert _sql_escape(0) == "0"

    def test_negative_int_unchanged(self):
        assert _sql_escape(-1) == "-1"

    def test_float_unchanged(self):
        assert _sql_escape(0.25) == "0.25"

    def test_string_wrapped_in_quotes(self):
        assert _sql_escape("USD") == "'USD'"

    def test_single_quote_escaped(self):
        assert _sql_escape("O'Brien") == "'O''Brien'"

    def test_multiple_single_quotes(self):
        assert _sql_escape("a'b'c") == "'a''b''c'"

    def test_only_a_single_quote(self):
        assert _sql_escape("'") == "''''"

    def test_empty_string(self):
        assert _sql_escape("") == "''"

    def test_string_with_double_quotes_unchanged(self):
        assert _sql_escape('say "hi"') == "'say \"hi\"'"

    def test_backslash_not_escaped(self):
        # SQLite does not interpret backslash as an escape; it must pass through.
        assert _sql_escape("a\\b") == "'a\\b'"

    def test_newline_preserved(self):
        assert _sql_escape("a\nb") == "'a\nb'"


# ---------------------------------------------------------------------------
# _write_atomic
# ---------------------------------------------------------------------------

class TestWriteAtomic:

    def test_writes_content(self, tmp_path):
        path = tmp_path / "out.txt"
        _write_atomic(path, "hello")
        assert path.read_text(encoding="utf-8") == "hello"

    def test_creates_file_when_missing(self, tmp_path):
        path = tmp_path / "new.txt"
        assert not path.exists()
        _write_atomic(path, "x")
        assert path.exists()

    def test_overwrites_existing(self, tmp_path):
        path = tmp_path / "out.txt"
        path.write_text("old", encoding="utf-8")
        _write_atomic(path, "new")
        assert path.read_text(encoding="utf-8") == "new"

    def test_no_tmp_file_left_behind(self, tmp_path):
        path = tmp_path / "out.txt"
        _write_atomic(path, "x")
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "out.txt"]
        assert leftovers == [], f"leftover temp files: {leftovers}"

    def test_utf8_content_round_trips(self, tmp_path):
        path = tmp_path / "out.txt"
        payload = "price — dollar\nratios: 10:1, 4:1\n"
        _write_atomic(path, payload)
        assert path.read_text(encoding="utf-8") == payload


# ---------------------------------------------------------------------------
# build_dist / build_minified
# ---------------------------------------------------------------------------

class TestJsonArtifacts:

    def test_dist_is_valid_json(self, tmp_path):
        path = tmp_path / "out.dist.json"
        build_dist(_sample_document(), path)
        json.loads(path.read_text(encoding="utf-8"))

    def test_dist_is_pretty_printed(self, tmp_path):
        path = tmp_path / "out.dist.json"
        build_dist(_sample_document(), path)
        text = path.read_text(encoding="utf-8")
        assert "\n  " in text, "dist output does not appear to be indented"

    def test_dist_ends_with_newline(self, tmp_path):
        path = tmp_path / "out.dist.json"
        build_dist(_sample_document(), path)
        assert path.read_text(encoding="utf-8").endswith("\n")

    def test_dist_preserves_data(self, tmp_path):
        doc = _sample_document()
        path = tmp_path / "out.dist.json"
        build_dist(doc, path)
        round_tripped = json.loads(path.read_text(encoding="utf-8"))
        assert round_tripped["actions"] == doc["actions"]
        assert round_tripped["meta"] == doc["meta"]

    def test_dist_has_no_build_timestamp(self, tmp_path):
        path = tmp_path / "out.dist.json"
        build_dist(_sample_document(), path)
        text = path.read_text(encoding="utf-8")
        assert "build_timestamp" not in text

    def test_min_is_valid_json(self, tmp_path):
        path = tmp_path / "out.min.json"
        build_minified(_sample_document(), path)
        json.loads(path.read_text(encoding="utf-8"))

    def test_min_has_no_extra_whitespace(self, tmp_path):
        path = tmp_path / "out.min.json"
        build_minified(_sample_document(), path)
        text = path.read_text(encoding="utf-8").rstrip("\n")
        # A minified JSON document must not contain ", " between fields
        # nor ": " after keys.
        assert ", " not in text
        assert "\": " not in text
        assert "\n" not in text

    def test_min_preserves_data(self, tmp_path):
        doc = _sample_document()
        path = tmp_path / "out.min.json"
        build_minified(doc, path)
        assert json.loads(path.read_text(encoding="utf-8")) == doc

    def test_min_has_no_build_timestamp(self, tmp_path):
        path = tmp_path / "out.min.json"
        build_minified(_sample_document(), path)
        assert "build_timestamp" not in path.read_text(encoding="utf-8")

    def test_dist_and_min_carry_the_same_data(self, tmp_path):
        doc = _sample_document()
        dist_path = tmp_path / "out.dist.json"
        min_path = tmp_path / "out.min.json"
        build_dist(doc, dist_path)
        build_minified(doc, min_path)
        assert json.loads(dist_path.read_text(encoding="utf-8")) == \
               json.loads(min_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# build_csv
# ---------------------------------------------------------------------------

class TestBuildCsv:

    def test_one_row_per_action(self, tmp_path):
        path = tmp_path / "out.csv"
        build_csv(_sample_document(), path)
        _, rows = _read_csv(path)
        assert len(rows) == 2

    def test_columns_are_the_union_of_all_actions(self, tmp_path):
        path = tmp_path / "out.csv"
        build_csv(_sample_document(), path)
        fields, _ = _read_csv(path)
        # From the split action:
        assert "ratio" in fields
        assert "impact_share_multiplier" in fields
        # From the dividend action:
        assert "amount" in fields
        assert "currency" in fields
        # Both:
        assert "dates_ex_date" in fields
        assert "provenance_source_url" in fields

    def test_columns_are_sorted_alphabetically(self, tmp_path):
        path = tmp_path / "out.csv"
        build_csv(_sample_document(), path)
        fields, _ = _read_csv(path)
        assert fields == sorted(fields)

    def test_regression_column_from_action_11_is_kept(self, tmp_path):
        """The old code looked at the first 10 actions to pick columns,
        and extrasaction='ignore' silently dropped any field that only
        appeared on later actions. This test proves the regression is
        closed."""
        base = [_split_action(action_id=f"A{i}") for i in range(10)]
        late = _split_action(action_id="A-late")
        late["extra_field_only_on_late_action"] = "present"
        data = {"actions": base + [late]}

        path = tmp_path / "out.csv"
        build_csv(data, path)
        fields, rows = _read_csv(path)

        assert "extra_field_only_on_late_action" in fields
        # And the value is present on the correct row:
        late_row = next(r for r in rows if r["action_id"] == "A-late")
        assert late_row["extra_field_only_on_late_action"] == "present"

    def test_values_match_source(self, tmp_path):
        path = tmp_path / "out.csv"
        build_csv(_sample_document(), path)
        _, rows = _read_csv(path)
        split_row = next(
            r for r in rows if r["action_id"].startswith("US67066G1040")
        )
        assert split_row["dates_ex_date"] == "2024-06-10"
        assert split_row["impact_share_multiplier"] == "10.0"
        assert split_row["status"] == "COMPLETED"

    def test_missing_key_renders_as_empty_cell(self, tmp_path):
        """A field present on some actions but not others must produce an
        empty string on rows that lack it, not the literal 'None'."""
        data = {"actions": [_split_action(), _dividend_action()]}
        path = tmp_path / "out.csv"
        build_csv(data, path)
        _, rows = _read_csv(path)
        split_row = next(r for r in rows if r["isin"] == "US67066G1040")
        # Split actions have no currency field.
        assert split_row["currency"] == ""

    def test_null_value_renders_as_empty(self, tmp_path):
        action = _split_action(dates={
            "announcement": "2024-05-22",
            "ex_date": "2024-06-10",
            "record_date": None,
            "effective_date": "2024-06-10",
        })
        path = tmp_path / "out.csv"
        build_csv({"actions": [action]}, path)
        _, rows = _read_csv(path)
        assert rows[0]["dates_record_date"] == ""

    def test_nested_list_raises(self, tmp_path):
        bad = _split_action()
        bad["listings"] = [{"exchange": "XNAS"}]
        with pytest.raises(ValueError, match="list"):
            build_csv({"actions": [bad]}, tmp_path / "out.csv")

    def test_nested_dict_inside_dates_raises(self, tmp_path):
        bad = _split_action()
        bad["dates"]["bad"] = {"deep": "value"}
        with pytest.raises(ValueError, match="dates.bad"):
            build_csv({"actions": [bad]}, tmp_path / "out.csv")

    def test_empty_actions_prints_and_writes_nothing(self, tmp_path, capsys):
        path = tmp_path / "out.csv"
        build_csv({"actions": []}, path)
        assert not path.exists()
        assert "No actions" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# build_sql
# ---------------------------------------------------------------------------

class TestBuildSql:

    def test_one_insert_per_action(self, tmp_path):
        path = tmp_path / "out.sql"
        build_sql(_sample_document(), path)
        inserts = [l for l in path.read_text(encoding="utf-8").splitlines()
                   if l.startswith("INSERT")]
        assert len(inserts) == 2

    def test_sql_has_create_and_transaction(self, tmp_path):
        path = tmp_path / "out.sql"
        build_sql(_sample_document(), path)
        text = path.read_text(encoding="utf-8")
        assert "CREATE TABLE corporate_actions" in text
        assert "BEGIN TRANSACTION" in text
        assert "COMMIT" in text
        assert "DROP TABLE IF EXISTS corporate_actions" in text

    def test_sql_has_primary_key_on_action_id(self, tmp_path):
        path = tmp_path / "out.sql"
        build_sql(_sample_document(), path)
        text = path.read_text(encoding="utf-8")
        assert "action_id TEXT PRIMARY KEY" in text

    def test_sql_escapes_single_quotes_in_strings(self, tmp_path):
        action = _split_action(provenance={
            "source": "O'Brien press release",
            "source_url": "https://example.com",
        })
        path = tmp_path / "out.sql"
        build_sql({"actions": [action]}, path)
        text = path.read_text(encoding="utf-8")
        assert "O''Brien" in text
        # The unescaped version must not appear inside a string literal.
        assert "O'Brien press" not in text

    def test_sql_nulls_for_missing_values(self, tmp_path):
        # A split action has no currency field; the corresponding column
        # must render as NULL, not as the empty string.
        path = tmp_path / "out.sql"
        build_sql({"actions": [_split_action()]}, path)
        text = path.read_text(encoding="utf-8")
        assert "NULL" in text

    def test_sql_ends_with_newline(self, tmp_path):
        path = tmp_path / "out.sql"
        build_sql(_sample_document(), path)
        assert path.read_text(encoding="utf-8").endswith("\n")

    def test_sql_is_valid_sqlite(self, tmp_path):
        """Execute the generated SQL against an in-memory SQLite DB."""
        import sqlite3
        path = tmp_path / "out.sql"
        build_sql(_sample_document(), path)
        sql = path.read_text(encoding="utf-8")
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(sql)
            cur = conn.execute("SELECT COUNT(*) FROM corporate_actions")
            assert cur.fetchone()[0] == 2
        finally:
            conn.close()

    def test_sql_roundtrip_preserves_ids(self, tmp_path):
        import sqlite3
        doc = _sample_document()
        path = tmp_path / "out.sql"
        build_sql(doc, path)
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(path.read_text(encoding="utf-8"))
            cur = conn.execute("SELECT action_id FROM corporate_actions ORDER BY action_id")
            ids = [row[0] for row in cur.fetchall()]
        finally:
            conn.close()
        expected = sorted(a["action_id"] for a in doc["actions"])
        assert ids == expected

    def test_empty_actions_prints_and_writes_nothing(self, tmp_path, capsys):
        path = tmp_path / "out.sql"
        build_sql({"actions": []}, path)
        assert not path.exists()
        assert "No actions" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# build_meta_sidecar
# ---------------------------------------------------------------------------

class TestBuildMetaSidecar:

    def test_creates_file(self, tmp_path):
        path = tmp_path / "out.meta.json"
        build_meta_sidecar(path)
        assert path.exists()

    def test_contains_build_timestamp(self, tmp_path):
        path = tmp_path / "out.meta.json"
        build_meta_sidecar(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "build_timestamp" in data
        assert isinstance(data["build_timestamp"], str)

    def test_timestamp_is_rfc3339_with_z_suffix(self, tmp_path):
        path = tmp_path / "out.meta.json"
        build_meta_sidecar(path)
        ts = json.loads(path.read_text(encoding="utf-8"))["build_timestamp"]
        # Format: YYYY-MM-DDTHH:MM:SSZ
        assert len(ts) == 20
        assert ts[4] == "-"
        assert ts[7] == "-"
        assert ts[10] == "T"
        assert ts[13] == ":"
        assert ts[16] == ":"
        assert ts.endswith("Z")

    def test_timestamp_is_parseable(self, tmp_path):
        from datetime import datetime, timezone
        path = tmp_path / "out.meta.json"
        build_meta_sidecar(path)
        ts = json.loads(path.read_text(encoding="utf-8"))["build_timestamp"]
        datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    def test_no_other_fields(self, tmp_path):
        path = tmp_path / "out.meta.json"
        build_meta_sidecar(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert set(data.keys()) == {"build_timestamp"}

    def test_idempotent_within_the_same_second(self, tmp_path):
        """Two calls in quick succession usually produce the same string
        because the resolution is one second. This is a property, not a
        guarantee, so the test allows a different result if the second
        boundary is crossed."""
        p1 = tmp_path / "a.meta.json"
        p2 = tmp_path / "b.meta.json"
        build_meta_sidecar(p1)
        build_meta_sidecar(p2)
        d1 = json.loads(p1.read_text(encoding="utf-8"))
        d2 = json.loads(p2.read_text(encoding="utf-8"))
        # Both must be valid; if the second ticked over, they differ.
        assert d1["build_timestamp"] <= d2["build_timestamp"]


# ---------------------------------------------------------------------------
# Determinism across artifacts
# ---------------------------------------------------------------------------

class TestDeterminism:
    """The four primary artifacts must be byte-identical across runs on
    the same input. This is the property that makes them safe to check
    into a repository or diff in CI."""

    def test_dist_is_byte_identical(self, tmp_path):
        doc = _sample_document()
        p1 = tmp_path / "a.dist.json"
        p2 = tmp_path / "b.dist.json"
        build_dist(doc, p1)
        build_dist(doc, p2)
        assert p1.read_bytes() == p2.read_bytes()

    def test_min_is_byte_identical(self, tmp_path):
        doc = _sample_document()
        p1 = tmp_path / "a.min.json"
        p2 = tmp_path / "b.min.json"
        build_minified(doc, p1)
        build_minified(doc, p2)
        assert p1.read_bytes() == p2.read_bytes()

    def test_csv_is_byte_identical(self, tmp_path):
        doc = _sample_document()
        p1 = tmp_path / "a.csv"
        p2 = tmp_path / "b.csv"
        build_csv(doc, p1)
        build_csv(doc, p2)
        assert p1.read_bytes() == p2.read_bytes()

    def test_sql_is_byte_identical(self, tmp_path):
        doc = _sample_document()
        p1 = tmp_path / "a.sql"
        p2 = tmp_path / "b.sql"
        build_sql(doc, p1)
        build_sql(doc, p2)
        assert p1.read_bytes() == p2.read_bytes()

    def test_no_timestamp_leaks_into_any_primary_artifact(self, tmp_path):
        doc = _sample_document()
        for build_fn, suffix in [
            (build_dist, ".dist.json"),
            (build_minified, ".min.json"),
            (build_csv, ".csv"),
            (build_sql, ".sql"),
        ]:
            out = tmp_path / f"out{suffix}"
            build_fn(doc, out)
            assert "build_timestamp" not in out.read_text(encoding="utf-8"), (
                f"build_timestamp leaked into {out.name}"
            )


# ---------------------------------------------------------------------------
# End-to-end via subprocess
# ---------------------------------------------------------------------------

def _run_build(actions_path, output_dir, *, cwd=None):
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "build.py"),
         "--actions", str(actions_path),
         "--output-dir", str(output_dir)],
        capture_output=True, text=True, cwd=str(cwd or REPO_ROOT),
    )


def _write_actions_file(tmp_path, doc):
    path = tmp_path / "actions.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


class TestEndToEnd:

    def test_successful_build_produces_five_files(self, tmp_path):
        actions_path = _write_actions_file(tmp_path, _sample_document())
        out_dir = tmp_path / "out"
        result = _run_build(actions_path, out_dir)
        assert result.returncode == 0, result.stdout + result.stderr
        for name in ("actions.dist.json", "actions.min.json",
                     "actions.csv", "actions.sql", "actions.meta.json"):
            assert (out_dir / name).exists(), f"missing {name}"

    def test_default_output_dir_is_next_to_input(self, tmp_path):
        actions_path = _write_actions_file(tmp_path, _sample_document())
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "build.py"),
             "--actions", str(actions_path)],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        for name in ("actions.dist.json", "actions.min.json",
                     "actions.csv", "actions.sql", "actions.meta.json"):
            assert (tmp_path / name).exists(), f"missing {name} in input dir"

    def test_determinism_across_two_full_runs(self, tmp_path):
        doc = _sample_document()
        actions_path = _write_actions_file(tmp_path, doc)
        od1 = tmp_path / "run1"
        od2 = tmp_path / "run2"
        r1 = _run_build(actions_path, od1)
        r2 = _run_build(actions_path, od2)
        assert r1.returncode == 0, r1.stdout + r1.stderr
        assert r2.returncode == 0, r2.stdout + r2.stderr
        for name in ("actions.dist.json", "actions.min.json",
                     "actions.csv", "actions.sql"):
            assert (od1 / name).read_bytes() == (od2 / name).read_bytes(), (
                f"{name} differs between two runs"
            )

    def test_missing_actions_file_exits_2(self, tmp_path):
        result = _run_build(tmp_path / "nope.json", tmp_path / "out")
        assert result.returncode == 2
        assert "not found" in result.stderr.lower()

    def test_invalid_json_exits_2(self, tmp_path):
        path = tmp_path / "actions.json"
        path.write_text("{ not valid json", encoding="utf-8")
        result = _run_build(path, tmp_path / "out")
        assert result.returncode == 2
        assert "invalid JSON" in result.stderr or "invalid json" in result.stderr.lower()

    def test_empty_actions_exits_1(self, tmp_path):
        actions_path = _write_actions_file(tmp_path, {"actions": []})
        result = _run_build(actions_path, tmp_path / "out")
        assert result.returncode == 1
        assert "empty" in result.stderr.lower()

    def test_action_missing_required_field_exits_1(self, tmp_path):
        actions_path = _write_actions_file(tmp_path, {"actions": [{"isin": "US1"}]})
        result = _run_build(actions_path, tmp_path / "out")
        assert result.returncode == 1

    def test_nested_list_in_action_exits_2(self, tmp_path):
        bad = _split_action()
        bad["listings"] = [{"exchange": "XNAS"}]
        actions_path = _write_actions_file(tmp_path, {"actions": [bad]})
        result = _run_build(actions_path, tmp_path / "out")
        assert result.returncode == 2
        assert "flatten" in result.stderr.lower() or "list" in result.stderr.lower()

    def test_creates_output_dir_if_missing(self, tmp_path):
        actions_path = _write_actions_file(tmp_path, _sample_document())
        nested = tmp_path / "a" / "b" / "c"
        assert not nested.exists()
        result = _run_build(actions_path, nested)
        assert result.returncode == 0, result.stdout + result.stderr
        assert nested.is_dir()
        assert (nested / "actions.dist.json").exists()

    def test_real_actions_json_builds_cleanly(self, tmp_path):
        """The committed actions.json must build without error."""
        real = REPO_ROOT / "actions.json"
        out_dir = tmp_path / "out"
        result = _run_build(real, out_dir)
        assert result.returncode == 0, result.stdout + result.stderr
        for name in ("actions.dist.json", "actions.min.json",
                     "actions.csv", "actions.sql", "actions.meta.json"):
            assert (out_dir / name).exists(), f"missing {name}"

    def test_real_actions_csv_matches_action_count(self, tmp_path):
        real = REPO_ROOT / "actions.json"
        out_dir = tmp_path / "out"
        result = _run_build(real, out_dir)
        assert result.returncode == 0, result.stdout + result.stderr

        source = json.loads(real.read_text(encoding="utf-8"))
        _, rows = _read_csv(out_dir / "actions.csv")
        assert len(rows) == len(source["actions"])

    def test_real_actions_sql_loads_into_sqlite(self, tmp_path):
        import sqlite3
        real = REPO_ROOT / "actions.json"
        out_dir = tmp_path / "out"
        result = _run_build(real, out_dir)
        assert result.returncode == 0, result.stdout + result.stderr

        source = json.loads(real.read_text(encoding="utf-8"))
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript((out_dir / "actions.sql").read_text(encoding="utf-8"))
            cur = conn.execute("SELECT COUNT(*) FROM corporate_actions")
            assert cur.fetchone()[0] == len(source["actions"])
        finally:
            conn.close()

    def test_actions_json_with_bom_loads(self, tmp_path):
        """A BOM-prefixed actions.json must load."""
        doc = _sample_document()
        path = tmp_path / "actions.json"
        path.write_bytes(b"\xef\xbb\xbf" + json.dumps(doc).encode("utf-8"))
        result = _run_build(path, tmp_path / "out")
        assert result.returncode == 0, result.stdout + result.stderr

class TestCheckMode:
    """Tests for build.py --check."""

    def _run_check(self, actions_path, output_dir, cwd=None):
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "build.py"),
             "--actions", str(actions_path),
             "--output-dir", str(output_dir),
             "--check"],
            capture_output=True, text=True, cwd=str(cwd or REPO_ROOT),
        )

    def test_check_passes_when_artifacts_match(self, tmp_path):
        actions_path = _write_actions_file(tmp_path, _sample_document())
        out_dir = tmp_path / "out"
        # Build first, then check.
        _run_build(actions_path, out_dir)
        result = self._run_check(actions_path, out_dir)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK: all artifacts match" in result.stdout

    def test_check_fails_when_artifact_is_stale(self, tmp_path):
        actions_path = _write_actions_file(tmp_path, _sample_document())
        out_dir = tmp_path / "out"
        _run_build(actions_path, out_dir)
        # Corrupt one artifact.
        (out_dir / "actions.dist.json").write_text("{}\n", encoding="utf-8")
        result = self._run_check(actions_path, out_dir)
        assert result.returncode == 1
        assert "stale" in result.stderr
        assert "actions.dist.json" in result.stderr

    def test_check_fails_when_artifact_is_missing(self, tmp_path):
        actions_path = _write_actions_file(tmp_path, _sample_document())
        out_dir = tmp_path / "out"
        _run_build(actions_path, out_dir)
        (out_dir / "actions.csv").unlink()
        result = self._run_check(actions_path, out_dir)
        assert result.returncode == 1
        assert "missing" in result.stderr
        assert "actions.csv" in result.stderr


class TestTwoPhaseCommit:
    """A render failure must leave no partial artifacts on disk."""

    def test_flatten_failure_leaves_no_artifacts(self, tmp_path):
        bad = _split_action()
        bad["listings"] = [{"exchange": "XNAS"}]  # list -> render_csv raises
        actions_path = _write_actions_file(
            tmp_path, {"actions": [bad]},
        )
        out_dir = tmp_path / "out"
        result = _run_build(actions_path, out_dir)
        assert result.returncode == 2
        # No file was written, not even the ones that would have
        # rendered successfully first.
        for name in ("actions.dist.json", "actions.min.json",
                     "actions.csv", "actions.sql"):
            assert not (out_dir / name).exists(), (
                f"{name} was written despite render failure"
            )

    def test_no_fetcher_output_in_tree(self):
        """The fetcher must not leave any output files in the repo."""
        tracked = subprocess.check_output(["git", "ls-files"]).decode().splitlines()
        forbidden = {"sec_actions.json", "fetched_actions.json", "yahoo_actions.json"}
        hits = [f for f in tracked if Path(f).name in forbidden]
        assert not hits, f"fetcher output tracked: {hits}"
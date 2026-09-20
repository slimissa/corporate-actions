"""
Full-document schema validation for the Corporate Actions Registry.

Why this file exists
--------------------
`tests/test_schema.py` validates individual entries from the `actions`
array against the action sub-schema. It does not validate the document
as a whole, so it could not catch violations at the top level.

A real example that shipped: `schema.json` declared
`additionalProperties: false` on the `meta` block, but the merge script
wrote an `updated_at` field. `actions.json` therefore did not validate
against its own schema, and no test caught it.

This file closes that gap. It also guards against the schema being
silently weakened in the future: if someone removes a constraint, a
test here fails and forces the change to be deliberate.

The tests do not use network access and do not require any sibling
registry. They read `schema.json` and `actions.json` from the
repository root.

Run
---
    python3 -m pytest tests/test_schema_full.py -v
"""

import copy
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from pydoc import doc

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schema.json"
ACTIONS_PATH = REPO_ROOT / "actions.json"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def schema():
    """The parsed JSON Schema. Loaded once per test session."""
    assert SCHEMA_PATH.is_file(), f"missing {SCHEMA_PATH}"
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def actions():
    """The parsed actions.json. Loaded once per test session."""
    assert ACTIONS_PATH.is_file(), f"missing {ACTIONS_PATH}"
    return json.loads(ACTIONS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def format_checker():
    """Enforce `format: date` and `format: date-time` during validation.

    jsonschema does not enforce `format` unless a `FormatChecker` is
    passed explicitly. Every test that needs real format enforcement
    passes this fixture.
    """
    return jsonschema.FormatChecker()


# ---------------------------------------------------------------------------
# Schema file sanity
# ---------------------------------------------------------------------------

class TestSchemaFile:
    """The schema file is loadable and has the expected shape."""

    def test_schema_file_exists(self):
        assert SCHEMA_PATH.is_file()

    def test_schema_is_a_json_object(self, schema):
        assert isinstance(schema, dict)

    def test_schema_declares_a_draft(self, schema):
        # Any draft is fine; we just need to know which one to validate
        # against. Draft 07 is what the file currently declares.
        assert "$schema" in schema
        assert isinstance(schema["$schema"], str)

    def test_schema_is_itself_valid_against_meta_schema(self, schema):
        """The schema must be a valid Draft 07 schema.

        `check_schema` raises `SchemaError` if the schema is malformed.
        A malformed schema would make every other test in this file
        misleading.
        """
        jsonschema.Draft7Validator.check_schema(schema)

    def test_schema_declares_top_level_type_object(self, schema):
        assert schema.get("type") == "object"

    def test_schema_requires_meta_and_actions(self, schema):
        required = schema.get("required", [])
        assert "meta" in required
        assert "actions" in required

    def test_schema_rejects_unknown_top_level_properties(self, schema):
        # If this ever becomes True, the whole-document test loses its
        # ability to catch stray top-level fields.
        assert schema.get("additionalProperties") is False


# ---------------------------------------------------------------------------
# Schema structure guards
# ---------------------------------------------------------------------------

class TestSchemaStructure:
    """Pin the schema's strictness so it cannot be silently weakened.

    Every one of these assertions is a property that a future
    contributor could reasonably remove while trying to "simplify"
    the schema. Removing one would make a class of typo'd field names
    pass validation silently. Each assertion is guarded by a test so
    the change has to be argued for, not slipped in.
    """

    def test_meta_block_rejects_unknown_properties(self, schema):
        meta = schema["properties"]["meta"]
        assert meta.get("additionalProperties") is False

    def test_actions_items_reject_unknown_properties(self, schema):
        items = schema["properties"]["actions"]["items"]
        assert items.get("additionalProperties") is False

    def test_dates_reject_unknown_properties(self, schema):
        items = schema["properties"]["actions"]["items"]
        dates = items["properties"]["dates"]
        assert dates.get("additionalProperties") is False

    def test_provenance_rejects_unknown_properties(self, schema):
        items = schema["properties"]["actions"]["items"]
        prov = items["properties"]["provenance"]
        assert prov.get("additionalProperties") is False

    def test_actions_items_requires_identity_fields(self, schema):
        items = schema["properties"]["actions"]["items"]
        required = set(items.get("required", []))
        for field in ("isin", "action_id", "action_type", "dates",
                      "status", "provenance"):
            assert field in required, f"schema no longer requires {field!r}"

    def test_action_type_enum_is_complete(self, schema):
        """The enum must match the action types the validator knows.

        If you add a new action type to `ALLOWED_ACTION_TYPES` in
        tools/validate.py, add it here too. If you remove one from
        the schema, this test fails and forces the coordination.
        """
        items = schema["properties"]["actions"]["items"]
        enum = set(items["properties"]["action_type"]["enum"])
        expected = {
            "SPLIT", "REVERSE_SPLIT", "DIVIDEND", "SPECIAL_DIVIDEND",
            "SYMBOL_CHANGE", "SPINOFF", "DELISTING", "MERGER",
        }
        assert enum == expected


# ---------------------------------------------------------------------------
# actions.json sanity
# ---------------------------------------------------------------------------

class TestActionsFile:
    """The data file is loadable and has the expected shape."""

    def test_actions_file_exists(self):
        assert ACTIONS_PATH.is_file()

    def test_actions_file_is_a_json_object(self, actions):
        assert isinstance(actions, dict)

    def test_actions_file_has_meta_and_actions(self, actions):
        assert "meta" in actions
        assert "actions" in actions

    def test_actions_is_a_non_empty_list(self, actions):
        assert isinstance(actions["actions"], list)
        assert len(actions["actions"]) > 0


# ---------------------------------------------------------------------------
# The critical test: the whole document validates against the whole schema
# ---------------------------------------------------------------------------

class TestFullDocumentValidation:
    """The reason this file exists.

    `test_schema.py` validates individual action items. It cannot catch
    violations that live above the item level (unknown fields on `meta`,
    missing top-level keys, wrong meta field types). This class covers
    that gap.
    """

    def test_actions_json_validates_against_schema(
        self, schema, actions, format_checker
    ):
        """The whole actions.json must validate against the whole schema.

        This is the test that would have caught the `updated_at`
        regression: `actions.json` carried a field on `meta` that the
        schema did not allow, and no test noticed.
        """
        try:
            jsonschema.validate(
                instance=actions,
                schema=schema,
                format_checker=format_checker,
            )
        except jsonschema.ValidationError as exc:
            path = "/".join(str(p) for p in exc.absolute_path) or "<root>"
            schema_path = "/".join(str(p) for p in exc.schema_path)
            pytest.fail(
                "actions.json does not validate against schema.json\n"
                f"  instance path: {path}\n"
                f"  schema path:   {schema_path}\n"
                f"  message:       {exc.message}"
            )

    def test_validation_error_names_the_offending_field(
        self, schema, actions, format_checker
    ):
        """Negative control: the schema actually rejects unknown fields.

        This is a meta-test. It proves the validator is doing real
        work on the whole document, not silently accepting anything.
        If the schema stops enforcing `additionalProperties: false` on
        `meta`, this test fails and the whole-document test above loses
        much of its protective value.
        """
        bad = copy.deepcopy(actions)
        bad["meta"]["__not_a_real_field__"] = "boom"

        with pytest.raises(jsonschema.ValidationError) as exc_info:
            jsonschema.validate(bad, schema, format_checker=format_checker)

        message = exc_info.value.message
        assert (
            "__not_a_real_field__" in message
            or "additional" in message.lower()
        ), f"unexpected error message: {message!r}"


# ---------------------------------------------------------------------------
# meta block
# ---------------------------------------------------------------------------

class TestMetaBlock:
    """Focused checks on the meta block of actions.json."""

    def test_meta_is_an_object(self, actions):
        assert isinstance(actions["meta"], dict)

    def test_meta_has_required_fields(self, actions):
        for field in ("version", "generated_at", "source"):
            assert field in actions["meta"], (
                f"meta missing required field: {field}"
            )

    def test_meta_version_is_semver_like(self, actions):
        version = actions["meta"]["version"]
        assert isinstance(version, str)
        parts = version.split(".")
        assert len(parts) == 3, (
            f"version {version!r} is not three dot-separated parts"
        )
        for part in parts:
            assert part.isdigit(), (
                f"version part {part!r} is not numeric"
            )

    def test_meta_generated_at_is_a_valid_datetime(self, actions):
        """Independent parse check, not just jsonschema's format hint.

        If jsonschema's format checker is ever disabled, this test still
        verifies the value is a real date-time.
        """
        value = actions["meta"]["generated_at"]
        assert isinstance(value, str)
        # Python 3.11+ accepts both 'Z' and '+00:00'. Normalize.
        normalized = value.replace("Z", "+00:00")
        datetime.fromisoformat(normalized)

    def test_meta_source_is_a_non_empty_string(self, actions):
        source = actions["meta"]["source"]
        assert isinstance(source, str)
        assert source.strip(), "meta.source must not be empty or whitespace"

    def test_meta_rejects_unknown_field(self, schema, actions, format_checker):
        bad = copy.deepcopy(actions)
        bad["meta"]["bogus"] = "x"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema, format_checker=format_checker)

    def test_meta_rejects_missing_required_field(
        self, schema, actions, format_checker
    ):
        bad = copy.deepcopy(actions)
        del bad["meta"]["version"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema, format_checker=format_checker)

    def test_meta_rejects_wrong_type_for_version(
        self, schema, actions, format_checker
    ):
        bad = copy.deepcopy(actions)
        bad["meta"]["version"] = 100
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema, format_checker=format_checker)


# ---------------------------------------------------------------------------
# Regression: updated_at
# ---------------------------------------------------------------------------

class TestUpdatedAtRegression:
    """The specific bug that motivated this test file.

    Background
    ----------
    `scripts/run_update.sh` writes `meta.updated_at` after a successful
    merge. `schema.json` previously declared `additionalProperties:
    false` on `meta` without listing `updated_at`, so `actions.json`
    did not validate against its own schema. No existing test caught
    this.

    These tests pin the fix in both directions:
      * `updated_at` must be accepted when present.
      * It must be optional, so a freshly generated file validates too.
      * If present, it must be a well-formed date-time.
    """

    def test_updated_at_is_declared_in_schema(self, schema):
        meta_props = schema["properties"]["meta"]["properties"]
        assert "updated_at" in meta_props, (
            "schema.json meta.properties must include updated_at: "
            "scripts/run_update.sh writes it and validation would fail."
        )

    def test_updated_at_is_optional(self, schema):
        required = schema["properties"]["meta"].get("required", [])
        assert "updated_at" not in required, (
            "updated_at must be optional: a freshly regenerated file "
            "may not have it yet, and it should still validate."
        )

    def test_updated_at_declared_as_date_time_string(self, schema):
        spec = schema["properties"]["meta"]["properties"]["updated_at"]
        assert spec.get("type") == "string"
        assert spec.get("format") == "date-time"

    def test_updated_at_in_actions_file_is_valid_if_present(self, actions):
        value = actions["meta"].get("updated_at")
        if value is None:
            pytest.skip(
                "updated_at not present in this revision of actions.json; "
                "the schema permits its absence"
            )
        assert isinstance(value, str)
        normalized = value.replace("Z", "+00:00")
        datetime.fromisoformat(normalized)

    def test_meta_without_updated_at_still_validates(
        self, schema, actions, format_checker
    ):
        """A file that has never been merged must still validate."""
        candidate = copy.deepcopy(actions)
        candidate["meta"].pop("updated_at", None)
        jsonschema.validate(candidate, schema, format_checker=format_checker)

    def test_meta_with_malformed_updated_at_is_rejected(
        self, schema, actions, format_checker
    ):
        """A malformed updated_at must fail, not pass silently."""
        bad = copy.deepcopy(actions)
        bad["meta"]["updated_at"] = "not-a-date"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema, format_checker=format_checker)


# ---------------------------------------------------------------------------
# actions array (whole-array view)
# ---------------------------------------------------------------------------

class TestActionsArray:
    """Whole-array checks that are not item-level concerns."""

    def test_actions_is_a_list(self, actions):
        assert isinstance(actions["actions"], list)

    def test_every_action_is_an_object(self, actions):
        for i, action in enumerate(actions["actions"]):
            assert isinstance(action, dict), (
                f"action at index {i} is not an object"
            )

    def test_every_action_has_required_fields(self, actions):
        required = (
            "isin", "action_id", "action_type", "dates", "status",
            "provenance",
        )
        for i, action in enumerate(actions["actions"]):
            for field in required:
                assert field in action, (
                    f"action {i} ({action.get('action_id', '?')}) "
                    f"missing required field {field!r}"
                )

    def test_every_action_id_is_unique(self, actions):
        counts = Counter(a["action_id"] for a in actions["actions"])
        duplicates = [k for k, c in counts.items() if c > 1]
        assert not duplicates, (
            f"duplicate action_id values: {duplicates[:5]}"
        )

    def test_actions_array_rejects_unknown_field(
        self, schema, actions, format_checker
    ):
        bad = copy.deepcopy(actions)
        bad["actions"][0]["__bogus__"] = 1
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema, format_checker=format_checker)

    def test_empty_actions_array_is_valid(self, schema, actions, format_checker):
        """An empty registry should still validate.

        The schema does not declare `minItems`, so an empty array is
        legal. Coverage of "how many actions is enough" is a separate
        concern handled by tools/validate.py's --min-actions layer,
        not by the schema.
        """
        candidate = copy.deepcopy(actions)
        candidate["actions"] = []
        jsonschema.validate(candidate, schema, format_checker=format_checker)


# ---------------------------------------------------------------------------
# Format enforcement
# ---------------------------------------------------------------------------

class TestFormatEnforcement:
    """Confirm `format: date` and `format: date-time` are enforced.

    jsonschema skips `format` validation unless a `FormatChecker` is
    passed. That is easy to forget, and forgetting it silently loses
    a class of protection. These tests prove the checker works when
    used, so that any code path calling `jsonschema.validate()`
    without one is a visible omission.
    """

    def test_bad_date_is_rejected_with_format_checker(
        self, schema, actions, format_checker
    ):
        bad = copy.deepcopy(actions)
        # The schema declares format: date on dates.announcement.
        bad["actions"][0]["dates"]["announcement"] = "2024-13-99"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema, format_checker=format_checker)

    def test_bad_datetime_is_rejected_with_format_checker(
        self, schema, actions, format_checker
    ):
        bad = copy.deepcopy(actions)
        bad["meta"]["generated_at"] = "not-a-datetime"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema, format_checker=format_checker)

    def test_valid_date_passes_with_format_checker(
        self, schema, actions, format_checker
    ):
        """Positive control: a valid date must not be rejected."""
        candidate = copy.deepcopy(actions)
        candidate["actions"][0]["dates"]["announcement"] = "2024-06-10"
        jsonschema.validate(candidate, schema, format_checker=format_checker)

    def test_full_document_validates():
        doc = json.load(open(REPO_ROOT / 'actions.json'))
        schema = json.load(open(REPO_ROOT / 'schema.json'))
        jsonschema.validate(doc, schema, format_checker=jsonschema.FormatChecker())
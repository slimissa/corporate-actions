# Validation Layers

The Corporate Actions Registry is validated in seven layers. Each layer
catches a distinct class of error. A single action must pass all seven
before it enters `actions.json`. The validator (`tools/validate.py`)
implements every layer and produces a single report listing every failure.

This document specifies:

- What each layer checks
- Why the layer exists
- The exact rules enforced
- How failures are reported
- The exit code semantics
- How to run the validator
- Known gaps and planned additions

---

## Table of contents

1. [Overview](#overview)
2. [Exit codes](#exit-codes)
3. [Layer 1: Schema](#layer-1-schema)
4. [Layer 2: Temporal](#layer-2-temporal)
5. [Layer 3: Arithmetic](#layer-3-arithmetic)
6. [Layer 4: Cross-reference](#layer-4-cross-reference)
7. [Layer 5: Uniqueness](#layer-5-uniqueness)
8. [Layer 6: Provenance](#layer-6-provenance)
9. [Layer 7: Coverage](#layer-7-coverage)
10. [Additional checks](#additional-checks)
11. [Warnings vs errors](#warnings-vs-errors)
12. [Running the validator](#running-the-validator)
13. [Extension guide](#extension-guide)
14. [Version history](#version-history)

---

## Overview

### The seven layers

| # | Layer | Catches | Reference |
|---|-------|---------|-----------|
| 1 | Schema | Structural errors, missing fields, wrong types | `schema.json` |
| 2 | Temporal | Invalid date ordering | `validate_temporal()` |
| 3 | Arithmetic | Invalid ratios, negative amounts | `validate_arithmetic()` |
| 4 | Cross-reference | Unknown ISINs, currencies, MICs | `validate_cross_reference()` |
| 5 | Uniqueness | Duplicate `action_id` | `validate_uniqueness()` |
| 6 | Provenance | Missing or malformed source URLs | `validate_provenance()` |
| 7 | Coverage | Too few actions for the current milestone | `--min-actions` flag |

Each layer is independent. An action that fails layer 2 still gets checked
by layers 3–6, so you see every problem in one pass. This is deliberate:
batch iteration is faster than fixing one error at a time.

### Failure philosophy

Two kinds of problems can arise during validation:

- **Hard errors** — the registry is invalid and cannot be shipped. These
  cause exit code 1.
- **Warnings** — the registry is shippable, but something should be looked
  at. These cause exit code 0 but print to stderr.

The distinction matters. During v1.0.0, missing ISINs are warnings (Asset
Identifiers is being rebuilt with partial coverage). Once full ISIN coverage
lands, the same checks will become errors via `--strict-isin`.

---

## Exit codes

| Code | Meaning | Cause |
|------|---------|-------|
| `0` | All layers passed. Any warnings printed to stderr. | Success |
| `1` | One or more layers failed. Every failure is listed. | Validation errors |
| `2` | Missing `actions.json` or `schema.json`, invalid JSON, bad CLI argument. | Local file problem |
| `3` | External registry could not be loaded (Asset Identifiers, ISO 4217, Exchange Calendar). | Dependency problem |

Exit code `3` is separate from `1` because the fix is different: the
problem is not in `actions.json` but in the surrounding infrastructure.
Scripts that wrap the validator can distinguish "my data is bad" from "the
environment is bad."

---

## Layer 1: Schema

### What it checks

Structural conformance to `schema.json`:

- Top-level object has `meta` and `actions` keys
- `meta` has `version`, `generated_at`, `source`
- `actions` is an array
- Each action has the required fields for its type
- Each field has the correct type
- No unexpected fields are present
- Enum values are in the allowed set

### Why it exists

Schema errors are the most common failure mode during manual data entry.
A typo like `"action_tyep"` instead of `"action_type"` is caught here. A
string `"0.25"` where a number `0.25` is expected is caught here.

Schema validation is enforced by `jsonschema` against `schema.json`. The
validator extracts the action sub-schema (`properties.actions.items`) and
applies it to each action individually. This gives per-action error
messages with field paths.

### Rules

The schema enforces, for every action:

- `isin` matches `^[A-Z]{2}[A-Z0-9]{9}[0-9]$`
- `action_id` is a non-empty string
- `action_type` is one of the eight valid values
- `dates.announcement` and `dates.effective_date` are required
- `dates.ex_date`, `dates.record_date` are optional but must be strings or null
- `status` is one of `COMPLETED`, `PENDING`, `CANCELLED`
- `provenance.source_url` is a required URI
- `impact` fields are numbers if present

Type-specific rules via `oneOf`:

- `SPLIT` / `REVERSE_SPLIT` require `ratio`
- `DIVIDEND` / `SPECIAL_DIVIDEND` require `amount` and `currency`
- `SYMBOL_CHANGE` / `DELISTING` / `SPINOFF` / `MERGER` require no additional fields

The `additionalProperties: false` setting on every object means any field
not in the schema fails. This prevents typo'd field names from silently
being ignored.

### Example failure

```
Action US0378331005-DIVIDEND-2024-05-16-0.2500: Schema error: 'usd' does not match '^[A-Z]{3}$' (path: currency)
```

### Example pass

```json
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
    "effective_date": "2024-05-23"
  },
  "status": "COMPLETED",
  "provenance": {
    "source_url": "https://www.apple.com/newsroom/..."
  }
}
```

---

## Layer 2: Temporal

### What it checks

Date ordering within an action, subject to rules that depend on the action
type. Different corporate events have different valid date sequences. A
dividend has a strict `ex_date < record_date` requirement; a split does not.

### Why it exists

Temporal errors are the second most common failure mode. A common mistake
is copying the record date into the ex-date field, or transposing day and
month. The rules catch these by imposing constraints that reflect how
corporate events actually work.

The layer also catches a subtler class of errors: date sequences that are
technically valid but economically nonsensical. For instance, an
announcement date after the effective date suggests a typo rather than a
real event.

### Rules by action type

```
SPLIT / REVERSE_SPLIT:
  announcement ≤ ex_date
  ex_date = effective_date
  record_date ≤ ex_date (if record_date present)

DIVIDEND / SPECIAL_DIVIDEND:
  announcement ≤ ex_date
  ex_date < record_date (strictly less)
  record_date ≤ effective_date

SYMBOL_CHANGE:
  announcement ≤ effective_date
  (ex_date and record_date ignored even if present)

SPINOFF:
  announcement ≤ ex_date
  ex_date = effective_date
  (record_date ignored)

DELISTING:
  announcement ≤ effective_date
  ex_date must not be present
  record_date must not be present

MERGER:
  announcement ≤ effective_date
  (placeholder; no additional rules)
```

### Date comparison semantics

Dates are compared as ISO `YYYY-MM-DD` strings. Lexicographic comparison
on ISO-formatted dates is equivalent to chronological comparison, so no
date parsing is needed. This avoids timezone and calendar-system bugs.

The validator does not validate that dates are real (e.g. `2024-02-30`).
The schema's `format: date` check catches this at layer 1, provided
`jsonschema` has format validation enabled. If you see a nonsense date
slip through, it is a schema configuration issue, not a temporal issue.

### Example failures

```
Action US0378331005-DIVIDEND-2024-05-16-0.2500: temporal: ex_date (2024-05-17) must be before record_date (2024-05-16)
```

```
Action US67066G1040-SPLIT-2024-06-10-10-1: temporal: ex_date (2024-06-10) must equal effective_date (2024-06-11)
```

```
Action US90184L1026-DELISTING-2022-10-28: temporal: DELISTING should not have ex_date
```

### Example pass

For a standard US dividend:
- `announcement`: 2024-05-02
- `ex_date`: 2024-05-16
- `record_date`: 2024-05-17
- `effective_date`: 2024-05-23

The ordering is `announcement < ex_date < record_date < effective_date`. All
rules pass.

### Why the split rule requires `ex_date = effective_date`

In the US, the split adjusts the price at the open of the ex-date, and that
same date is the effective date. This is the standard NYSE/Nasdaq rule. Some
non-US markets diverge; if such an entry is added, the rule must be relaxed
for that market. This is a known limitation of v1.0.0.

---

## Layer 3: Arithmetic

### What it checks

Numerical consistency within an action:

- `ratio` is well-formed (`"N:M"` with positive integers)
- `amount` is a positive number for dividend types
- Field types are numeric where required

### Why it exists

Manual data entry can introduce:

- Ratio typos (`"10-1"` instead of `"10:1"`)
- Negative amounts
- Zero ratios
- Non-numeric strings in numeric fields

The arithmetic layer catches these before they propagate into backtests.
A `"10-1"` ratio would cause `derive_impacts.py` to produce garbage
multipliers if not caught here.

### Rules

```
SPLIT / REVERSE_SPLIT:
  ratio must be present
  ratio must match regex \d+:\d+
  both parts must be positive integers

DIVIDEND / SPECIAL_DIVIDEND:
  amount must be present
  amount must be numeric (int or float)
  amount must be strictly greater than 0

Other types:
  no arithmetic checks (fields not applicable)
```

### Ratio format

The regex `\d+:\d+` allows only digits, one colon, no whitespace. This is
stricter than the schema's `^\d+:\d+$` only in that the code additionally
checks for positivity.

Valid:
- `"10:1"`
- `"1:8"`
- `"4:1"`

Invalid:
- `"10 : 1"` (spaces)
- `"10-1"` (dash instead of colon)
- `"10/1"` (slash)
- `"0:1"` (zero part)
- `"-1:2"` (negative part)
- `"a:b"` (non-numeric)
- `"10:"` (missing denominator)
- `":1"` (missing numerator)

### Amount rules

- Must be present for dividend types
- Must be numeric (`int` or `float`, not `str`)
- Must be `> 0`

The validator rejects amount as a string. If `"0.25"` appears in a JSON
file with quotes, layer 1 (schema) catches it first. Layer 3 is a
defensive backup.

### Example failures

```
Action US67066G1040-SPLIT-2024-06-10-10-1: arithmetic: Invalid ratio format: 10-1
```

```
Action US0378331005-DIVIDEND-2024-05-16-0.2500: arithmetic: DIVIDEND amount must be positive: -0.25
```

```
Action US0378331005-DIVIDEND-2024-05-16-0.2500: arithmetic: DIVIDEND amount must be a number: lots
```

---

## Layer 4: Cross-reference

### What it checks

External registry consistency:

- `isin` exists in the Asset Identifiers Registry
- `currency` exists in the ISO 4217 active set
- `exchange` (if present) exists in the Exchange Calendar Registry

### Why it exists

Internal consistency is not enough. An `actions.json` can be internally
consistent (schema valid, dates ordered, ratios well-formed) while
referring to an instrument, currency, or exchange that does not exist.

The cross-reference layer catches:

- Typo'd ISINs that accidentally match the ISIN format
- Currency codes that are ISO 4217 but withdrawn (DEM, FRF, ITL)
- Exchange MICs that have been retired or reassigned

### Rules

For each action:

```
if action.isin is present and action.isin not in active_isins:
    → warning (default) or error (with --strict-isin)
if action.currency is present and action.currency not in active_currencies:
    → error
if action.exchange is present and action.exchange not in active_mics:
    → error
```

The `--strict-isin` flag converts missing-ISIN warnings into errors. This
is intended to be enabled once Asset Identifiers ships full ISIN coverage.

### Why ISINs are warnings but currencies are errors

The Asset Identifiers Registry is currently mid-rebuild. Its public release
ships only ~50 ISINs (the private store has more). If missing ISINs were
hard errors, every action for an instrument outside the 50 would fail.

The ISO 4217 registry is stable and complete (167 active currencies). If a
currency code is not in that set, it is a real error.

The Exchange Calendar Registry is stable and complete (74 MICs). Same logic.

Once Asset Identifiers reaches full coverage and `--strict-isin` is the
default, all three checks will be symmetric.

### External registry loading

The validator loads three external registries before running:

| Registry | Loader | Expected structure |
|----------|--------|---------------------|
| Asset Identifiers | `load_identifiers_registry()` | `{"instruments": [{"isin": "..."}]}` |
| ISO 4217 | `load_iso4217_registry()` | `{"currencies": {"active": [{"code": "USD"}]}}` |
| Exchange Calendar | `load_exchange_calendar_registry()` | `{"exchanges": [{"mic": "XNAS"}]}` |

Each loader is tolerant of structural variation, but if it cannot find a
recognizable list, it raises `RegistryLoadError` and the validator exits
with code 3.

### Example failures

```
Action US9999999999-SPLIT-2024-01-01-2-1: cross-reference: ISIN not found in Asset Identifiers registry: US9999999999
```

```
Action US0378331005-DIVIDEND-2024-05-16-0.2500: cross-reference: Currency not an active ISO 4217 code: XYZ
```

```
Action US0378331005-DIVIDEND-2024-05-16-0.2500: cross-reference: Exchange MIC not found in Exchange Calendar registry: XXXX
```

### Example warning

```
Warnings (1):
  - ISIN not found in Asset Identifiers registry: US67066G1040
```

---

## Layer 5: Uniqueness

### What it checks

Every `action_id` in `actions.json` is unique.

### Why it exists

Duplicate `action_id` values indicate either:

- A copy-paste error during manual entry
- A merge bug (the update pipeline added an action that was already there)
- A collision in the auto-generated ID scheme

Duplicates break downstream indexing. Wrappers key their lookup tables by
`action_id`; a duplicate means one entry silently shadows the other.

### Rules

The validator iterates through the actions once, tracking seen IDs in a
set. If an ID appears a second time, an error is added.

```
seen = set()
for action in actions:
    action_id = action.get("action_id")
    if action_id is None:
        continue  # not required at this layer (schema catches it)
    if action_id in seen:
        errors.append(f"Duplicate action_id: {action_id}")
    else:
        seen.add(action_id)
```

Missing or `None` action IDs are ignored at this layer. The schema
requires the field, so a missing ID would already have failed layer 1.

### Why uniqueness is by action_id, not by (isin, date, type)

The registry can legitimately contain two entries for the same
`(isin, action_type, ex_date)` — for example, a regular dividend and a
special dividend on the same day. Those are distinct events with distinct
IDs. The uniqueness check is only about the identifier itself.

Deduplication at the merge step uses a different key
(`isin, action_type, ex_date, ratio, amount`) to detect duplicate events.
See `scripts/run_update.sh`.

### Example failure

```
Duplicate action_id: US0378331005-DIVIDEND-2024-05-16-0.2500
```

---

## Layer 6: Provenance

### What it checks

Every action has a valid source URL.

### Why it exists

Corporate actions are factual claims. If a claim cannot be traced back to a
source, it cannot be verified. The registry's credibility depends on every
entry pointing to a URL a human can check.

### Rules

```
For each action:
  provenance must exist
  provenance.source_url must be present and non-empty
  provenance.source_url must start with "http://" or "https://"
```

Missing URL → error. Non-HTTP scheme (like `ftp://` or `file://`) → error.
Empty string → error.

### Why HTTP(S) only

The provenance URL is intended to be a clickable link in a user interface
and programmatically fetchable by a verification tool. Non-HTTP schemes
break both. They are rejected.

### What is not required

- `provenance.source` (source name) is optional
- `provenance.verification_source` is optional
- `provenance.verification_url` is optional
- The URL does not need to be reachable at validation time

The last point is deliberate: URLs rot. A company press release from 2004
may have moved. Requiring live reachability would fail valid historical
data. The `check-sources.yml` workflow monitors source health separately
from per-action URL validity.

### Example failures

```
Action US0378331005-DIVIDEND-2024-05-16-0.2500: provenance: provenance.source_url is required
```

```
Action US0378331005-DIVIDEND-2024-05-16-0.2500: provenance: source_url must be HTTP(S): ftp://example.com/div
```

### Example pass

```json
"provenance": {
  "source": "Apple Inc. press release",
  "source_url": "https://www.apple.com/newsroom/2024/05/apple-reports-second-quarter-results/",
  "verification_source": "SEC EDGAR 8-K"
}
```

---

## Layer 7: Coverage

### What it checks

The total number of actions in `actions.json` meets a minimum threshold.

### Why it exists

Coverage is a sanity check against accidental truncation. If a merge step
or a fetch step accidentally wipes out half the registry, every other layer
still passes (the remaining entries are valid), and the file ships
truncated. Coverage prevents that.

Coverage also sets a floor for release quality. A "release" with 5 actions
is not a release.

### Rules

```
if total_actions < min_actions:
    errors.append(f"Coverage: only {total_actions} actions found, minimum required is {min_actions}")
```

`min_actions` is resolved in priority order:

1. `--min-actions N` CLI argument
2. `CORP_ACTIONS_MIN_ACTIONS` environment variable
3. Default: `1` (permissive)

For CI, the workflow sets `--min-actions 100` as a regression guard. The
current registry has 242 actions; if a future change drops it below 100,
CI fails.

### Recommended thresholds by context

| Context | Recommended `--min-actions` |
|---------|----------------------------|
| Local development | `1` (default) |
| CI validation | `100` |
| Pre-release tag | Current total minus 5% |
| Post-release sanity | Current total minus 1% |

The "current total minus X%" approach catches sudden drops without hard-coding
a value that becomes stale as the registry grows.

### Example failure

```
Coverage: only 50 actions found, minimum required is 100
```

---

## Additional checks

Beyond the seven layers, the validator enforces two specific policies:

### MERGER rejection in v1.0.0

`MERGER` is a valid schema type but is not accepted in v1.0.0. Any action
with `action_type == "MERGER"` fails validation with:

```
Action <action_id>: MERGER is not allowed in v1.0.0
```

This is deliberate. The schema reserves the type so future entries will not
require a schema change. The validator enforces that no such entries exist
until the extraction pipeline supports them.

See `docs/action_types.md#merger` for the full rationale.

### Deprecation notice for `--strict-isin`

The `--strict-isin` flag is not itself a check, but it changes layer 4
behavior. When enabled, missing ISINs are errors rather than warnings. This
is documented in [Warnings vs errors](#warnings-vs-errors).

---

## Warnings vs errors

### What produces a warning

Only one thing: a missing ISIN in the Asset Identifiers Registry, when
`--strict-isin` is not set.

### Why this distinction

Asset Identifiers is being rebuilt. During the interim, the registry is
validated against the subset of ISINs that are publicly available. Warnings
surface the gap without blocking the release.

The distinction is temporary. Once the Asset Identifiers rebuild is complete
and `--strict-isin` is the default, this section will be revised to reflect
that all cross-reference checks are symmetric.

### How warnings are reported

Warnings are printed to stdout after the validation runs:

```
Warnings (3):
  - ISIN not found in Asset Identifiers registry: US67066G1040
  - ISIN not found in Asset Identifiers registry: US5949181045
  - ISIN not found in Asset Identifiers registry: US0378331005
```

They do not affect the exit code. A validation that produces warnings and
no errors exits `0`.

### How errors are reported

Errors are printed to stdout at the end of the run:

```
Validation FAILED with the following errors:
  - Action US0378331005-DIVIDEND-2024-05-16-0.2500: schema error: 'usd' does not match '^[A-Z]{3}$'
  - Action US67066G1040-SPLIT-2024-06-10-10-1: temporal: ex_date must equal effective_date
  - Duplicate action_id: US0378331005-DIVIDEND-2024-05-16-0.2500
```

Exit code is `1`.

### Suppressing warnings

There is no flag to suppress warnings. They are cheap to print and cheap to
read. If a warning is noise, the correct fix is to fix the underlying issue
(add the ISIN to the Asset Identifiers subset, or update the check policy).

---

## Running the validator

### Basic invocation

```bash
python3 tools/validate.py \
  --actions actions.json \
  --schema schema.json \
  --identifiers tests/fixtures/identifiers.json \
  --iso4217 tests/fixtures/iso4217.json \
  --exchange-calendar tests/fixtures/exchange_calendar.json
```

### With strict ISIN

```bash
python3 tools/validate.py \
  --actions actions.json \
  --schema schema.json \
  --identifiers tests/fixtures/identifiers.json \
  --iso4217 tests/fixtures/iso4217.json \
  --exchange-calendar tests/fixtures/exchange_calendar.json \
  --strict-isin
```

### With a coverage floor

```bash
python3 tools/validate.py \
  --actions actions.json \
  --schema schema.json \
  --identifiers tests/fixtures/identifiers.json \
  --iso4217 tests/fixtures/iso4217.json \
  --exchange-calendar tests/fixtures/exchange_calendar.json \
  --min-actions 100
```

### Environment variables

| Variable | Purpose |
|----------|---------|
| `CORP_ACTIONS_ACTIONS_PATH` | Override `--actions` |
| `CORP_ACTIONS_SCHEMA_PATH` | Override `--schema` |
| `CORP_ACTIONS_IDENTIFIERS_PATH` | Override `--identifiers` |
| `CORP_ACTIONS_ISO4217_PATH` | Override `--iso4217` |
| `CORP_ACTIONS_EXCHANGE_CALENDAR_PATH` | Override `--exchange-calendar` |
| `CORP_ACTIONS_MIN_ACTIONS` | Override `--min-actions` |
| `LAS_DATA_HOME` | Fallback location for Asset Identifiers `identifiers.json` |

### Resolution order

CLI arguments > environment variables > default paths.

Default paths:

- Asset Identifiers: `$LAS_DATA_HOME/identifiers.json` if set, else `../asset-identifiers/identifiers.json`
- ISO 4217: `../iso4217/iso4217.json`
- Exchange Calendar: `../exchange-calendar/calendar.json`

### Example output

Success:

```
Loading Asset Identifiers registry...
  Loaded 294 ISINs
Loading ISO 4217 registry...
  Loaded 167 active currencies
Loading Exchange Calendar registry...
  Loaded 74 exchange MICs

Validating 242 actions...

OK: 242 actions validated successfully.
Cross-reference: 242 ISINs validated, 0 missing (warnings)
All layers passed: schema, temporal, arithmetic, cross-reference, uniqueness, provenance, coverage
```

Failure:

```
Loading Asset Identifiers registry...
  Loaded 294 ISINs
Loading ISO 4217 registry...
  Loaded 167 active currencies
Loading Exchange Calendar registry...
  Loaded 74 exchange MICs

Validating 242 actions...

Validation FAILED with the following errors:
  - Action US0378331005-DIVIDEND-2024-05-16-0.2500: arithmetic: DIVIDEND amount must be positive: -0.25
  - Duplicate action_id: US67066G1040-SPLIT-2024-06-10-10-1
```

---

## Extension guide

### Adding a new layer

The validator is a linear pipeline. To add a new layer:

1. **Write the check as a function.** Signature:

   ```python
   def validate_my_layer(action: Dict[str, Any]) -> List[str]:
       errors = []
       # ... check the action ...
       return errors
   ```

   For cross-action checks (like uniqueness), the signature takes the full
   actions list:

   ```python
   def validate_my_layer(actions: List[Dict[str, Any]]) -> List[str]:
       ...
   ```

2. **Call it in `main()`.** Add the call inside the action loop or after
   the loop, depending on whether the check is per-action or cross-action.

3. **Prefix the error message.** All per-action errors use the format
   `Action <action_id>: <layer>: <message>`. Cross-action errors use their
   own prefix.

4. **Add tests.** Add cases to `tests/test_<layer>.py`.

5. **Document it.** Update this file.

### Adding a rule to an existing layer

Each layer has a dedicated function. Add the rule to the function body.
Follow the pattern of the existing rules:

```python
if <condition that indicates a problem>:
    errors.append(f"<clear description of the problem>")
```

Error messages should name the field, the invalid value, and what was
expected. A user reading the message should know exactly what to fix.

### Adding a new cross-reference registry

Cross-references follow a pattern:

1. **Write a loader** in `tools/validate.py`:

   ```python
   def load_my_registry(path: str) -> Set[str]:
       data = load_json_file(path)
       # extract the set of valid keys
       return valid_keys
   ```

2. **Add a CLI flag** for the registry path.

3. **Add an environment variable** override.

4. **Add the set to the cross-reference call**.

5. **Update `docs/data_sources.md`** with the new registry.

### Testing changes

Run the full suite after any validator change:

```bash
pytest tests/ -v
```

Then run the validator against the production file to check for false
positives:

```bash
python3 tools/validate.py \
  --actions actions.json \
  --schema schema.json \
  --identifiers tests/fixtures/identifiers.json \
  --iso4217 tests/fixtures/iso4217.json \
  --exchange-calendar tests/fixtures/exchange_calendar.json
```

If the change causes a previously-passing validation to fail, either the
change is wrong or the data is wrong. Investigate before committing.

---

## Version history

### v1.0.0

- All seven layers implemented
- `--strict-isin` flag added (default: missing ISIN is a warning)
- `--min-actions` for coverage floor
- MERGER rejected explicitly
- Warnings vs errors distinction documented

### v1.1.0 (planned)

- `--strict-isin` becomes the default once Asset Identifiers reaches full
  coverage
- New layer: currency conversion validation (check that dividend currency
  matches instrument currency, or that a documented conversion exists)
- New layer: `impact` consistency (re-derive multipliers and compare
  against the stored values)

### v1.2.0 (planned)

- Cross-action temporal validation (e.g. no two splits within 1 day)
- Reference data checks (validate that the ISIN's country code matches the
  provenance source's jurisdiction)

---

## See also

- `docs/action_types.md` — semantics of each action type
- `docs/data_sources.md` — where data comes from
- `docs/roadmap.md` — long-term plan
- `tools/validate.py` — the implementation
- `schema.json` — the schema that layer 1 enforces
- `tests/` — the test suite for each layer
- `.github/workflows/validate.yml` — CI runs the validator on every push
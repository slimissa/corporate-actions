# Wrapper Contract

The Corporate Actions Registry ships four language wrappers: Python,
JavaScript, Go, and Rust. Each wraps the same JSON document with
idiomatic code for its language. This document freezes the interface
they all implement, so that a change to one wrapper can be verified
against a written contract rather than against the other three.

This file is the source of truth for wrapper behaviour. When a wrapper
disagrees with this document, the wrapper is wrong. When this document
disagrees with the tests, the tests win and this document is updated.

**Revision note (v2, Phase 5).** This revision adds `by_ticker`, makes
duplicate `action_id` and missing identifiers load-time errors, and
introduces the exported constants. The previous revision had `by_ticker`
in "out of scope"; it is now a required method. Section numbers are
stable since v1 except where marked `(new)`.

---

## Table of contents

1. [Purpose](#1-purpose)
2. [Scope](#2-scope)
3. [Cross-language name map](#3-cross-language-name-map)
4. [Method contracts](#4-method-contracts)
   - [4.1 `by_isin`](#41-by_isin)
   - [4.2 `by_action_id`](#42-by_action_id)
   - [4.3 `by_action_type`](#43-by_action_type)
   - [4.4 `by_date_range`](#44-by_date_range)
   - [4.5 `all_action_types`](#45-all_action_types)
   - [4.6 `count`](#46-count)
   - [4.7 Serialization](#47-serialization)
   - [4.8 `by_ticker` (new)](#48-by_ticker-new)
   - [4.9 Exported constants (new)](#49-exported-constants-new)
5. [Loading behaviour](#5-loading-behaviour)
   - [5.1 UTF-8 BOM](#51-utf-8-bom)
   - [5.2 Missing `actions` key](#52-missing-actions-key)
   - [5.3 Empty `actions` list](#53-empty-actions-list)
   - [5.4 Action items that are not objects](#54-action-items-that-are-not-objects)
   - [5.5 Duplicate `action_id` (new)](#55-duplicate-action_id-new)
   - [5.6 Missing identifier fields (new)](#56-missing-identifier-fields-new)
6. [Error types](#6-error-types)
7. [Example CLIs](#7-example-clis)
8. [Testing](#8-testing)
9. [Change process](#9-change-process)
10. [Appendix — full signature reference](#10-appendix--full-signature-reference)

---

## 1. Purpose

Three properties are worth guaranteeing across the four wrappers:

- **Same inputs, same outputs.** A caller who moves from Python to Go
  to Rust should not have to relearn `by_date_range`. The method name
  changes, the semantics do not.
- **Nothing silent.** A typo'd field name raises. A missing key is an
  error. A malformed file is an error. A duplicate identifier is an
  error. The wrapper never returns an empty list because the caller
  mistyped a string, and it never silently accepts data the validator
  would reject.
- **No side effects on return.** A caller who mutates a returned list
  or object does not corrupt the wrapper's internal state. The next
  call returns the same answer as the first.

Where a language cannot express one of these directly — for example, Go
returning `([]Action, error)` rather than raising — the language's
idiom is used, and the difference is documented here.

## 2. Scope

### In scope

- Load semantics
- Lookup methods: `by_isin`, `by_action_id`, `by_action_type`,
  `by_date_range`, `by_ticker`, `all_action_types`, `count`
- Serialization: `to_dict` / `toJSON` / `ToJSON` / `to_json` and `save`
- Exported constants: `DEFAULT_DATE_FIELD`, `VALID_DATE_FIELDS`
- Error types and messages
- Example CLI flag parsing and exit codes
- Test conventions shared across wrappers

### Out of scope

- **Cross-language consistency tests beyond the shared fixture.**
  Broader comparison is a later phase.
- **Wrapper publishing to package registries.**
- **Internal representation.** How a wrapper stores its index is its
  own business, so long as the public behaviour matches.
- **Ticker lists, exchange lists, and instrument metadata.** Those
  belong to the Asset Identifiers registry. The wrapper reads them, it
  does not own them.

## 3. Cross-language name map

Each wrapper follows its language's naming convention. The mapping is
fixed and does not change between versions.

| Concept | Python | JavaScript | Go | Rust |
|---------|--------|------------|-----|------|
| Class / type | `CorporateActionsRegistry` | `CorporateActionsRegistry` | `Registry` | `Registry` |
| Lookup by ISIN | `by_isin` | `byIsin` | `ByISIN` | `by_isin` |
| Lookup by action ID | `by_action_id` | `byActionId` | `ByActionID` | `by_action_id` |
| Lookup by action type | `by_action_type` | `byActionType` | `ByActionType` | `by_action_type` |
| Date-range filter | `by_date_range` | `byDateRange` | `ByDateRange` | `by_date_range` |
| Lookup by ticker | `by_ticker` | `byTicker` | `ByTicker` | `by_ticker` |
| List of action types | `all_action_types` | `allActionTypes` | `AllActionTypes` | `all_action_types` |
| Action count | `count` | `count` | `Count` | `count` |
| Serialize | `to_dict` | `toJSON` | `ToJSON` | `to_json` |
| Write to disk | `save` | `save` | `Save` | `save` |
| Load from a file path | `CorporateActionsRegistry(path)` | `new CorporateActionsRegistry(path)` | `LoadRegistry(path)` | `Registry::load_from_file(path)` |
| Load from parsed data | `CorporateActionsRegistry(actions_data=...)` | `new CorporateActionsRegistry(object)` | `FromJSON([]byte)` | `Registry::from_value(Value)` |
| Default date field constant | `DEFAULT_DATE_FIELD` | `DEFAULT_DATE_FIELD` | `DefaultDateField` | `DEFAULT_DATE_FIELD` |
| Valid date fields constant | `VALID_DATE_FIELDS` | `VALID_DATE_FIELDS` | `ValidDateFields` | `VALID_DATE_FIELDS` |

Two naming choices are deliberate and are not bugs:

- Go uses `ISIN` (all caps) because it is an initialism; Go convention
  is to capitalise initialisms.
- Rust uses `by_isin` rather than `by_ISIN` because Rust identifiers
  are snake_case and do not preserve initialism capitalisation.

## 4. Method contracts

Each method is specified once. Language-specific differences are noted
inside the method's subsection.

Throughout this section:

- **`Action`** means the parsed representation of one corporate action.
  Python returns `Action` objects, JavaScript returns plain objects, Go
  returns `Action` structs, Rust returns `Action` structs.
- **"Fresh list"** means a list whose mutation does not affect the
  registry's internal state. Python achieves this with `copy.deepcopy`
  or `list(...)`, JavaScript with `structuredClone`, Go with
  `deepCopyAction`, and Rust with `Vec` by value.
- **"Deep copy"** means an object whose nested dicts and lists are also
  independent of the registry's internal state. Only `by_action_id`
  returns a single object, and only that method needs a deep copy.

### 4.1 `by_isin`

```
Python:     by_isin(isin: str) -> List[Action]
JavaScript: byIsin(isin: string) -> Action[]
Go:         ByISIN(isin string) []Action
Rust:       by_isin(&self, isin: &str) -> Vec<Action>
```

Returns every action whose `isin` field equals `isin`. Returns an empty
list when no action matches. Never raises for an unknown ISIN.

The returned list is **fresh**: the caller may sort, reverse, or mutate
it without affecting the registry.

Matching is exact and case-sensitive. ISINs are uppercase by standard;
`by_isin("us0378331005")` returns an empty list, not the Apple
dividends.

### 4.2 `by_action_id`

```
Python:     by_action_id(action_id: str) -> Optional[Action]
JavaScript: byActionId(actionId: string) -> Action | null
Go:         ByActionID(actionID string) *Action
Rust:       by_action_id(&self, action_id: &str) -> Option<Action>
```

Returns the single action whose `action_id` equals `action_id`, or the
language's "no value" sentinel (`None`, `null`, `nil`, `None`) when no
action matches.

The returned object is a **deep copy** in Python, JavaScript, and Rust.
In Go, the returned pointer refers to a fresh copy allocated by the
method; mutating the pointed-to struct does not affect the registry's
internal slice.

Matching is exact and case-sensitive.

Duplicate `action_id` values are a load-time error (see § 5.5). The
loader raises before returning a registry instance, so `by_action_id`
can rely on each ID appearing at most once.

### 4.3 `by_action_type`

```
Python:     by_action_type(action_type: str) -> List[Action]
JavaScript: byActionType(actionType: string) -> Action[]
Go:         ByActionType(actionType string) []Action
Rust:       by_action_type(&self, action_type: &str) -> Vec<Action>
```

Returns every action whose `action_type` equals `action_type`. Returns
an empty list when no action matches.

The returned list is **fresh**, as with `by_isin`.

Matching is exact and case-sensitive. `by_action_type("split")` returns
nothing; the standard form is `"SPLIT"`.

### 4.4 `by_date_range`

This is the only method whose signature and error semantics differ
across languages.

```
Python:     by_date_range(start_date: Optional[str] = None,
                          end_date: Optional[str] = None,
                          date_field: str = "ex_date") -> List[Action]

JavaScript: byDateRange(startDate: Optional<string>,
                        endDate: Optional<string>,
                        dateField: string = 'ex_date') -> Action[]

Go:         ByDateRange(startDate, endDate, dateField string)
                          ([]Action, error)

Rust:       by_date_range(&self,
                          start_date: Option<&str>,
                          end_date: Option<&str>,
                          date_field: &str)
                          -> Result<Vec<Action>, RegistryError>
```

**Valid `date_field` values** — exactly these four, no others:

- `"announcement"`
- `"ex_date"`
- `"record_date"`
- `"effective_date"`

The four values are exported as `VALID_DATE_FIELDS` / `ValidDateFields`
(see § 4.9). Callers who want to enumerate them should import the
constant rather than duplicating the list.

**Default value.** Python and JavaScript default to `"ex_date"` when
the argument is omitted. Go and Rust require the argument; callers
should use the exported `DEFAULT_DATE_FIELD` / `DefaultDateField`
constant. The default value is a language-idiomatic concession, not a
semantic difference: all four wrappers treat an explicit `"ex_date"` and
an omitted argument identically.

**Behaviour, in order:**

1. **Validate the field name.** If `date_field` is not one of the four
   values above, raise or return an error naming the offending value
   and listing the valid ones.
   - Python raises `ValueError`
   - JavaScript throws `Error`
   - Go returns `ErrInvalidDateField` (wrapped)
   - Rust returns `RegistryError::InvalidDateField`
2. **Filter actions.** Include an action when its value for `date_field`
   is non-null and satisfies `start_date <= value <= end_date`. Both
   bounds are inclusive. A `None`, `null`, `""`, or `nil` bound means
   "no bound on that side." An empty-string bound is not a bound of
   zero; it is equivalent to `None` in every wrapper.
3. **Skip actions that lack the field.** An action whose `dates` object
   is missing, or whose `date_field` is `null`, is silently skipped.
   This is not an error: `SYMBOL_CHANGE` and `DELISTING` actions have
   no `ex_date`, and asking for `ex_date` legitimately excludes them.
4. **Sort the result** by `(date_field_value, action_id)`, ascending,
   using string comparison on ISO-8601 dates and action IDs. Two
   actions with the same date are ordered by `action_id`.
5. **Return a fresh list.** Mutation of the returned list must not
   affect the registry.

**Worked example.** Given three actions:

```
A1: ex_date=2024-03-01, effective_date=2024-03-01
A2: ex_date=2024-01-01, effective_date=2024-01-01
A3: ex_date=2024-02-01, effective_date=2024-02-15
```

`by_date_range("2024-01-01", "2024-12-31", "ex_date")` returns
`[A2, A3, A1]` — sorted by ex_date, not by file order.

`by_date_range("2024-02-01", "2024-03-01", "effective_date")` returns
`[A3, A1]` — A3 has `effective_date=2024-02-15`, A1 has
`effective_date=2024-03-01`, A2 is excluded because its
`effective_date=2024-01-01` is before the start bound.

`by_date_range(None, "2024-02-01", "ex_date")` returns `[A2, A3]` —
the start bound is open.

`by_date_range("", "", "ex_date")` returns the same result as
`by_date_range(None, None, "ex_date")` — empty-string bounds mean no
bound.

`by_date_range(None, None, "exdate")` raises or returns an error,
because `"exdate"` is not a valid field name.

### 4.5 `all_action_types`

```
Python:     all_action_types() -> List[str]
JavaScript: allActionTypes() -> string[]
Go:         AllActionTypes() []string
Rust:       all_action_types() -> Vec<String>
```

Returns the set of distinct `action_type` values present in the loaded
registry, **sorted alphabetically**. Returns an empty list for an empty
registry.

The result reflects only the types that actually appear in the data. It
does not include reserved types that are valid per the schema but
absent from `actions.json`. A registry with only SPLIT and DIVIDEND
actions returns `["DIVIDEND", "SPLIT"]`, not all eight schema types.

### 4.6 `count`

```
Python:     count() -> int
JavaScript: count() -> number
Go:         Count() int
Rust:       count() -> usize
```

Returns the number of actions in the loaded registry.

### 4.7 Serialization

```
Python:     to_dict() -> Dict[str, Any]
            save(path: str) -> None

JavaScript: toJSON() -> { meta, actions }
            save(filePath: string) -> void

Go:         ToJSON() ([]byte, error)
            Save(path: string) -> error

Rust:       to_json() -> serde_json::Value
            save<P: AsRef<Path>>(path: P) -> Result<(), RegistryError>
```

**`to_dict` / `toJSON` / `ToJSON` / `to_json`** return a serializable
representation with exactly two top-level keys: `"meta"` and
`"actions"`. No wrapper adds fields, renames fields, or changes nesting.

**`save`** writes the same representation to a file. The output is
valid UTF-8 JSON. No specific formatting is required by the contract;
each wrapper uses its language's conventional indentation (2 spaces in
Python and JavaScript, 2 spaces in Go, 2 spaces in Rust). Trailing
newline is optional.

### 4.8 `by_ticker` (new)

```
Python:     by_ticker(ticker: str,
                      exchange: str,
                      identifiers_path: Optional[str] = None)
                      -> List[Action]

JavaScript: byTicker(ticker: string,
                     exchange: string,
                     identifiersPath: Optional<string> = null)
                     -> Action[]

Go:         ByTicker(ticker, exchange, identifiersPath string)
                      ([]Action, error)

Rust:       by_ticker(&self,
                      ticker: &str,
                      exchange: &str,
                      identifiers_path: Option<&str>)
                      -> Result<Vec<Action>, RegistryError>
```

Resolves `(ticker, exchange)` to an ISIN using the Asset Identifiers
registry, then returns the same list as `by_isin(isin)`.

**Why this exists.** Before this method, consumers who wanted "all
actions for AAPL on NASDAQ" had to know the ISIN, or scan the
`provenance.source_url` of every action for the ticker string. The
second approach produced false positives at scale — tickers that appear
as substrings of other strings, tickers that appear in unrelated URLs,
and multi-class instruments like `GOOG` vs `GOOGL`. The
`(ticker, exchange)` pair is unique, and the Asset Identifiers registry
already indexes it.

**Path resolution.** When `identifiers_path` is `None` / `null` / `""`,
the wrapper tries, in order:

1. `$CORP_ACTIONS_IDENTIFIERS_PATH`
2. `$LAS_DATA_HOME/identifiers.json`

If none is set and the file does not exist, the wrapper raises or
returns a `MissingData` error (see § 6). The message names the two
environment variables that would fix it.

The path is resolved once per process and the parsed index is cached.
A caller who wants to force a reload can pass an explicit
`identifiers_path` different from the cached one, or, in tests, use the
language-specific cache-reset helper (see § 8.3).

**Ticker and exchange are uppercased before lookup.** `by_ticker
("aapl", "xnas")` resolves identically to `by_ticker("AAPL", "XNAS")`.
This matches user expectation: tickers are case-insensitive in every
financial context.

**Unknown ticker.** A `(ticker, exchange)` pair not present in the
index returns an empty list, not an error. This matches `by_isin`
behaviour for an unknown ISIN. "Not in the data" and "data unavailable"
are different answers, and this method only returns the first kind.

**No `by_ticker` without a registry.** If the identifiers file is
missing, `by_ticker` errors rather than returning an empty list. A
caller who wants "not in the data" should ensure the identifiers file
exists; a caller who passes no `identifiers_path` and sets neither
environment variable gets an error naming the missing configuration.

**Worked example.** Given `tests/fixtures/identifiers.json` with the
following entries:

```json
{ "ticker": "AAPL", "exchange": "XNAS", "isin": "US0378331005" }
{ "ticker": "PRU",  "exchange": "XNYS", "isin": "US7443201022" }
{ "ticker": "PRU",  "exchange": "XLON", "isin": "GB0007099541" }
```

`by_ticker("AAPL", "XNAS")` returns the same list as
`by_isin("US0378331005")`.

`by_ticker("PRU", "XNYS")` returns the Prudential Financial actions,
not the Prudential plc actions. The exchange disambiguates.

`by_ticker("PRU", "XLON")` returns the Prudential plc actions.

`by_ticker("aapl", "xnas")` returns the same list as
`by_ticker("AAPL", "XNAS")`.

`by_ticker("NOTREAL", "XNAS")` returns an empty list.

`by_ticker("AAPL", "NOTEXCH")` returns an empty list.

**Errors.**

- `MissingData` when no identifiers file is resolvable.
- The same errors as `by_isin` when the resolved ISIN is passed through.

### 4.9 Exported constants (new)

Every wrapper exports two constants at module scope:

| Constant | Value |
|----------|-------|
| `DEFAULT_DATE_FIELD` | `"ex_date"` |
| `VALID_DATE_FIELDS` | `("announcement", "ex_date", "record_date", "effective_date")` |

Language-specific names:

| Concept | Python | JavaScript | Go | Rust |
|---------|--------|------------|-----|------|
| Default date field | `DEFAULT_DATE_FIELD` | `DEFAULT_DATE_FIELD` | `DefaultDateField` | `DEFAULT_DATE_FIELD` |
| Valid date fields | `VALID_DATE_FIELDS` | `VALID_DATE_FIELDS` | `ValidDateFields` | `VALID_DATE_FIELDS` |

**`DEFAULT_DATE_FIELD`** is the value Python and JavaScript use when
the `date_field` argument to `by_date_range` is omitted. Go and Rust
require the argument and export the constant so callers do not
hard-code the string.

**`VALID_DATE_FIELDS`** is the closed set every wrapper accepts. A
caller who wants to enumerate the choices imports it rather than
duplicating the list. The order of the constant is fixed: announcement,
ex_date, record_date, effective_date. Callers should not depend on this
order for display purposes; sort if presentation order matters.

Both constants are part of the public API. A wrapper that does not
export them is non-conformant.

## 5. Loading behaviour

### 5.1 UTF-8 BOM

A JSON file saved through a Windows editor often begins with a UTF-8
byte-order mark (`\xEF\xBB\xBF`). The contract requires every wrapper
to accept such a file and load it identically to a file without a BOM.

- **Python** — open with `encoding="utf-8-sig"`.
- **JavaScript** — read as UTF-8, strip a leading `\uFEFF` before
  `JSON.parse`.
- **Go** — `bytes.TrimPrefix(data, []byte{0xEF, 0xBB, 0xBF})` before
  `json.Unmarshal`.
- **Rust** — `content.strip_prefix('\u{FEFF}')` before
  `serde_json::from_str`.

A file with a BOM is not malformed. It is a valid UTF-8 text file whose
first codepoint is the BOM.

### 5.2 Missing `actions` key

A document that is not an object, or that lacks an `actions` key, is a
structural error. The wrapper does not silently construct an empty
registry.

- **Python** — raise `ValueError`
- **JavaScript** — throw `Error`
- **Go** — return an `error`
- **Rust** — return `RegistryError::InvalidStructure`

The message names the missing key when possible. Examples:

```
Python:     ValueError("Invalid actions data: expected dict with 'actions' key.")
JavaScript: Error("Invalid actions data: expected object with \"actions\" array.")
Go:         parsing registry JSON: missing 'actions' key
Rust:       invalid registry structure: missing 'actions' key
```

### 5.3 Empty `actions` list

A document with `"actions": []` is valid. The registry loads with
`count() == 0`. All lookups return empty results. This is the state of
a freshly reset registry and is not an error.

### 5.4 Action items that are not objects

An entry in the `actions` array that is not a JSON object is a
structural error. The wrapper does not skip it silently.

The `actions` key must be an array; a scalar, string, or object is an
error.

Error message names the index:

```
Python:     ValueError("Invalid actions data: action at index 7 is not an object.")
JavaScript: Error("Invalid actions data: action at index 7 is not an object.")
Go:         parsing registry JSON: action at index 7 is not an object
Rust:       invalid registry structure: action at index 7 is not an object
```

### 5.5 Duplicate `action_id` (new)

If two actions in the `actions` array share an `action_id`, the loader
raises before returning a registry instance. The wrapper does not
silently keep the last one.

**Why.** `tools/validate.py` treats duplicate `action_id` as a
validation error. A wrapper that accepts them would let malformed data
through. The contract's second purpose is "nothing silent," and a
silent last-wins rule is the opposite of that.

The check applies only to actions whose `action_id` is present and
non-empty. Two actions with no `action_id` are not duplicates of each
other; they are missing identifiers (see § 5.6).

Error message names both indices:

```
Python:     ValueError("duplicate action_id at index 42: 'US0378331005-SPLIT-2024-06-10-10-1' (first seen at index 17)")
JavaScript: Error("duplicate action_id at index 42: \"US0378331005-SPLIT-2024-06-10-10-1\" (first seen at index 17)")
Go:         parsing registry JSON: duplicate action_id at index 42: US0378331005-SPLIT-2024-06-10-10-1 (first seen at index 17)
Rust:       invalid registry structure: duplicate action_id at index 42: US0378331005-SPLIT-2024-06-10-10-1 (first seen at index 17)
```

Matching is exact and case-sensitive. `"abc"` and `"ABC"` are different
IDs.

### 5.6 Missing identifier fields (new)

An action with neither `isin` nor `action_id` is a structural error. The
wrapper requires at least one identifier. It does not skip such entries
silently.

**Why.** An action with no ISIN and no action ID cannot be looked up,
joined, or referenced. The validator rejects such entries; the wrapper
follows.

**An action with only `isin`, or only `action_id`, is valid.** The
production schema requires both, but the wrapper accepts either because
some intermediate states during enrichment carry only one. This is the
same tolerance the validator applies at the schema layer.

Error message names the index:

```
Python:     ValueError("invalid actions data: action at index 7 has neither 'isin' nor 'action_id'")
JavaScript: Error("Invalid actions data: action at index 7 has neither \"isin\" nor \"action_id\"")
Go:         parsing registry JSON: action at index 7 has neither 'isin' nor 'action_id'
Rust:       invalid registry structure: action at index 7 has neither 'isin' nor 'action_id'
```

## 6. Error types

Each wrapper uses its language's idiomatic error mechanism. The types
below are the whole of the contract; additional internal error types
are permitted but must not surface to the caller.

| Condition | Python | JavaScript | Go | Rust |
|-----------|--------|------------|-----|------|
| File not found | `FileNotFoundError` | `Error` | `*os.PathError` | `RegistryError::Io` |
| Invalid JSON | `json.JSONDecodeError` | `SyntaxError` (from `JSON.parse`) | `*json.SyntaxError` | `RegistryError::Json` |
| Missing `actions` key | `ValueError` | `Error` | `error` | `RegistryError::InvalidStructure` |
| Non-object action item | `ValueError` | `Error` | `error` | `RegistryError::InvalidStructure` |
| Duplicate `action_id` | `ValueError` | `Error` | `error` | `RegistryError::InvalidStructure` |
| Missing identifier fields | `ValueError` | `Error` | `error` | `RegistryError::InvalidStructure` |
| Invalid `date_field` | `ValueError` | `Error` | `ErrInvalidDateField` | `RegistryError::InvalidDateField` |
| Identifiers file not found | `RuntimeError` | `Error` | `ErrMissingData` | `RegistryError::MissingData` |
| Invalid `source` argument | `ValueError` | `Error` | — | — |

**Message format.** Error messages are not part of the contract, but
each wrapper's message must include:

- The offending value, quoted, when a value is at fault
- The index into the actions array, when an entry is at fault
- The list of valid values, when applicable

Example, invalid date field:

```
Python:     invalid date_field 'exdate'; expected one of ['announcement', 'effective_date', 'ex_date', 'record_date']
JavaScript: invalid dateField 'exdate'; expected one of announcement, ex_date, record_date, effective_date
Go:         invalid date_field: exdate
Rust:       invalid date_field: exdate
```

Go and Rust may use a terser message because the error type itself
carries the meaning; the offending value is still included.

**Sentinel errors.** Go and Rust expose sentinel error values so callers
can match on the class of error without string comparison:

- Go: `ErrInvalidDateField`, `ErrMissingData`
- Rust: `RegistryError::InvalidDateField`, `RegistryError::MissingData`
  (the `RegistryError` enum is `#[non_exhaustive]`)

Python and JavaScript do not use sentinel errors. Callers match on the
exception class (`ValueError`, `RuntimeError`) and, when needed, on the
message text.

## 7. Example CLIs

Each wrapper ships an example CLI under `examples/`. These are not part
of the library API, but they are the first contact most users have with
the wrapper. The contract covers three properties.

### 7.1 Flag values

A flag that takes a value must reject a following flag as its value.
`--date-range 2024-01-01 --isin US0378331005` must be a usage error,
not a silent misparse.

Concretely, in every example CLI:

- `--actions`, `--isin`, `--action-id`, `--action-type`,
  `--date-field` take one value
- `--date-range` takes two values
- A value that begins with `--` is rejected with exit code 2
- A missing value is rejected with exit code 2

### 7.2 Exit codes

Every example CLI uses the same four exit codes:

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Runtime error (file exists but cannot be parsed, or an unexpected error) |
| 2 | Usage error (bad flag, missing value, unknown flag) |
| 3 | File not found |

### 7.3 `--summary`

Where `--summary` is supported, it suppresses the "first few actions"
illustration block. It does not suppress the header (registry metadata)
or the action-type counts. A `--summary` run is quiet but not silent.

## 8. Testing

### 8.1 Per-language unit tests

Each wrapper has its own test suite:

| Wrapper | Command | Location |
|---------|---------|----------|
| Python | `python -m pytest tests/` | `wrappers/python/tests/` |
| JavaScript | `npm test` | `wrappers/javascript/test/` |
| Go | `go test ./registry` | `wrappers/go/registry/` |
| Rust | `cargo test` | `wrappers/rust/tests/` |

Each suite covers:

- Loading from a file path
- Loading from a pre-parsed object
- Every method in Section 4
- Every error condition in Section 6
- The BOM case in Section 5.1
- The missing-actions case in Section 5.2
- Duplicate `action_id` rejection (Section 5.5)
- Missing-identifier rejection (Section 5.6)
- `by_ticker` path resolution and unknown-ticker behaviour (Section 4.8)
- Exported constants (Section 4.9)

### 8.2 Cross-language contract fixture

`tests/wrapper_contract.json` defines a small set of actions, queries,
and tickers. Each wrapper's test suite reads this file and asserts the
same answers, so that a divergence between languages is caught by every
suite, not just the one that changed.

The fixture's shape:

```json
{
  "actions": [ { "action_id": ..., "dates": { ... }, ... }, ... ],
  "queries": [
    {
      "date_field": "ex_date",
      "start": "2024-01-01",
      "end": "2024-12-31",
      "expected_action_ids": [ ... ]
    }
  ],
  "invalid_date_fields": [ "exdate", "ex-date", "effective", "" ],
  "tickers": [
    { "ticker": "AAPL", "exchange": "XNAS", "isin": "US0378331005" }
  ]
}
```

Each wrapper reads the file and:

- Runs every query, comparing the returned `action_id` list to
  `expected_action_ids` in order.
- Asserts that every string in `invalid_date_fields` produces an error.
- For every ticker entry, asserts that `by_ticker(ticker, exchange)`
  returns the same list as `by_isin(isin)`. The `isin` referenced by
  each ticker entry must be present in the fixture's `actions`.

Adding a language does not require editing the fixture. Adding a
contract rule does.

### 8.3 Cache reset for tests

`by_ticker` caches the parsed identifiers index for the life of the
process. Tests that need to load a different identifiers file across
cases must reset the cache between tests. Each wrapper provides a
helper:

- Python: `corporate_actions_registry.registry._TICKER_INDEX_CACHE = None`
- JavaScript: `require('../src/index.js')._resetTickerCache()`
- Go: `registry.ResetTickerIndexCache()`
- Rust: tests run in separate threads with their own `OnceLock`;
  use a fresh `cargo test` invocation per fixture, or pass an explicit
  `identifiers_path` to `by_ticker` on every call.

The cache reset helpers are not part of the public API. They exist for
tests and are marked with a leading underscore in Python and JavaScript,
a `Reset…` prefix in Go, and a `reset_cache` function in Rust.

## 9. Change process

### 9.1 Changes to this document

Any change to this contract is a **breaking change** for the wrappers
unless it only adds new behaviour that was previously undefined. The
change process is:

1. Update the relevant section of this file.
2. Update all four wrappers to match, in separate commits — one per
   wrapper, referencing this file in the commit message.
3. Update `tests/wrapper_contract.json` if the fixture changes.
4. Bump the wrapper version according to semantic versioning.

### 9.2 Changes to a wrapper that do not change the contract

These are ordinary changes. They do not touch this file and do not
require updates to the other wrappers. A commit message that says
"implements docs/wrapper_contract.md" only belongs on a change that
brings the wrapper into compliance with a stated rule.

### 9.3 A new wrapper language

A fifth wrapper is welcome. It must:

1. Implement every method in Section 4.
2. Follow the naming conventions of its language (Section 3).
3. Export the constants in Section 4.9.
4. Pass the cross-language fixture (Section 8.2).
5. Add a row to Section 3 and Section 8.1.

No other file in the repository needs to change.

## 10. Appendix — full signature reference

This table is the quick reference. For behaviour, see Section 4.

### Python

```python
from corporate_actions_registry import (
    CorporateActionsRegistry,
    DEFAULT_DATE_FIELD,
    VALID_DATE_FIELDS,
)

class CorporateActionsRegistry:
    def __init__(self, actions_path: Optional[str] = None,
                 actions_data: Optional[Dict[str, Any]] = None) -> None: ...

    def by_isin(self, isin: str) -> List[Action]: ...
    def by_action_id(self, action_id: str) -> Optional[Action]: ...
    def by_action_type(self, action_type: str) -> List[Action]: ...
    def by_date_range(self,
                      start_date: Optional[str] = None,
                      end_date: Optional[str] = None,
                      date_field: str = DEFAULT_DATE_FIELD) -> List[Action]: ...
    def by_ticker(self,
                  ticker: str,
                  exchange: str,
                  identifiers_path: Optional[str] = None) -> List[Action]: ...
    def all_action_types(self) -> List[str]: ...
    def count(self) -> int: ...
    def to_dict(self) -> Dict[str, Any]: ...
    def save(self, path: str) -> None: ...

# Module scope
DEFAULT_DATE_FIELD: str
VALID_DATE_FIELDS: Tuple[str, ...]
```

### JavaScript

```javascript
const {
    CorporateActionsRegistry,
    DEFAULT_DATE_FIELD,
    VALID_DATE_FIELDS,
} = require('corporate-actions-registry');

class CorporateActionsRegistry {
    constructor(source) { ... }

    byIsin(isin) { ... }                              // -> Object[]
    byActionId(actionId) { ... }                      // -> Object | null
    byActionType(actionType) { ... }                  // -> Object[]
    byDateRange(startDate, endDate,
                dateField = DEFAULT_DATE_FIELD) { ... }
                                                      // -> Object[]
    byTicker(ticker, exchange,
             identifiersPath = null) { ... }          // -> Object[]
    allActionTypes() { ... }                          // -> string[]
    count() { ... }                                   // -> number
    toJSON() { ... }                                  // -> { meta, actions }
    save(filePath) { ... }                            // -> void
}

// Module scope
DEFAULT_DATE_FIELD;                                   // 'ex_date'
VALID_DATE_FIELDS;                                    // string[]
```

### Go

```go
type Registry struct { /* unexported fields */ }

func LoadRegistry(path string) (*Registry, error)
func FromJSON(data []byte) (*Registry, error)

func (r *Registry) ByISIN(isin string) []Action
func (r *Registry) ByActionID(actionID string) *Action
func (r *Registry) ByActionType(actionType string) []Action
func (r *Registry) ByDateRange(startDate, endDate, dateField string)
    ([]Action, error)
func (r *Registry) ByTicker(ticker, exchange, identifiersPath string)
    ([]Action, error)
func (r *Registry) AllActionTypes() []string
func (r *Registry) Count() int
func (r *Registry) ToJSON() ([]byte, error)
func (r *Registry) Save(path string) error

// Module scope
const DefaultDateField = "ex_date"
var ValidDateFields = []string{
    "announcement", "ex_date", "record_date", "effective_date",
}

var ErrInvalidDateField = errors.New("invalid date_field")
var ErrMissingData      = errors.New("missing identifier data")

// Test helper
func ResetTickerIndexCache()
```

### Rust

```rust
pub struct Registry { /* private fields */ }

impl Registry {
    pub fn load_from_file<P: AsRef<Path>>(path: P)
        -> Result<Self, RegistryError>;
    pub fn from_value(data: serde_json::Value)
        -> Result<Self, RegistryError>;

    pub fn by_isin(&self, isin: &str) -> Vec<Action>;
    pub fn by_action_id(&self, action_id: &str) -> Option<Action>;
    pub fn by_action_type(&self, action_type: &str) -> Vec<Action>;
    pub fn by_date_range(&self,
                         start_date: Option<&str>,
                         end_date: Option<&str>,
                         date_field: &str)
                         -> Result<Vec<Action>, RegistryError>;
    pub fn by_ticker(&self,
                     ticker: &str,
                     exchange: &str,
                     identifiers_path: Option<&str>)
                     -> Result<Vec<Action>, RegistryError>;
    pub fn all_action_types(&self) -> Vec<String>;
    pub fn count(&self) -> usize;
    pub fn to_json(&self) -> serde_json::Value;
    pub fn save<P: AsRef<Path>>(&self, path: P)
        -> Result<(), RegistryError>;
}

// Module scope
pub const DEFAULT_DATE_FIELD: &str = "ex_date";
pub const VALID_DATE_FIELDS: &[&str] = &[
    "announcement", "ex_date", "record_date", "effective_date",
];

#[non_exhaustive]
pub enum RegistryError {
    Io(std::io::Error),
    Json(serde_json::Error),
    InvalidStructure(String),
    InvalidDateField(String),
    MissingData(String),
}
```

---

## See also

- [`docs/action_types.md`](./action_types.md) — semantics of the eight
  action types referenced by `action_type`
- [`docs/data_sources.md`](./data_sources.md) — where the data comes
  from and the licensing position
- [`docs/validation_layers.md`](./validation_layers.md) — the seven
  layers that validate `actions.json` before the wrappers ever load it
- [`tests/wrapper_contract.json`](../tests/wrapper_contract.json) — the
  shared fixture that each wrapper's test suite reads
- [`wrappers/python/README.md`](../wrappers/python/README.md) — Python
  wrapper usage
- [`wrappers/javascript/README.md`](../wrappers/javascript/README.md) —
  JavaScript wrapper usage
- [`wrappers/go/README.md`](../wrappers/go/README.md) — Go wrapper usage
- [`wrappers/rust/README.md`](../wrappers/rust/README.md) — Rust
  wrapper usage

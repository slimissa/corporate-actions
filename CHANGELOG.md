# Changelog

All notable changes to the Corporate Actions Registry are documented in
this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## Table of contents

- [How to read this changelog](#how-to-read-this-changelog)
- [Unreleased](#unreleased)
- [1.1.0 — 2026-09-21](#110--2026-09-21)
- [1.0.0 — 2026-09-13](#100--2026-09-13)
- [Pre-release history](#pre-release-history)

---

## How to read this changelog

Entries use the following categories:

| Category | Meaning |
|----------|---------|
| **Added** | New features, actions, wrappers, or files |
| **Changed** | Changes to existing behavior |
| **Deprecated** | Features that will be removed in a future version |
| **Removed** | Features that were removed |
| **Fixed** | Bug fixes |
| **Security** | Security-relevant changes |
| **Data** | Changes to `actions.json` content |
| **Docs** | Documentation-only changes (READMEs, `docs/`, templates) |

Version links at the end of each section compare against the previous
tag. `BREAKING` annotations appear inline for major-version changes.

**A note on section numbering.** Sections are added in release order, but
an item removed or renamed in a later release does not renumber earlier
sections. A missing number means the item was withdrawn, not lost.

---

## Unreleased

_No unreleased changes._

---

## [1.1.0] — 2026-09-21

**Release note.** This release consolidates three workstreams that were
originally slated for separate releases: canonical data cleanup,
doc-fact consistency enforcement, and cross-wrapper unification. They
ship together as `v1.1.0` because the wrapper contract — a minor-version
change — required the earlier work to be complete first.

The headline is `by_ticker` on all four wrappers and a shared contract
that specifies every public method. The rest is the groundwork that
makes the contract verifiable.

### Data

- **No changes to `actions.json` content.** Action count remains 240,
  instruments remain 6, populated types remain 4 of 8.
- **Two semantic duplicate pairs removed** by `scripts/fix_duplicates.py`:
  an AAPL Q2 FY2024 dividend recorded at two different ex-dates, and a
  MSFT Q4 2004 special dividend that Yahoo bundled with the regular
  quarterly dividend at a combined amount. The correct entries are the
  single AAPL dividend on 2024-05-16 and two separate MSFT entries
  (2004-12-09 regular at $0.08, 2004-12-02 special at $3.00).
- **`meta.updated_at` timestamps standardized** to `Z`-suffixed,
  second-precision ISO 8601. Previously mixed.

### Added

#### Wrapper contract and API

- **`docs/wrapper_contract.md` revised to v2.** Adds `by_ticker`,
  the exported constants, the duplicate-`action_id` policy, the
  required-identifier policy, and the `MissingData` error class. The
  document is the source of truth for wrapper behaviour; when the code
  disagrees, the code is wrong.
- **`by_ticker(ticker, exchange)` on all four wrappers.** Resolves a
  ticker and exchange to an ISIN using the Asset Identifiers registry,
  then returns the same list as `by_isin`. Ticker and exchange are
  uppercased before lookup. An unknown pair returns an empty list, not
  an error. See contract section 4.8.
- **Exported constants on all four wrappers**:
  - `DEFAULT_DATE_FIELD` (`"ex_date"`)
  - `VALID_DATE_FIELDS` (the closed set of four date fields)
  
  See contract section 4.9.
- **`RegistryError::MissingData` (Rust) and `ErrMissingData` (Go).**
  Named error class for ticker-resolution failures, so callers can
  match on the class without string comparison.
- **Cache-reset helpers** on all four wrappers for the ticker index:
  `reset_ticker_cache` (Python), `_resetTickerCache` (JavaScript),
  `ResetTickerIndexCache` (Go), `reset_cache` (Rust, re-exported at
  crate scope). See contract section 8.3.
- **Ticker-index modules** in Rust (`ticker_index.rs`) and Go
  (`ticker_index.go`). Both use a per-canonical-path cache so a caller
  who passes the same identifiers file sees the same index, and a
  caller who passes a different one gets a fresh parse.

#### Data pipeline

- **`tools/merge_fetched.py`** — extracts the merge step from
  `run_update.sh`. Rejects three classes of addition: exact duplicates
  (fuzzy key match), deliberately removed actions (matched against
  `_removed_actions.json`), and semantic duplicates (same event under a
  different ID scheme, detected by `validate_semantic_uniqueness`).
- **`_removed_actions.json`** — durable reject list for actions that
  have been deliberately removed from `actions.json`. The merge step
  refuses to re-add any action matching a reject-list entry, matched by
  `(isin, action_type_family, ex_date, amount)`. The family collapses
  `DIVIDEND`+`SPECIAL_DIVIDEND` and `SPLIT`+`REVERSE_SPLIT`.
- **`tools/update_facts.py`** — regenerates `docs/facts.json` from the
  code, the data, and the wrapper test collectors. Runs in CI as
  `--check`, so a stale fact sheet fails the build.
- **`tools/check_doc_facts.py --scan` mode** — scans docs for any number
  near a known keyword that is not present in `docs/facts.json`. Catches
  the class of doc drift that a fixed-value regex cannot.
- **`scripts/fix_duplicates.py` appends to the reject list** on removal,
  so any future correction the script makes is automatically protected
  against re-fetch.

#### CI and enforcement

- **`tests/test_ci_gates.py`** — proves each CI gate actually catches
  the drift it claims to. Every gate has a positive case (clean tree
  passes) and a negative case (deliberately corrupted tree fails).
- **Three new CI jobs in `validate.yml`**:
  - `docs-facts` — runs `check_doc_facts.py`, `check_doc_facts.py --scan`,
    and `update_facts.py --check`.
  - `build-artifacts` — regenerates `dist/` and verifies with
    `build.py --check`.
  - `lint` — runs `ruff check` on `tests/`, `tools/`, `examples/`,
    `scripts/`.
- **`pyproject.toml`** with `ruff` configuration. Initial scope is
  pyflakes-only (`F` rules) so pre-existing style is not gated; broader
  rules can be enabled incrementally.

#### Tests

- `tests/test_doc_facts.py` — 27 tests covering `facts.json` structure,
  its consistency with `actions.json`, the manifest integrity, the
  checker's behaviour on a clean and a corrupted tree, and cross-doc
  consistency checks that the manifest cannot express as regexes.
- `tests/test_merge_fetched.py` — 8 tests covering the three rejection
  rules, `--strict`, `--dry-run`, and missing-file handling.
- `tests/test_ci_gates.py` — proves the three new CI jobs fire.

### Changed

#### Wrapper behaviour

- **Duplicate `action_id` is now a load-time error in all four
  wrappers.** Previously the last-inserted entry silently won. The
  validator already treats duplicate IDs as an error; a wrapper that
  accepted them would let malformed data through. See contract
  section 5.5.
- **An action with neither `isin` nor `action_id` is now a load-time
  error in all four wrappers.** An entry with no identifier cannot be
  looked up, joined, or referenced. See contract section 5.6.
- **`by_date_range` empty-string bounds** are now treated as "no bound"
  uniformly across all four wrappers. Previously Python, JavaScript, and
  Go behaved this way; Rust treated `Some("")` as a bound of empty
  string, which excluded every action.
- **The `date_field` default is a language-idiomatic concession, not a
  semantic difference.** Python and JavaScript default to `"ex_date"`;
  Go and Rust require the argument and export `DEFAULT_DATE_FIELD` /
  `DefaultDateField` for callers who want the same value without
  hard-coding it. All four wrappers treat an explicit `"ex_date"` and an
  omitted argument identically.

#### Validator and tools

- **`tools/validate.py` replaces the `MERGER` special-case with an
  `ALLOWED_ACTION_TYPES` allowlist.** The previous behaviour was a
  schema-vs-validator disagreement: the schema accepted `MERGER`,
  the validator rejected it, and the error message did not name the
  offending value. Now the error is uniform for every non-allowlisted
  type.
- **`tools/validate.py` passes a `FormatChecker`** to
  `jsonschema.validate`. `format: date` and `format: date-time` are now
  enforced, not merely declared.
- **`tools/validate.py` validates the full document** before running the
  per-action loop. Previously a stray top-level key was silently
  accepted.
- **`tools/validate.py` adds `validate_action_id_format`** to check the
  discriminator content, not just the shape. A split ID whose
  discriminator does not match the ratio is now rejected.
- **`resolve_default_identifiers_path` doc and code aligned.** The
  docstring previously described a fixture fallback the code did not
  implement.
- **`run_update.sh` refuses broken fetchers with `usage_error` (exit
  2).** Previously it used `error_exit` (exit 1), which obscured the
  difference between a typo and a pipeline failure.
- **`run_update.sh` deletes a stale local tag before creating a new
  one.** A locally-existing tag that the remote did not have caused an
  opaque `git tag` failure.
- **`run_update.sh --commit` refuses when `--skip-tests` is set.** A
  commit that ships without tests is a commit that ships with unknown
  state.
- **`run_update.sh --dry-run` no longer mutates `actions.json`.**
  Previously the merge step and `derive_impacts.py` both wrote
  unconditionally; `--dry-run` now passes through to both.
- **`fetch_yahoo_actions.py` narrows the retry `except`.** The previous
  bare `except Exception` caught `KeyboardInterrupt` and `SystemExit`.
  The retry now catches only transient network and rate-limit failures.
- **`notify_on_change.py` narrows the webhook `except`.** Previous
  behaviour caught `MemoryError` and `KeyboardInterrupt`; now only
  `URLError`, `HTTPError`, `TimeoutError`, and `ValueError`.
- **`notify_on_change.py` cleans up its temp file on failure.** An
  exception between the temp write and the atomic rename left an orphan
  `.tmp` file behind.

#### Documentation

- **All four wrapper READMEs** now document `by_ticker`, the exported
  constants, and the error semantics from the contract.
- **`docs/validation_layers.md`** corrects the Layer 2 date-validation
  statement (Layer 1 enforces `format: date`; Layer 2 does not) and the
  Layer 7 default (`100`, not `1`).
- **`CONTRIBUTING.md` §3.5** corrects the `CORP_ACTIONS_MIN_ACTIONS`
  default (`100`, not `1`).
- **`docs/data_sources.md`** documents the reject list and its
  purpose.

### Fixed

#### Validator

- **`validate.py` no longer crashes on a non-dict action entry.** The
  main loop previously raised `AttributeError` on a string or number.
- **`validate.py` no longer crashes on an action missing `action_type`.**
  `validate_arithmetic` previously raised `KeyError`.
- **`validate_arithmetic` treats a missing `action_type` as a skipped
  check.** The schema layer catches missing fields; the arithmetic layer
  is a backup.
- **`load_identifiers_registry` fallback checks all elements.** The
  previous `value[0]` check silently skipped lists whose first entry
  was metadata and whose second entry was a valid instrument.
- **`load_exchange_calendar_registry` fallback checks all elements.**
  Same class of bug.

#### Tools

- **`derive_impacts.py` refuses to write when any action fails.** A
  single failure no longer leaves a file with some actions carrying
  fresh multipliers and others carrying stale ones.
- **`derive_impacts.py` ratio parser aligned with `validate_arithmetic`.**
  A ratio that passed one tool but failed the other is no longer
  possible.
- **`build.py` moves `build_timestamp` to a sidecar.** The primary
  artifacts are byte-identical across runs on identical input.
- **`build.py` collects CSV columns from every action.** A column
  present only on an action past index 10 was previously dropped.
- **`build.py` `flatten_action` rejects nested dicts and lists.** A
  structured value cannot round-trip through a CSV cell; the previous
  silent `repr()` embedding produced a file that looked correct and
  was not.
- **`build.py --check` compares bytes, not decoded text.** A CSV written
  with `\r\n` line terminators read back with universal-newlines returned
  a different string from what was written. The comparison now works on
  raw bytes.
- **`fetch_sec_edgar_actions.py` no longer skips the delisting check
  after a symbol-change match.** The previous `continue` meant a filing
  announcing both was recorded as only a symbol change.
- **`fetch_sec_edgar_actions.py` `SYMBOL_CHANGE_TRIGGERS` reject
  candidates followed by alphanumerics.** The previous regex matched
  `AB1` and `ABCDEFGH` as symbols; now the trailing
  `(?![A-Za-z0-9])` guard applies.
- **`fetch_sec_edgar_actions.py` warns when `filings.files[]` is
  non-empty.** The submissions endpoint returns only the last ~1,000
  filings; older filings live in archive files that the fetcher does
  not yet read. A partial result is now visible rather than silent.
- **`fetch_yahoo_actions.py` gates its exit code on the error list.** A
  partial run now exits 1, not 0. A run where every ticker failed exits
  3.
- **`fetch_yahoo_actions.py` adds retries with exponential backoff.**
  Transient 429s, timeouts, and DNS failures are retried up to
  `MAX_RETRIES` times.
- **`fetch_sec_edgar_actions.py` retries with exponential backoff.**
  Same class of fix.

#### Scripts

- **`notify_on_change.py` state-file writes are atomic.** A killed
  process between the temp write and the rename leaves the original
  file untouched rather than truncated.
- **`scripts/README.md` mojibake reversed.** UTF-8 bytes had been
  decoded as Latin-1 in an earlier edit.
- **`scripts/README.md` no longer claims `sec` is refused.** The code
  runs the SEC fetcher; the README now says so.

#### Wrappers

- **Go `ByDateRange` deep-copies its results.** Previously a caller
  could corrupt the registry's internal state by mutating a returned
  `Dates`, `Provenance`, or `Impact` field.
- **Contract-fixture absence is fatal at collection** in all four
  wrappers. Previously a missing `tests/wrapper_contract.json` caused a
  silent skip; a silently-skipping test is worse than no test.
- **Python `from yfinance import ticker` removed.** The wrapper imports
  only the standard library; the stray import was leftover from a
  debugging session.
- **JavaScript `byActionId` and `toJSON` use `structuredClone`.**
  Previously they used `JSON.parse(JSON.stringify(...))`, which dropped
  `undefined`, converted `NaN` to `null`, and stringified `Date` values.
  Now all five lookup methods use the same copy primitive.
- **Rust `by_date_range` treats `Some("")` as "no bound".** Previously
  the empty string was a bound and excluded every action.
- **`test_no_fetcher_output_in_tree` matches by basename.** The previous
  substring match flagged `tools/fetch_yahoo_actions.py` and
  `tests/test_fetch_yahoo_actions.py` as tracked fetcher output.
- **`tests/test_semantic_uniqueness.py::test_missing_isin_skips_action`
  now calls the function under test.** The previous body had no
  assertion.

### Removed

- **`tools/fetch_dividends_nasdaq.py`.** The Nasdaq dividends API times
  out from non-US IPs and CI runners, and Yahoo Finance covers the same
  data reliably via `yfinance`. Passing `--fetch-source nasdaq` to
  `scripts/run_update.sh` now exits 2 with a message rather than
  running a broken code path.

### Security

- No security issues were known at release time.
- The `v1.0.0` history rewrite (see below) is documented in
  `CONTRIBUTING.md` §10.7 as the reason for the rule against committing
  licensed identifier data.

### Known issues

These are documented limitations, not bugs. They are tracked in
[`docs/roadmap.md`](./docs/roadmap.md).

- **SEC EDGAR fetcher scope is narrow.** Limited to `SYMBOL_CHANGE` and
  `DELISTING`, and to the last ~1,000 filings per company. Older
  filings live in archive files the fetcher does not yet read.
- **SEC `SYMBOL_CHANGE_TRIGGERS` blocklist can drop real tickers.**
  `COMMON_ENGLISH_WORDS` contains `AN`, `DO`, `GO`, `HE`, `IT`, `ME`,
  `ON`, `SO`, `UP`, `WE` — all real US-listed tickers. A symbol change
  to any of these is silently dropped. Fix targeted for v1.2.0.
- **`MERGER` action type is not populated.** The schema reserves it; the
  validator rejects any `MERGER` entry until the extraction pipeline
  supports it.
- **No international coverage.** US equities only.
- **No non-USD dividends.** All current instruments are US-listed.
- **Announcement dates are approximated for Yahoo-sourced dividends.**
  The Yahoo API does not expose the announcement date, so it is set
  equal to the ex-date.
- **Dividend amounts are split-adjusted as provided by yfinance.** A
  dividend paid before a split is reported at the post-split equivalent
  amount.
- **Cross-language consistency is tested only for `by_date_range`.** The
  shared fixture covers query semantics, duplicate-id rejection, missing
  identifiers, and empty-string bounds. A broader runtime comparison is
  a later phase.

---

## [1.0.0] — 2026-09-13

The first production release of the Corporate Actions Registry. 242
actions at tag time (240 after the duplicate removal documented in
v1.1.0), four language wrappers, seven-layer validation, three CI
workflows, complete documentation.

### Data

- **240 actions** across 6 instruments
- **4 action types populated**: `SPLIT`, `DIVIDEND`, `SPECIAL_DIVIDEND`,
  `SYMBOL_CHANGE`
- **4 action types reserved**: `REVERSE_SPLIT`, `SPINOFF`, `DELISTING`,
  `MERGER`
- **6 instruments covered**: AAPL, AMZN, GOOGL, META, MSFT, NVDA
- **Historical depth**: earliest action in the registry is from 2000
- **Currency**: USD only

### Added

#### Registry and schema

- 242 corporate actions at tag time
- `schema.json` — JSON Schema (Draft 07) supporting 8 action types with
  per-type `oneOf` constraints
- `meta` block with `version`, `generated_at`, `source`, `updated_at`,
  `notes`
- Null-tolerant optional date fields (`ex_date`, `record_date`) and
  optional `verification_source` / `verification_url` fields
- `impact` block on every action (`price_multiplier`, `share_multiplier`,
  `cash_adjustment`)

#### Tools

- `tools/validate.py` — seven-layer validator (schema, temporal,
  arithmetic, cross-reference, uniqueness, provenance, coverage)
- `tools/derive_impacts.py` — computes `impact` multipliers from `ratio`
  and `amount`
- `tools/build.py` — generates distribution artifacts (dist JSON,
  minified JSON, CSV, SQL)
- `tools/fetch_yahoo_actions.py` — working fetcher using the `yfinance`
  library
- `tools/fetch_sec_edgar_actions.py` — SEC EDGAR fetcher

#### Wrappers

Four language wrappers, all with parity APIs and test suites:

| Wrapper | Tests at v1.0.0 | API |
|---------|:---------------:|-----|
| Python | 23 | `CorporateActionsRegistry` |
| JavaScript | 16 | `CorporateActionsRegistry` |
| Go | 17 | `registry.Registry` |
| Rust | 26 | `corporate_actions_registry::Registry` |

Each wrapper provided:

- `by_isin(isin)` — all actions for an instrument
- `by_action_id(action_id)` — single action by ID
- `by_action_type(action_type)` — all actions of a type
- `by_date_range(start, end, field)` — date-range filter
- `all_action_types()` — sorted list of unique types
- `count()` — total action count
- `to_json()` / `to_dict()` — serialization
- `save(path)` — persist to disk

#### Root test suite

- 143 tests across 8 files:
  - `test_arithmetic.py` — 20 tests
  - `test_cross_reference.py` — 17 tests
  - `test_notify_on_change.py` — 16 tests
  - `test_provenance.py` — 10 tests
  - `test_schema.py` — 20 tests
  - `test_temporal.py` — 37 tests
  - `test_uniqueness.py` — 11 tests
  - `test_wrappers.py` — 12 tests

#### CI workflows

- `.github/workflows/validate.yml` — runs 5 jobs on every push and PR:
  - Registry validator against fixtures
  - Python tests (root + wrapper)
  - JavaScript tests
  - Go tests
  - Rust tests + `cargo fmt --check` + `cargo clippy -- -D warnings`
- `.github/workflows/check-sources.yml` — weekly source health monitor
  with automatic issue open/close
- `.github/workflows/update-actions.yml` — weekly fetch, fuzzy-dedup
  merge, and automated PR creation

#### Scripts

- `scripts/run_update.sh` — full pipeline (fetch → merge → derive →
  validate → test → build → notify → commit)
- `scripts/notify_on_change.py` — SHA-256 change detection with optional
  webhook notification
- `scripts/README.md` — script documentation

#### Examples

- `examples/python_lookup.py` — Python wrapper CLI demo
- `examples/javascript_lookup.js` — JavaScript wrapper CLI demo
- `examples/go_lookup.go` — Go wrapper CLI demo
- `examples/rust_lookup.rs` — Rust wrapper CLI demo
- `examples/backtest_adjustment.py` — demonstrates split and dividend
  adjustment using the registry

#### Documentation

- `README.md` — repository overview, quick start, coverage
- `docs/action_types.md` — semantics of each of the eight action types
- `docs/validation_layers.md` — the seven validation layers
- `docs/data_sources.md` — sources, licensing, reliability
- `docs/roadmap.md` — v1.0.0 through v3.0.0
- `docs/contributing.md` — documentation contribution guide
- `CONTRIBUTING.md` — code contribution guide
- `LICENSE` — Apache 2.0, copyright Le P'tit
- `CHANGELOG.md` — this file

#### Templates

- `.github/PULL_REQUEST_TEMPLATE.md` — adaptive PR template
- `.github/ISSUE_TEMPLATE/action_update.md` — report a missing or
  incorrect action
- `.github/ISSUE_TEMPLATE/data_source.md` — propose a new data source

#### Fixtures

- `tests/fixtures/identifiers.json` — Asset Identifiers snapshot for CI
- `tests/fixtures/iso4217.json` — ISO 4217 snapshot for CI
- `tests/fixtures/exchange_calendar.json` — Exchange Calendar snapshot
  for CI

### Changed

- **Validator reads Asset Identifiers from
  `$LAS_DATA_HOME/identifiers.json` by default**, with `--identifiers`
  CLI override and `CORP_ACTIONS_IDENTIFIERS_PATH` env override.
  Previously read from a hardcoded sibling path.
- **Missing ISINs are warnings, not errors**, by default. The
  `--strict-isin` flag restores error behavior. This accommodates the
  Asset Identifiers rebuild, which currently ships 50 of 515 ISINs.
- **`fetch_yahoo_actions.py` uses `yfinance`** instead of raw HTTP
  requests. This resolves the HTTP 429 rate-limiting that blocked the
  previous implementation.
- **Fuzzy dedup** in the merge pipeline uses
  `(isin, action_type, ex_date, ratio, amount)` instead of exact
  `action_id` match. This catches duplicate events expressed under
  different ID schemes.
- **`run_update.sh` refuses broken fetchers** (`sec`, `nasdaq`) with a
  clear error message instead of running a broken code path.
- **CI includes Rust `clippy` and `fmt` checks** enforced with
  `-D warnings`. These are gating, not advisory.

### Fixed

- `datetime.utcnow()` deprecation warnings in `tools/build.py` and
  `tools/fetch_dividends_nasdaq.py` replaced with
  `datetime.now(timezone.utc)`.
- `validate_cross_reference` treats missing ISIN as an error when
  `isin_warnings` is not provided. Previously it silently did nothing.
- CI Go cache warning suppressed by setting `cache: false` on
  `actions/setup-go`.
- `scripts/notify_on_change.py` state file path resolution corrected.
- Rust wrapper `Dates`, `Provenance`, and `Impact` structs derive
  `PartialEq` so tests can compare them.
- Rust wrapper `all_actions()` accessor added so examples can iterate.
- `.gitignore` now covers `.venv/`, `.cache_yahoo/`,
  `.cache_sec_edgar/`, `.notify_state.json`, `yahoo_actions_test.json`,
  `fetched_actions.json`, `dist/`, and `wrappers/rust/target/`.

### Removed

- `scripts/sync_wrappers.sh` — unnecessary; wrappers load
  `actions.json` by path, they do not embed a copy.
- `dividends_actions.json` and `yahoo_actions.json` — stale exploratory
  output, not part of the release.
- `wrappers/rust/target/` — removed from git tracking; now ignored.

### Known issues

Documented limitations at release time. Most have since been resolved;
see v1.1.0.

- **SEC EDGAR fetcher returns HTTP 500.** The legacy full-text search
  endpoint was retired by the SEC. Recovery is planned for v1.1.0 using
  the `data.sec.gov` submissions API.
- **Nasdaq dividends fetcher times out.** The API blocks non-US IPs and
  CI runners. Scheduled for removal in v1.1.0 since Yahoo covers the
  same data reliably.
- **`MERGER` action type is not populated.** Schema reserves it; the
  validator explicitly rejects any `MERGER` entry in v1.0.0.
- **No international coverage.** US equities only.
- **No non-USD dividends.** All current instruments are US-listed.
- **Ticker-to-ISIN lookup is heuristic.** The example scripts scan
  `provenance.source_url` for the ticker. A proper lookup depends on
  Asset Identifiers exposing a ticker→ISIN index (planned for their
  v1.1.0).
- **Cross-language consistency is not automatically tested in CI.**
  Wrapper test suites validate each language independently. A
  cross-wrapper comparison test is planned for v1.1.0.

### Security

- No security issues were known at release time.
- Security reporting process established: private vulnerability reports
  via GitHub Security Advisories. See
  [`CONTRIBUTING.md`](./CONTRIBUTING.md#12-security-disclosure).

### Tag note

The `v1.0.0` tag was force-pushed on 2026-09-14 as part of a history
rewrite that removed licensed identifier data from the repository. Any
consumer who pinned `v1.0.0` before that date should re-pin. The
rewritten tag is the authoritative `v1.0.0`.

---

## Pre-release history

Prior to v1.0.0, the registry went through four internal phases that are
not tagged as releases. They are documented here for context.

### Phase 1 — Repository skeleton (2026-09-10)

- Initial repository structure created
- Empty `schema.json`, `actions.json`, wrapper directories, tool
  directories
- `README.md`, `LICENSE`, `CONTRIBUTING.md` placeholders

### Phase 2 — Core validators and wrappers (2026-09-11)

- `schema.json` supporting 8 action types
- `validate.py` with 7 layers
- First 5 hand-curated actions (NVDA split, AAPL split, AAPL dividend,
  MSFT special dividend, META symbol change)
- Python wrapper implemented and tested (23 tests)
- JavaScript wrapper implemented and tested (16 tests)
- Go wrapper implemented and tested (17 tests)
- Rust wrapper implemented and tested (26 tests)
- Root test suite written (143 tests)

### Phase 3 — Working fetcher and expanded registry (2026-09-12)

- `fetch_yahoo_actions.py` rewritten to use `yfinance`
- First successful automated extraction: 176 actions from 5 tickers
- Merged into `actions.json` → 181 actions
- Second extraction after removing dead cache: 61 more actions
- Merged with fuzzy dedup → **242 actions**
- `derive_impacts.py` run against expanded registry

### Phase 4 — CI, scripts, documentation, release (2026-09-13)

- Three GitHub Actions workflows added and verified green
- `scripts/` folder hardened: fuzzy dedup, `--dry-run`, refusal of
  broken sources, `notify_on_change.py` tests
- Full documentation written: `docs/action_types.md`,
  `docs/validation_layers.md`, `docs/data_sources.md`,
  `docs/roadmap.md`, `docs/contributing.md`
- Root `CONTRIBUTING.md`, `LICENSE`, issue templates, PR template
- `v1.0.0` tagged

---

## Version links

- [Unreleased] — https://github.com/slimissa/corporate-actions/compare/v1.1.0...HEAD
- [1.1.0] — https://github.com/slimissa/corporate-actions/releases/tag/v1.1.0
- [1.0.0] — https://github.com/slimissa/corporate-actions/releases/tag/v1.0.0

---

## See also

- [`docs/roadmap.md`](./docs/roadmap.md) — what comes next
- [`docs/data_sources.md`](./docs/data_sources.md) — data source status
- [`docs/wrapper_contract.md`](./docs/wrapper_contract.md) — the wrapper
  contract every release must satisfy
- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — how to contribute
- [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — the format
- [Semantic Versioning](https://semver.org/spec/v2.0.0.html) — the version policy
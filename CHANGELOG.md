# Changelog

All notable changes to the Corporate Actions Registry are documented in
this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## Table of contents

- [How to read this changelog](#how-to-read-this-changelog)
- [Unreleased](#unreleased)
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

Version links at the end of each section compare against the previous
tag. `BREAKING` annotations appear inline for major-version changes.

---

## Unreleased

### Planned for v1.1.0

See [`docs/roadmap.md`](./docs/roadmap.md) for the full plan. Summary:

**Added**
- `MERGER` action type populated from SEC S-4 filings
- Expanded coverage to 50+ US instruments
- Cross-language consistency tests in CI
- Python wrapper published to PyPI
- JavaScript wrapper published to npm
- Rust wrapper published to crates.io
- Go module tagged and published

**Changed**
- `--strict-isin` becomes the default (missing ISIN is an error, not a warning)
- CI `--min-actions` floor raised to 200
- `fetch_yahoo_actions.py` gains announcement-date inference from additional sources
- Fuzzy dedup hardened with normalized comparison

**Removed**
- `tools/fetch_dividends_nasdaq.py` (redundant with Yahoo Finance)

**Fixed**
- `tools/fetch_sec_edgar_actions.py` rewritten to use `data.sec.gov` submissions API
- Ticker-to-ISIN lookup no longer relies on `provenance.source_url` scanning

---

## [1.0.0] — 2026-09-13

The first production release of the Corporate Actions Registry. 242
actions, four language wrappers, 7-layer validation, three CI workflows,
complete documentation.

### Data

- **242 actions** across 10 instruments
- **5 action types populated**: `SPLIT`, `REVERSE_SPLIT`, `DIVIDEND`,
  `SPECIAL_DIVIDEND`, `SYMBOL_CHANGE`
- **3 action types reserved**: `SPINOFF`, `DELISTING`, `MERGER`
  (schema-valid but not populated)
- **10 instruments covered**: AAPL, AMZN, GOOGL, META, MSFT, NVDA, plus
  a small number of ETFs and additional US large caps
- **Historical depth**: dividends and splits back to 1987 for the
  longest-history instruments
- **Currency**: USD only

### Added

#### Registry and schema

- `actions.json` — canonical registry of 242 corporate actions
- `schema.json` — JSON Schema (Draft 07) supporting 8 action types with
  per-type `oneOf` constraints
- `meta` block with `version`, `generated_at`, `source`, `updated_at`,
  `notes`
- Null-tolerant optional date fields (`ex_date`, `record_date`) and
  optional `verification_source` / `verification_url` fields
- `impact` block on every action (`price_multiplier`, `share_multiplier`,
  `cash_adjustment`)

#### Tools

- `tools/validate.py` — 7-layer validator (schema, temporal, arithmetic,
  cross-reference, uniqueness, provenance, coverage)
- `tools/derive_impacts.py` — computes `impact` multipliers from `ratio`
  and `amount`
- `tools/build.py` — generates distribution artifacts (dist JSON,
  minified JSON, CSV, SQL)
- `tools/fetch_yahoo_actions.py` — working fetcher using the `yfinance`
  library
- `tools/fetch_sec_edgar_actions.py` — SEC EDGAR fetcher (currently
  broken; see Known Issues)
- `tools/fetch_dividends_nasdaq.py` — Nasdaq dividend fetcher (currently
  broken; scheduled for removal)
- `tools/requirements.txt` — Python dependencies

#### Wrappers

Four language wrappers, all with parity APIs and test suites:

| Wrapper | Tests | API |
|---------|-------|-----|
| Python | 23 | `CorporateActionsRegistry` |
| JavaScript | 16 | `CorporateActionsRegistry` |
| Go | 17 | `registry.Registry` |
| Rust | 26 | `corporate_actions_registry::Registry` |

Each wrapper provides:

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

- **Validator reads Asset Identifiers from `$LAS_DATA_HOME/identifiers.json`
  by default**, with `--identifiers` CLI override and
  `CORP_ACTIONS_IDENTIFIERS_PATH` env override. Previously read from a
  hardcoded sibling path.
- **Missing ISINs are warnings, not errors**, by default. The
  `--strict-isin` flag restores error behavior. This accommodates the
  Asset Identifiers rebuild which currently ships 50 of 515 ISINs.
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
- `.gitignore` now covers `.venv/`, `.cache_yahoo/`, `.cache_sec_edgar/`,
  `.notify_state.json`, `yahoo_actions_test.json`, `fetched_actions.json`,
  `dist/`, and `wrappers/rust/target/`.

### Removed

- `scripts/sync_wrappers.sh` — unnecessary; wrappers load
  `actions.json` by path, they do not embed a copy.
- `dividends_actions.json` and `yahoo_actions.json` — stale exploratory
  output, not part of the release.
- `wrappers/rust/target/` — removed from git tracking; now ignored.

### Known issues

These are documented limitations, not bugs to be fixed in a patch
release. They are tracked in [`docs/roadmap.md`](./docs/roadmap.md).

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
  via GitHub Security Advisories. See [`CONTRIBUTING.md`](./CONTRIBUTING.md#12-security-disclosure).

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

- [1.0.0] — https://github.com/slimissa/corporate-actions/releases/tag/v1.0.0
- [Unreleased] — https://github.com/slimissa/corporate-actions/compare/v1.0.0...HEAD

---

## See also

- [`docs/roadmap.md`](./docs/roadmap.md) — what comes next
- [`docs/data_sources.md`](./docs/data_sources.md) — data source status
- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — how to contribute
- [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — the format
- [Semantic Versioning](https://semver.org/spec/v2.0.0.html) — the version policy
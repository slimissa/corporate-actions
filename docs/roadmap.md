# Roadmap

This document describes the plan for the Corporate Actions Registry from
v1.0.0 through v3.0.0. It lists what each version aims to deliver, what
dependencies must be resolved, and which items are uncertain.

The roadmap is a working document, not a contract. Priorities shift when
external factors shift — a broken source, a licensing blocker, or a
cross-registry dependency can move an item forward or backward. Each
version section states its success criteria so that "done" is falsifiable.

---

## Table of contents

1. [Where we are now](#where-we-are-now)
2. [Release philosophy](#release-philosophy)
3. [v1.0.0 — Foundation](#v100--foundation)
4. [v1.1.0 — US completeness](#v110--us-completeness)
5. [v1.2.0 — International expansion](#v120--international-expansion)
6. [v2.0.0 — Real-time pipeline](#v200--real-time-pipeline)
7. [v3.0.0 — Global comprehensive](#v300--global-comprehensive)
8. [What is not on the roadmap](#what-is-not-on-the-roadmap)
9. [Dependencies and blockers](#dependencies-and-blockers)
10. [Cross-registry coordination](#cross-registry-coordination)
11. [How to influence the roadmap](#how-to-influence-the-roadmap)
12. [Timeline caveats](#timeline-caveats)

---

## Where we are now

As of v1.1.1 (2026-10-08):

| Metric | Value |
|--------|-------|
| Actions | 240 |
| Instruments covered | 6 US large caps |
| Action types populated | 4 of 8 (`SPLIT`, `DIVIDEND`, `SPECIAL_DIVIDEND`, `SYMBOL_CHANGE`) |
| Action types accepted but unpopulated | 3 of 8 (`REVERSE_SPLIT`, `SPINOFF`, `DELISTING`) |
| Action types rejected by validator | 1 of 8 (`MERGER`) |
| Redistribution categories in use | 2 (`secondary-source`, `facts-only`) |
| Root tests | <N> |
| Wrapper tests | 119 Python, 101 JavaScript, 79 Go, 98 Rust (+1 doctest) |
| CI workflows | 1 (`validate.yml`, 6 jobs) |
| Working fetchers | 2 (Yahoo Finance; SEC EDGAR for SYMBOL_CHANGE, DELISTING) |
| SEC filing coverage | Full history (archive loading added v1.1.1) |
| SEC corpus | 2 positives, 9 negatives |
| Redistribution doc | `docs/redistribution.md` |
| Sibling registries pinned | `tools/sibling_versions.json` |

The registry is **production-ready for US-equity splits, dividends,
and symbol changes across six large-cap instruments**. Expansion to a
larger instrument set is v1.2.0.
---

## Release philosophy

The version numbers follow [semantic versioning](https://semver.org) for the
registry data and the wrapper APIs:

- **Patch** (`1.0.1`): data corrections, documentation fixes, non-breaking
  tool improvements.
- **Minor** (`1.1.0`): new actions added, new instruments covered, new
  action types populated, new optional schema fields.
- **Major** (`2.0.0`): breaking changes to schema, wrappers, or tool CLI.

### What counts as a "release"

A release is a tagged commit on `main` where:

- All CI jobs pass
- All tests pass
- The validator passes with the release's `--min-actions` floor
- `CHANGELOG.md` documents what changed
- The wrapper versions are consistent with the registry version

A commit on `main` without a tag is not a release. It is an incremental
change that will be included in the next release.

### Release cadence

| Type | Cadence | Examples |
|------|---------|----------|
| Patch | As needed | Data corrections |
| Minor | Every 4–8 weeks | Coverage expansion, new fetchers |
| Major | Every 6–12 months | Schema changes, breaking API changes |

---

## v1.0.0 — Foundation

**Status**: Shipped. Tag `v1.0.0` (2026-09-13).

**Success criteria**:

- [x] 100+ actions in the registry
- [x] Four language wrappers with test suites
- [x] Validator with all seven layers
- [x] CI green on every push
- [x] At least one working data source
- [x] Documentation for every public concept
- [x] Examples in all four languages
- [x] Scripts for update and notification
- [x] Issue and PR templates

**What shipped**:

- 240 actions across 6 instruments (242 at tag time)
- Schema for 8 action types (4 populated)
- 7-layer validator
- Four language wrappers (Python, JS, Go, Rust) with 82 tests
- 781 root tests
- 93 (JS) + 70 (Rust) wrapper tests and 781 root tests
- 3 GitHub Actions workflows
- Working Yahoo Finance fetcher
- Cross-reference validation against 3 external registries
- Full documentation: action types, data sources, validation layers

**Known limitations documented at release**:

- SEC EDGAR fetcher broken
- Nasdaq fetcher broken
- No MERGER support
- No international coverage
- No non-USD dividends
- Fuzzy dedup only catches some duplicate patterns
- Cross-language consistency not automatically tested

---

## v1.1.0 — US completeness

**Status**: In planning.

**Target**: 4–8 weeks after v1.0.0.

**Theme**: Close the US coverage gap and fix the broken infrastructure.

### Success criteria

- [ ] All 8 action types populated (or explicitly deferred with reason)
- [ ] Coverage expanded to at least 50 US instruments
- [ ] Cross-language consistency tests in CI
- [ ] Wrappers published to their package registries
- [ ] `--strict-isin` flipped to default
- [ ] `--min-actions` set to 200 in CI

### Items

#### 1. Fix SEC EDGAR fetcher ✅ DONE (2026-09-20)

**Priority**: High
**Effort**: 1–2 weeks
**Blocker**: The legacy full-text search endpoint returns HTTP 500.

Plan:

- Use `data.sec.gov/submissions/CIK{cik}.json` to list filings per company
- Filter to 8-K filings
- Download and parse the 8-K documents
- Extract corporate action details from the filing text

The alternative (`browse-edgar` scraping) is a fallback if
`data.sec.gov` is insufficient.

#### 2. ~~Remove Nasdaq fetcher~~ ✅ DONE (2026-09-13)

**Status**: Completed. Deleted `tools/fetch_dividends_nasdaq.py`.
See commit `864d746`.

#### 3. Add MERGER support (2015+ only)

**Priority**: High
**Effort**: 2–3 weeks
**Blocker**: Depends on SEC EDGAR fetcher.

Plan:

- Extend `fetch_sec_edgar_actions.py` to parse SEC S-4 filings
- Extract acquirer ISIN, target ISIN, exchange ratio, cash component
- Add `MERGER` to the validator's allowed action types
- Add a `status` lifecycle (announced, approved, closed, terminated)
- Write tests

Restricting to 2015+ avoids the sparse 1990s filing data.

#### 4. Expand to 50 instruments

**Priority**: High
**Effort**: 2–4 weeks
**Blocker**: Depends on Asset Identifiers coverage.

Plan:

- Once Asset Identifiers reaches 500+ ISINs, expand the fetch list
- Filter to tickers with valid ISINs
- Run the fetcher; expect 1,000–2,000 new actions
- Merge with fuzzy dedup
- Validate
- Tag v1.1.0

#### 5. Cross-language consistency tests

**Priority**: Medium
**Effort**: 1 week
**Blocker**: None.

Plan:

- Add `tests/test_cross_language.py`
- Load `actions.json` in all four wrappers
- Compare `by_isin`, `by_action_id`, `by_action_type`, `by_date_range`
- Fail on any divergence

This catches subtle parsing differences (e.g. date comparison, float
representation) that unit tests do not.

#### 6. Publish wrappers

**Priority**: High
**Effort**: 1–2 days
**Blocker**: None, but requires npm/PyPI/crates.io account setup.

| Wrapper | Registry | Package name |
|---------|----------|--------------|
| Python | PyPI | `corporate-actions-registry` |
| JavaScript | npm | `corporate-actions-registry` |
| Rust | crates.io | `corporate-actions` |
| Go | pkg.go.dev | module path |

Publishing is a one-time setup followed by routine version bumps.

#### 7. Flip `--strict-isin` default

**Priority**: High
**Effort**: 1 hour
**Blocker**: Depends on Asset Identifiers reaching 500+ ISINs.

Once Asset Identifiers is complete for the instruments we cover, missing
ISINs should be errors, not warnings. This closes the temporary gap
documented in `docs/validation_layers.md`.

#### 8. Data hygiene: fuzzy dedup hardening

**Priority**: Medium
**Effort**: 3–5 days
**Blocker**: None.

The current fuzzy dedup key is `(isin, action_type, ex_date, ratio, amount)`.
This catches most duplicates but has edge cases:

- Amounts that differ due to split adjustment
- Actions with slightly different ex-dates due to timezone confusion

Extend the key with normalized comparisons.

### What v1.1.0 will not include

- International coverage
- Real-time updates
- Historical depth below 2000
- Non-USD dividends

---

## v1.1.1 — Hardening and licensing

**Status**: Shipped 2026-10-08.

**Theme**: The fetch pipeline was hardened against its two largest
failure modes, and the registry gained a documented legal position for
the data it redistributes.

### What shipped

**Fetch pipeline (Phase 2)**

- **SEC false-positive reduction.** `extract_new_symbol` now requires
  a filing anchor (`Item 5.03`, `5.07`, `7.01`, or `8.01`) within
  2000 characters of the match. Cover-page "Trading Symbol(s)" tables
  and notes issuances no longer produce false positives.
- **SEC archive loading.** `fetch_all_filings` merges
  `filings.recent` with every archive listed under `filings.files[]`,
  deduped by accession number. Coverage extends from ~2 years to the
  full filing history SEC publishes.
- **Yahoo `--ticker-offset`.** Enables chunked parallel fetches across
  CI runners.
- **`derive_impacts.py --check`.** Verify impacts in place without
  writing.
- **`--summary` alignment.** All four lookup examples behave identically.
- **Exit-code convention.** `docs/exit_codes.md` defines 0/1/2/3;
  `tests/test_exit_codes.py` enforces it across all tools.

**Licensing (Phase 3)**

- **`docs/redistribution.md`.** Four categories (`public-domain`,
  `facts-only`, `secondary-source`, `restricted`), the *Feist* legal
  theory, a takedown procedure, and jurisdictional limits.
- **`redistribution` field on every action.** Required by the schema,
  enforced by the validator, mapped by
  `tools/derive_redistribution.py`, preserved by all four wrappers.
- **Current distribution:** 234 `secondary-source`, 6 `facts-only`,
  0 `restricted`.

**Consolidation**

- `tools/check_mojibake.py` — UTF-8 corruption detector, wired into CI
- `tools/check_ecosystem_versions.py` + `tools/sibling_versions.json` —
  README ecosystem table gated against pinned sibling versions
- `tests/conftest.py` — canonical action factories shared across tests
- `docs/roadmap.md` (this file) — metrics verified against `facts.json`

### What did not ship

- 50-instrument expansion — moved to v1.2.0
- `--strict-isin` default flip — moved to v1.2.0
- MERGER extraction — moved to v1.2.0
- Ex-date trading-day check — moved to v1.2.0

## v1.2.0 — Expansion

**Status**: In progress.

**Target**: TBD. Depends on rate-limit strategy and corpus growth.

**Theme**: Extend the registry from 6 to a production-relevant
instrument count, and close the remaining semantic gaps.

### Success criteria

- [ ] Rate limiter on the Yahoo fetcher (token bucket, target 6 req/sec)
- [ ] 50-instrument fetch verified end-to-end
- [ ] 500-instrument fetch verified
- [ ] `--min-actions` floor becomes a rolling percentage of the last
      known count
- [ ] `--strict-isin` flipped to default
- [ ] SEC corpus grown to 20+ positives across sectors
- [ ] MERGER accepted by the validator (schema already reserves it)
- [ ] `REVERSE_SPLIT`, `SPINOFF`, and `DELISTING` each populated with at
      least one entry
- [ ] Ex-date trading-day check added as a validation layer
- [ ] `docs/action_types.md` fully specifies all eight types including
      the accepted-but-unpopulated three

### Items

#### 1. Rate limiter

Add a global token bucket to `fetch_yahoo_actions.py`. Without it, a
500-instrument fetch hits Yahoo's 429 limit around ticker 200.

#### 2. Instrument expansion

Fetch 50 instruments first. Verify the yield rate (actions per
instrument) against the six-instrument baseline. Then fetch the full
500.

#### 3. `--strict-isin` default flip

Every ISIN in the expanded dataset must resolve against the private
Asset Identifiers store. Turn the warning into an error.

#### 4. Corpus growth

Add at least 20 SEC corpus positives covering:
- Tech, finance, energy, healthcare
- Smaller issuers with less polished prose
- Multi-item 8-Ks

#### 5. Action-type population

- `MERGER`: accept in the validator, add at least one entry once the
  S-4 extraction pipeline exists
- `REVERSE_SPLIT`: `GE` (2021), `NBR` (2020), and others
- `SPINOFF`: `GE HealthCare` (2023), `Kellogg` (2023), and others
- `DELISTING`: `TWTR` (2022), and others; the SEC fetcher already
  extracts these

#### 6. Ex-date trading-day check

Add a validation layer that requires `ex_date` to be a trading day on
the referenced exchange's calendar. Requires the Exchange Calendar
snapshot; makes the dependency load-bearing rather than nominal.

### What v1.2.0 will not include

- Non-USD dividends
- International exchanges
- Real-time updates

---

## v2.0.0 — Real-time pipeline

**Status**: Planned.

**Target**: 6–12 months after v1.0.0.

**Theme**: Automated, near-real-time updates.

### Success criteria

- [ ] Daily automatic data refresh
- [ ] New actions appear within 24 hours of announcement
- [ ] Automated PR creation for new data
- [ ] QLF Orchestrator integration
- [ ] Historical depth to 1990 for major US indices

### Items

#### 1. Daily update pipeline

**Priority**: High
**Effort**: 3–4 weeks

The current `update-actions.yml` runs weekly. Increase to daily for the
fetchers that support it (Yahoo, SEC EDGAR when fixed).

Plan:

- Split `update-actions.yml` into daily and weekly jobs
- Daily: fetch, merge, open PR if new actions
- Weekly: full validation, tag if significant changes
- Automated PR cleanup (close stale PRs)

#### 2. Real-time notifications

**Priority**: Medium
**Effort**: 2 weeks

When a new action is added, notify subscribers.

Plan:

- Webhook fan-out (Slack, Discord, generic HTTP)
- RSS feed of recent additions
- Optional email digest

#### 3. QLF Orchestrator integration

**Priority**: High
**Effort**: 4–6 weeks

The QLF Orchestrator is the unified query layer across all four registries
(ISO 4217, Exchange Calendar, Asset Identifiers, Corporate Actions).

Plan:

- Define the query API
- Implement cross-registry joins
- Support "give me everything about instrument X"
- Publish as a library and a CLI

#### 4. Historical depth to 1990

**Priority**: Medium
**Effort**: 2–3 weeks

Currently most actions date from 2000 onward. Historical accuracy for the
1990s matters for long-horizon backtests.

Plan:

- Extend Yahoo fetch window
- Add SEC EDGAR historical filings (available back to 1993)
- Handle split-adjusted vs raw dividends more carefully for old data

### What v2.0.0 will not include

- Coverage of fixed income or derivatives
- Regulatory-grade audit trail
- Non-US real-time updates

---

## v3.0.0 — Global comprehensive

**Status**: Aspirational.

**Target**: 12–24 months after v1.0.0.

**Theme**: Comprehensive global coverage of equity corporate actions.

### Success criteria

- [ ] 50,000+ actions
- [ ] 5,000+ instruments
- [ ] 40+ exchanges covered
- [ ] All 8 action types populated for every major market
- [ ] Regulatory-grade audit trail
- [ ] Documented SLAs for data freshness

### Items

#### 1. Coverage expansion

**Priority**: High
**Effort**: Ongoing

Add every exchange in the Exchange Calendar Registry that publishes
corporate actions in machine-readable form.

#### 2. Regulatory-grade audit trail

**Priority**: Medium
**Effort**: 4–6 weeks

Every action should have:

- The primary source URL
- The date the source was accessed
- A cryptographic hash of the source content
- A sign-off for manual corrections

This enables the registry to be cited in regulated contexts.

#### 3. Fixed income corporate actions

**Priority**: Low
**Effort**: Unknown

Bond calls, coupon payments, and redemptions. This is a different data
model and may become a separate registry rather than extending this one.

#### 4. Derivatives corporate actions

**Priority**: Low
**Effort**: Unknown

Adjustments to options and futures contracts after splits or dividends.
Complex; may become a separate registry.

### What v3.0.0 will not include

- Anything that depends on commercial data vendors (Bloomberg, Refinitiv)
  unless the license situation changes

---

## What is not on the roadmap

Explicitly out of scope, so no one assumes otherwise:

- **Real-time tick data.** This registry handles events, not price data.
- **Execution services.** Orders are out of scope.
- **Portfolio management.** Position tracking is out of scope.
- **Tax accounting.** Cost basis calculations are out of scope.
- **Commercial licensing negotiation.** The registry stays free and open.
- **Bloomberg / Refinitiv integration.** Their licenses prohibit
  redistribution, which is incompatible with the registry's purpose.
- **Data on private companies.** Only publicly traded instruments.

---

## Dependencies and blockers

### External dependencies

| Dependency | Owner | Impact | Status |
|------------|-------|--------|--------|
| Asset Identifiers (500+ ISINs) | QuantOS | Blocks v1.1.0 expansion | In progress |
| SEC EDGAR endpoint | SEC | None currently; fetched via data.sec.gov | Working |
| ESMA FIRDS files | ESMA | Blocks v1.2.0 EU coverage | Available, not integrated |
| npm / PyPI accounts | External | Blocks wrapper publishing | Not set up |
| QLF Orchestrator design | QuantOS | Blocks v2.0.0 integration | Not started |

### Internal blockers

| Blocker | Impact | ETA |
|---------|--------|-----|
| Fuzzy dedup edge cases | Data hygiene | v1.1.0 |
| Cross-language consistency tests | Regression risk | v1.1.0 |
| CUSIP/SEDOL licensing | None currently; blocks Asset Identifiers | Indefinite |

### What could delay the roadmap

- SEC EDGAR endpoint changes again
- Yahoo Finance changes its API shape
- Asset Identifiers rebuild takes longer than expected
- International exchanges change their publication formats

The roadmap is designed to be resilient to individual blockers. Each version
has multiple items; if one is delayed, others proceed.

---

## Cross-registry coordination

The Corporate Actions Registry is one of four QuantOS registries. Its
roadmap is tied to theirs:

### Asset Identifiers

| Version | Coordination point |
|---------|--------------------|
| v1.0.0 | 50 ISINs available |
| v1.1.0 | 500+ ISINs → enables Corporate Actions v1.1.0 expansion |
| v1.2.0 | International instruments → enables Corporate Actions v1.2.0 |

### Exchange Calendar

| Version | Coordination point |
|---------|--------------------|
| v2.1.x | All currently-covered exchanges present |
| v2.2.0 | Additional exchanges as Corporate Actions expands |

### ISO 4217

| Version | Coordination point |
|---------|--------------------|
| v1.3.0 | All currencies used by dividends are covered |
| v1.4.0 | Historical currencies for pre-2000 dividends |

### QLF Orchestrator

The Orchestrator is the eventual unification layer. When it exists, the
Corporate Actions Registry will be one of its data sources. The design of
the Orchestrator's query API is a coordination point for v2.0.0.

---

## How to influence the roadmap

Three ways to influence priorities:

1. **Open an issue.** Describe what you need and why. Feature requests
   backed by a real use case carry more weight than generic "add more
   data" requests.

2. **Open a PR.** If you can implement a roadmap item, do so. Submit it
   with tests and documentation. Merged PRs accelerate the roadmap.

3. **Vote with usage.** Track which features are used in the wild. If a
   particular market is high-demand, that influences priority.

Priorities are revisited after every release. The v1.1.0 plan, for example,
may shift if a critical bug is found in v1.0.0.

---

## Timeline caveats

Every date in this document is a target, not a commitment. The registry is
maintained by a small team. Three honest caveats:

### 1. External dependencies can slip

If Asset Identifiers takes 3 months instead of 1 to reach 500 ISINs, the
v1.1.0 expansion slips by 2 months. Nothing in the Corporate Actions
Registry can accelerate that.

### 2. Data sources can break

The SEC EDGAR endpoint broke without warning. If Yahoo changes its API,
the pipeline breaks until a fix is shipped. Recovery time is 1–2 weeks in
the worst case.

### 3. Contributors matter more than plans

A roadmap item with a contributor who is actively working on it moves. An
item without one waits. If any v1.1.0 item matters to you, contribute or
sponsor it.

### 4. AI-assisted development is not free

Even with heavy automation, every change requires review, testing, and
documentation. A 5-line fix can take a day of careful work. This is by
design: financial data cannot ship with sloppy reviews.

---

## Release history

| Version | Date | Actions | Milestone |
|---------|------|---------|-----------|
| v1.0.0 | 2026-09-13 | 242 | Foundation |
| v1.0.1 | 2026-09-20 | 240 | Data correctness |
| v1.1.0 | Planned Q4 2026 | ~1,500 | US completeness |
| v1.2.0 | Planned Q1 2027 | ~5,000 | International |
| v2.0.0 | Planned mid 2027 | ~15,000 | Real-time |
| v3.0.0 | Planned 2028+ | 50,000+ | Comprehensive |

---

## See also

- `docs/action_types.md` — what each action type means
- `docs/data_sources.md` — current and planned sources
- `docs/validation_layers.md` — how data is validated
- `CHANGELOG.md` — version history
- `.github/ISSUE_TEMPLATE/` — how to propose changes
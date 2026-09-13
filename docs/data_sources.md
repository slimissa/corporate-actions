# Data Sources

The Corporate Actions Registry combines multiple data sources into a single
canonical `actions.json`. No single source provides complete, reliable, and
legally redistributable coverage, so the registry depends on a curated mix
of primary and secondary sources, each with different trade-offs.

This document specifies:

- Every source the registry draws from, current and planned
- What each source provides and what it does not
- Licensing and legal status of each source
- Rate limits and reliability characteristics
- How each source feeds the pipeline
- Known problems and their status

The `provenance` block on every action records the exact source URL used
for that entry. This document is the higher-level view: which sources
exist, why they were chosen, and what their limitations are.

---

## Table of contents

1. [Strategy](#strategy)
2. [Current sources](#current-sources)
3. [Supporting registries](#supporting-registries)
4. [Broken sources](#broken-sources)
5. [Planned sources](#planned-sources)
6. [Rejected sources](#rejected-sources)
7. [Licensing](#licensing)
8. [Reliability](#reliability)
9. [How to propose a new source](#how-to-propose-a-new-source)
10. [Version history](#version-history)

---

## Strategy

The registry operates on three principles:

### 1. Prefer primary sources

A primary source is the original publisher of the fact: the SEC filing, the
exchange announcement, the company press release. Secondary sources (Yahoo
Finance, Nasdaq summary pages) copy the fact and may introduce errors.

For every action accepted into the registry, the `provenance.source_url`
should point at a primary source whenever possible. Secondary sources are
acceptable as fallback when a primary source is not linkable.

### 2. Automate what can be automated, curate what cannot

The fetchers in `tools/` are the primary path for new data. They extract
splits and dividends from Yahoo Finance automatically. However:

- Coverage of mergers, spinoffs, and rights offerings is manual or planned
  but not yet automated.
- When a fetcher cannot retrieve data, a human adds the entry from a
  primary source.

The registry is designed for this hybrid approach. Nothing about the schema
or validation assumes machine extraction.

### 3. Fail loudly on unreliable sources

The current pipeline uses `run_update.sh` to refuse broken sources
(`--fetch-source sec` and `--fetch-source nasdaq` exit with an error). A
silent failure in a data pipeline is worse than a loud one: it produces a
partial registry that appears complete.

---

## Current sources

### Yahoo Finance (primary, working)

| Attribute | Value |
|-----------|-------|
| Provider | Yahoo |
| Access method | `yfinance` Python library |
| Endpoint | `https://query1.finance.yahoo.com/v8/finance/chart/{ticker}` |
| Data provided | Splits, dividends, historical prices |
| Action types covered | `SPLIT`, `REVERSE_SPLIT`, `DIVIDEND` |
| Coverage | US-listed equities with dividend/split history |
| Currency | In the instrument's trading currency (usually USD) |
| Fetcher | `tools/fetch_yahoo_actions.py` |
| Status | **Working** as of v1.0.0 |
| Rate limit | Session-based; `yfinance` handles cookies and CRUMB token |
| Authentication | None required |
| License | Data is redistributed as facts; the `yfinance` library is Apache 2.0 |

**What it provides**

- Dividend history back to the 1980s for many US tickers
- Split history with exact ratios and ex-dates
- Dividend ex-dates

**What it does not provide**

- Announcement dates (approximated as ex-dates)
- Record dates (not available)
- Payment dates (approximated as ex-dates)
- Dividends for non-US instruments
- Symbol changes, spinoffs, delistings, mergers

**How it is used**

`fetch_yahoo_actions.py` reads a list of `(isin, ticker, currency)` from an
identifiers file, queries Yahoo for each ticker, and produces corporate
action entries. The pipeline:

1. Fetches `query1.finance.yahoo.com` with `range=10y` and
   `events=div,splits`
2. Converts each dividend to a `DIVIDEND` action
3. Converts each split to a `SPLIT` or `REVERSE_SPLIT` action based on
   ratio orientation
4. Writes `yahoo_actions.json`

The output is then merged into `actions.json` with fuzzy dedup (see
`scripts/run_update.sh`).

**Known limitations**

- **Split-adjusted dividends.** `yfinance` returns dividend amounts that
  are split-adjusted. A dividend before a split is reported at the
  post-split equivalent amount. This is intentional for backtesting but is
  a known approximation.
- **No announcement dates.** The announcement date is set equal to the
  ex-date. This passes temporal validation but is not historically accurate.
- **Rate limits.** Heavy usage can trigger HTTP 429. The `yfinance` library
  mitigates this with a proper browser session, but aggressive refresh
  schedules can still hit limits.

---

### SEC EDGAR (planned, currently broken)

| Attribute | Value |
|-----------|-------|
| Provider | U.S. Securities and Exchange Commission |
| Access method | Full-text search API + 8-K filing downloads |
| Endpoint | `https://efts.sec.gov/LATEST/search-index` |
| Data provided | 8-K filings containing corporate action announcements |
| Action types covered | `SPLIT`, `DIVIDEND`, `SPECIAL_DIVIDEND`, `SYMBOL_CHANGE`, `SPINOFF`, `DELISTING`, `MERGER` |
| Coverage | All US-listed issuers filing 8-K |
| Fetcher | `tools/fetch_sec_edgar_actions.py` |
| Status | **Broken** as of v1.0.0 |
| Rate limit | 10 requests/second, User-Agent required |
| Authentication | None, but User-Agent header is enforced |
| License | Public domain |

**Why it matters**

SEC EDGAR is the only free source that contains filings for every action type,
including ones Yahoo Finance does not expose (mergers, spinoffs, delistings).
For the registry to reach full coverage, SEC EDGAR integration is required.

**Why it is broken**

The full-text search endpoint used by the fetcher was retired by the SEC in
2024. The endpoint returns HTTP 500 for the parameter combination the
fetcher uses. The correct replacement endpoint is not documented and may
require authenticated access via `data.sec.gov`.

**Recovery plan (v1.1.0)**

Three options, in order of preference:

1. **Use `data.sec.gov` submissions API.** The SEC publishes a structured
   JSON index of every filing per company. Combine with full-text search
   through the standard UI. This is the preferred path.
2. **Scrape `browse-edgar`.** The legacy filing listing endpoint still
   works. Download 8-K filings and parse the text locally.
3. **Use a third-party mirror.** Sources like `sec-api.io` offer
   re-hosted EDGAR data at commercial cost. Not preferred, but viable
   if the SEC endpoints remain unstable.

See `tools/fetch_sec_edgar_actions.py` for the current implementation.

---

### Nasdaq dividends API (broken, removal candidate)

| Attribute | Value |
|-----------|-------|
| Provider | Nasdaq |
| Access method | REST API |
| Endpoint | `https://api.nasdaq.com/api/quote/{ticker}/dividends` |
| Data provided | Dividend history per ticker |
| Action types covered | `DIVIDEND` |
| Coverage | US-listed equities |
| Fetcher | `tools/fetch_dividends_nasdaq.py` |
| Status | **Broken** as of v1.0.0 |
| Rate limit | Not documented; aggressive blocking |
| Authentication | None, but browser-like headers required |
| License | Unclear; access restrictions suggest restricted redistribution |

**Why it is broken**

The API times out from non-US IPs and from CI runners. It also requires
browser-like headers (`Origin`, `Referer`) that are not sufficient on their
own. Nasdaq has tightened access over time.

**Removal candidate**

The Nasdaq fetcher overlaps almost entirely with Yahoo Finance for the
dividend data it provides. Since Yahoo works reliably via `yfinance`, the
Nasdaq fetcher adds little value and adds a broken code path to maintain.

**Recommendation**: remove `fetch_dividends_nasdaq.py` in v1.1.0 unless a
compelling use case emerges (e.g. Yahoo coverage gaps for specific tickers).
Tracked in the roadmap.

---

## Supporting registries

The Corporate Actions Registry does not exist in isolation. Three sibling
registries from the QuantOS Ledger Foundation provide cross-reference data
that validates every corporate action entry.

### Asset Identifiers Registry

| Attribute | Value |
|-----------|-------|
| Purpose | Map instruments to ISIN, CUSIP, FIGI, LEI, ticker |
| Repository | `https://github.com/slimissa/asset-identifiers` |
| Version used | Pinned to a specific local path or `$LAS_DATA_HOME` |
| Load | `load_identifiers_registry()` in `tools/validate.py` |
| Coverage (as of v1.0.0) | ~50 ISINs in the public subset, up to 515 in the private store |

**How it is used**

Every action's `isin` is validated against the active set of ISINs. If the
ISIN is not present, the validator emits a warning (not an error, since the
registry is being rebuilt). Use `--strict-isin` to make it an error when
the coverage is complete.

**Coverage caveat**

The public repository ships no identifier data (ADR 0001). Data lives at
`$LAS_DATA_HOME/identifiers.json` in a private store. The CI uses the
repo-local fixtures in `tests/fixtures/identifiers.json`.

---

### ISO 4217 Registry

| Attribute | Value |
|-----------|-------|
| Purpose | Validate currency codes in dividend entries |
| Repository | `https://github.com/slimissa/iso4217` |
| Version used | v1.3.0 |
| Load | `load_iso4217_registry()` in `tools/validate.py` |
| Coverage | 167 active currencies, 135 withdrawn |

**How it is used**

Every `currency` field on a `DIVIDEND` or `SPECIAL_DIVIDEND` is checked
against the active currency set. Withdrawn currencies are rejected.
Non-ISO codes (crypto, commodities) are not accepted.

---

### Exchange Calendar Registry

| Attribute | Value |
|-----------|-------|
| Purpose | Validate exchange MIC codes and provide trading-hours context |
| Repository | `https://github.com/slimissa/exchange-calendar` |
| Version used | v2.1.2 |
| Load | `load_exchange_calendar_registry()` in `tools/validate.py` |
| Coverage | 74 exchanges across 6 continents |

**How it is used**

If an action carries an `exchange` field (currently optional), the MIC is
validated against the registry. The current `actions.json` does not use
this field, but the validator supports it for future expansion.

---

## Broken sources

### Summary table

| Source | Status | Reason | Recovery plan |
|--------|--------|--------|---------------|
| SEC EDGAR | Broken | Endpoint returns HTTP 500 | Use `data.sec.gov` submissions API (v1.1.0) |
| Nasdaq | Broken | API times out, blocks non-US IPs | Remove, Yahoo covers same data (v1.1.0) |

Both broken sources are refused by `scripts/run_update.sh` with a clear
error message. This is deliberate: a silent skip would hide the problem.

---

## Planned sources

Sources under consideration for v1.1.0 and beyond. None are implemented yet.

### ESMA FIRDS (EU)

| Attribute | Value |
|-----------|-------|
| Provider | European Securities and Markets Authority |
| Data provided | EU instrument reference data including ISIN, MIC, currency |
| Action types covered | Instrument metadata (not corporate actions directly) |
| License | Open data |
| Status | Planned for v1.2.0 |

**Use case**: fill the international instrument gap. FIRDS does not publish
corporate actions, but its instrument metadata allows cross-referencing EU
instruments for use with other European corporate action sources.

---

### JPX (Japan)

| Attribute | Value |
|-----------|-------|
| Provider | Japan Exchange Group |
| Data provided | Corporate action announcements, dividend schedules |
| Action types covered | `SPLIT`, `DIVIDEND`, `MERGER` |
| License | Public announcements |
| Status | Planned for v1.2.0 |

**Use case**: Japan is a major market with no coverage today.

---

### HKEX (Hong Kong)

| Attribute | Value |
|-----------|-------|
| Provider | Hong Kong Exchanges and Clearing |
| Data provided | Corporate action announcements |
| Action types covered | `SPLIT`, `DIVIDEND`, `RIGHTS`, `MERGER` |
| License | Public announcements |
| Status | Planned for v1.2.0 |

---

### LSE / Companies House (UK)

| Attribute | Value |
|-----------|-------|
| Provider | London Stock Exchange, UK Companies House |
| Data provided | Corporate actions, incorporation events |
| License | Mixed |
| Status | Planned for v1.2.0 |

---

### GLEIF (LEI verification)

| Attribute | Value |
|-----------|-------|
| Provider | Global Legal Entity Identifier Foundation |
| Data provided | LEI, corporate hierarchy |
| License | Open data |
| Status | Optional verification |

**Use case**: verify that a `MERGER` is between the correct legal entities
once MERGER support lands.

---

## Rejected sources

Sources that were evaluated and declined. Documented so future contributors
do not re-investigate.

### Bloomberg Terminal

- **Reason**: Commercial license. Redistribution prohibited.
- **Could be used as**: Verification source only, if a maintainer has access.

### Refinitiv Eikon

- **Reason**: Commercial license. Redistribution prohibited.
- **Could be used as**: Verification source only.

### CUSIP Global Services

- **Reason**: Commercial license. Redistribution prohibited. Same blocker
  that stops Asset Identifiers from publishing full ISIN/CUSIP coverage.

### Wikipedia

- **Reason**: Unreliable. Historical corporate action lists are often
  incomplete, out of date, or incorrect. Not suitable as a primary or
  verification source.
- **Could be used as**: Pointer to primary sources only.

### Yahoo Finance HTML pages

- **Reason**: Scraping the HTML site is fragile and violates Yahoo's terms.
  The `yfinance` library accesses a documented JSON endpoint instead, which
  is the accepted method.
- **Use `yfinance` instead.**

---

## Licensing

### The general principle

Facts are not copyrightable. The date of an Apple dividend is a fact. The
list of a company's stock splits is a fact. In most jurisdictions, factual
data is not protected by copyright.

However, the *compilation* of facts can be protected in some jurisdictions
(notably the EU's database right), and the terms of service under which
data is provided often restrict redistribution regardless of copyright.

### What this registry relies on

1. **Yahoo Finance data via `yfinance`**: The `yfinance` library is Apache
   2.0. Data pulled from Yahoo is factual. The registry republishes the
   facts it extracts (split dates, dividend amounts) with a source URL
   pointing back to Yahoo. This is standard practice for financial data
   libraries.

2. **SEC EDGAR**: US government works are in the public domain under
   17 U.S.C. § 105. No licensing concern.

3. **Exchange announcements**: Press releases and regulatory
   announcements are made for public consumption. Their factual content is
   not copyrightable.

4. **Asset Identifiers, ISO 4217, Exchange Calendar data**: Each of those
   projects has its own licensing model. See their respective READMEs.

### What this registry does NOT do

- It does not redistribute Yahoo Finance's raw price data.
- It does not redistribute Nasdaq's API responses.
- It does not redistribute Bloomberg's or Refinitiv's data.
- It does not claim ownership of the facts it records.

### If you redistribute this registry

You may redistribute `actions.json` and the wrappers under Apache 2.0.
The factual data is provided as-is, with source URLs preserved in each
entry's `provenance` block. Attribution is not required by the license,
but it is good practice and helps traceability.

---

## Reliability

### How reliability is measured

Three axes:

1. **Endpoint availability.** Does the source respond to requests?
   `check-sources.yml` tests this weekly.
2. **Data freshness.** How quickly does the source reflect new events?
   Yahoo Finance updates dividends within 24 hours of ex-date; SEC EDGAR
   filings are searchable within minutes of submission.
3. **Data completeness.** Does the source cover what it claims to cover?
   Yahoo has full history for US equities but not international.

### Current reliability summary

| Source | Availability | Freshness | Completeness |
|--------|--------------|-----------|--------------|
| Yahoo Finance | High | 24 hours | US only |
| SEC EDGAR | Broken | minutes | US, all action types |
| Nasdaq | Broken | hours | US dividends |
| ESMA FIRDS | Not integrated | daily | EU |
| JPX | Not integrated | 24 hours | Japan |
| HKEX | Not integrated | 24 hours | Hong Kong |

### Monitoring

`.github/workflows/check-sources.yml` runs weekly on Monday at 06:00 UTC.
For each source, it:

1. Makes a small test request.
2. Confirms the response parses correctly.
3. Confirms the expected shape (for example, `yfinance` returns both
   dividends and splits for a known ticker).
4. Opens a GitHub issue if any source fails.
5. Closes the issue automatically once all sources recover.

This workflow is the single source of truth for source health.

---

## How to propose a new source

Use the `.github/ISSUE_TEMPLATE/data_source.md` template. The template
requires:

1. A working URL to the source's documentation
2. A statement of the license status
3. Coverage claims compared to current gaps
4. Effort estimate
5. Risk assessment
6. Integration plan

Do not open a PR for a new source without an accepted issue first. Source
integration affects CI, licensing, and the maintenance surface, and those
are reviewed at the issue stage.

### Evaluation criteria

A source will be accepted only if all of the following hold:

- **Legally usable.** License permits redistribution, or the source can be
  used as a verification-only check.
- **Reliable.** Uptime and stability sufficient to be a dependency.
- **Technically integrable.** Interface is accessible with standard tools
  (no headless browser for every fetch, no CAPTCHA solving).
- **Non-redundant.** Does not duplicate a source that is already working
  and stable.
- **Documented.** Public documentation exists for the interface.

### Evaluation criteria for rejection

- **Restricted license.** No redistribution permitted.
- **Unstable interface.** Frequent breaking changes without notice.
- **Aggressive access controls.** IP blocking, CAPTCHA, or commercial
  paywall.
- **Redundant.** A working source already provides the same data.
- **Unreliable data.** History of incorrect or incomplete entries.

---

## Version history

### v1.0.0

- Yahoo Finance integration via `yfinance` (working)
- SEC EDGAR integration attempted (broken)
- Nasdaq integration attempted (broken)
- Cross-reference with Asset Identifiers, ISO 4217, Exchange Calendar
- Weekly source health monitoring (`check-sources.yml`)
- Weekly automated update workflow (`update-actions.yml`)

### v1.1.0 (planned)

- Fix SEC EDGAR via `data.sec.gov` submissions API
- Remove Nasdaq fetcher (redundant with Yahoo)
- Add `MERGER` extraction from SEC S-4 filings
- Expand to 50 tickers

### v1.2.0 (planned)

- ESMA FIRDS integration for EU instrument metadata
- JPX integration
- HKEX integration
- LSE / Companies House integration
- Cross-registry coordination with Asset Identifiers

### v2.0.0 (planned)

- Real-time update pipeline (daily refetch)
- Automated PR creation for new actions
- Non-US currency support in dividends

---

## See also

- `docs/action_types.md` — what each action type means
- `docs/validation_layers.md` — how data is validated
- `docs/roadmap.md` — long-term plan
- `tools/fetch_yahoo_actions.py` — the working fetcher
- `tools/fetch_sec_edgar_actions.py` — the broken fetcher (needs repair)
- `tools/fetch_dividends_nasdaq.py` — the redundant fetcher (removal candidate)
- `.github/ISSUE_TEMPLATE/data_source.md` — how to propose new sources
- `.github/workflows/check-sources.yml` — source health monitoring
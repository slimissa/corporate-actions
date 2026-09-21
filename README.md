```markdown
# Corporate Actions Registry

[![Validate](https://github.com/slimissa/corporate-actions/actions/workflows/validate.yml/badge.svg)](https://github.com/slimissa/corporate-actions/actions/workflows/validate.yml)
[![Check Sources](https://github.com/slimissa/corporate-actions/actions/workflows/check-sources.yml/badge.svg)](https://github.com/slimissa/corporate-actions/actions/workflows/check-sources.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)
[![Registry](https://img.shields.io/badge/registry-v1.1.0-orange.svg)](./CHANGELOG.md)
[![Actions](https://img.shields.io/badge/actions-240-green.svg)](./actions.json)
[![Languages](https://img.shields.io/badge/wrappers-4-purple.svg)](./wrappers/)
[![Tests](https://img.shields.io/badge/tests-890-success.svg)](./tests/)

**A canonical, versioned, machine-readable registry of corporate actions.**
One JSON file as the source of truth. Four language wrappers. Seven-layer
validation. Zero runtime dependencies.

---

## Table of contents

- [What this is](#what-this-is)
- [Current status](#current-status)
- [What's new in v1.1.0](#whats-new-in-v110)
- [Quick start](#quick-start)
- [Why this exists](#why-this-exists)
- [The 8 action types](#the-8-action-types)
- [Validation](#validation)
- [Data sources](#data-sources)
- [Wrapper contract](#wrapper-contract)
- [Repository structure](#repository-structure)
- [Development](#development)
- [Known limitations](#known-limitations)
- [Roadmap](#roadmap)
- [Versioning](#versioning)
- [Ecosystem](#ecosystem)
- [License](#license)

---

## What this is

Corporate actions are the events that change what a financial instrument
is, how much of it exists, and what it is worth: stock splits, dividends,
mergers, spinoffs, symbol changes, and delistings.

Every trading system, backtest framework, and portfolio tool needs this
data. Most projects hand-roll their own list, which becomes stale,
inconsistent, or silently wrong. A missed 10-for-1 split makes a 700%
gain look like a 20% loss. A mislabeled dividend corrupts total-return
calculations.

This registry provides one versioned, schema-validated JSON file that any
tool can depend on. It is language-agnostic by design.

```json
{
  "isin": "US67066G1040",
  "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
  "action_type": "SPLIT",
  "ratio": "10:1",
  "dates": {
    "announcement": "2024-05-22",
    "ex_date": "2024-06-10",
    "record_date": "2024-06-07",
    "effective_date": "2024-06-10"
  },
  "status": "COMPLETED",
  "provenance": {
    "source": "NVIDIA Corp press release",
    "source_url": "https://nvidianews.nvidia.com/news/nvidia-announces-ten-for-one-forward-stock-split"
  },
  "impact": {
    "price_multiplier": 0.1,
    "share_multiplier": 10.0,
    "cash_adjustment": 0.0
  }
}
```

---

## Current status

**Version**: v1.1.0
**Actions**: 240
**Instruments**: 6 US large caps
**Action types populated**: 4 of 8
**Wrappers**: Python, JavaScript, Go, Rust
**Total tests**:
890 root (network deselected) + 117 Python + 99 JavaScript + 76 Go + 96 Rust + 1 Rust doctest

### Coverage

| Category | Count | Notes |
|----------|-------|-------|
| Actions | 240 | Splits and dividends dominate |
| Instruments | 6 | AAPL, MSFT, GOOGL, AMZN, META, NVDA |
| Action types populated | 4 of 8 | `SPLIT`, `DIVIDEND`, `SPECIAL_DIVIDEND`, `SYMBOL_CHANGE` |
| Action types reserved | 4 of 8 | `REVERSE_SPLIT`, `SPINOFF`, `DELISTING`, `MERGER` |
| Currencies | 1 | USD only |
| Exchanges | 1 | US equities (XNAS, XNYS) |
| Historical depth | 2000+ | Earliest action in the registry is from 2000 |

### What works, what does not

| Component | Status |
|-----------|--------|
| Yahoo Finance fetcher | ✅ Working |
| SEC EDGAR fetcher | ✅ Working (narrow scope: SYMBOL_CHANGE, DELISTING) |
| Validator | ✅ All 7 layers |
| Python wrapper | ✅ 117 tests |
| JavaScript wrapper | ✅ 99 tests |
| Go wrapper | ✅ 76 tests |
| Rust wrapper | ✅ 96 tests + 1 doctest |
| Reject list | ✅ Enforced in merge step |
| Doc-fact consistency | ✅ CI-gated |
| Build artifact consistency | ✅ CI-gated |
| Lint | ✅ Ruff, pyflakes-only |
| CI workflows | ✅ 3 green |

See [Known limitations](#known-limitations) for the full list.

---

## What's new in v1.1.0

The four wrappers now share a written contract, and every public method
is specified in [`docs/wrapper_contract.md`](./docs/wrapper_contract.md).
The headline additions:

- **`by_ticker(ticker, exchange)`** on all four wrappers. Resolves a
  ticker and exchange to an ISIN via the Asset Identifiers registry,
  then returns the same list as `by_isin`. Ticker and exchange are
  uppercased before lookup; an unknown pair returns an empty list.
- **Exported constants**: `DEFAULT_DATE_FIELD` (`"ex_date"`) and
  `VALID_DATE_FIELDS` (the closed set of four date fields).
- **Duplicate `action_id` is a load-time error** in all four wrappers.
  Previously the last-inserted entry silently won.
- **An action with neither `isin` nor `action_id` is a load-time error.**
  Previously such entries were accepted.
- **Consistent copy semantics**: every lookup returns a fresh copy, so a
  caller cannot corrupt the registry's internal state.
- **A durable reject list** (`_removed_actions.json`) so the merge step
  cannot re-introduce a deliberately removed action.
- **CI enforcement** of doc-fact consistency, build-artifact drift, and
  lint.

The registry data itself is unchanged: 240 actions across 6 instruments.

See [`CHANGELOG.md`](./CHANGELOG.md) for the full list.

---

## Quick start

### Use the data directly

Download `actions.json` and read it in any language:

```bash
curl -O https://raw.githubusercontent.com/slimissa/corporate-actions/main/actions.json
```

```python
import json

with open("actions.json") as f:
    data = json.load(f)

for action in data["actions"]:
    print(action["action_type"], action["isin"], action["dates"]["ex_date"])
```

No dependency on this project's code. The JSON is the contract.

### Use a wrapper

Wrappers are **source-only until v3.0.0**. Install from the repository:

**Python**

```bash
git clone https://github.com/slimissa/corporate-actions.git
cd corporate-actions/wrappers/python
pip install -e .
```

```python
from corporate_actions_registry import CorporateActionsRegistry

registry = CorporateActionsRegistry("actions.json")

# All actions for Apple by ISIN
for action in registry.by_isin("US0378331005"):
    print(action.action_type, action.dates.ex_date)

# All actions for a ticker on an exchange
aapl_on_nasdaq = registry.by_ticker("AAPL", "XNAS")

# All splits in the registry
splits = registry.by_action_type("SPLIT")

# A specific action
action = registry.by_action_id("US67066G1040-SPLIT-2024-06-10-10-1")
```

**JavaScript**

```bash
git clone https://github.com/slimissa/corporate-actions.git
cd corporate-actions/wrappers/javascript
npm install
```

```javascript
const { CorporateActionsRegistry } = require('./wrappers/javascript/src');

const registry = new CorporateActionsRegistry('actions.json');
const aapl = registry.byIsin('US0378331005');
const aaplOnNasdaq = registry.byTicker('AAPL', 'XNAS');
const splits = registry.byActionType('SPLIT');
```

**Go**

```bash
go get github.com/slimissa/corporate-actions/wrappers/go@v1.1.0
```

```go
import registry "github.com/slimissa/corporate-actions/wrappers/go/registry"

r, _ := registry.LoadRegistry("actions.json")
aapl := r.ByISIN("US0378331005")
splits := r.ByActionType("SPLIT")

aaplOnNasdaq, err := r.ByTicker("AAPL", "XNAS", "")
if err != nil {
    panic(err)
}
```

**Rust**

```bash
git clone https://github.com/slimissa/corporate-actions.git
cd corporate-actions/wrappers/rust
cargo build
```

```rust
use corporate_actions_registry::Registry;

let registry = Registry::load_from_file("actions.json")?;
let aapl = registry.by_isin("US0378331005");
let splits = registry.by_action_type("SPLIT");

let aapl_on_nasdaq = registry.by_ticker("AAPL", "XNAS", None)?;
```

### Run the examples

The `examples/` directory has a working CLI example for each language
plus one that demonstrates backtest price adjustment:

```bash
# Python
python examples/python_lookup.py --isin US0378331005

# JavaScript
node examples/javascript_lookup.js --action-type SPLIT

# Go
cd wrappers/go && go run ../../examples/go_lookup.go ../../actions.json

# Rust
cd wrappers/rust && cargo run --example rust_lookup -- ../../actions.json

# Backtest adjustment demo (shows why this registry matters)
python examples/backtest_adjustment.py --ticker NVDA --isin US67066G1040 \
  --start 2024-01-02 --end 2024-07-01
```

The backtest example prints three P&L numbers: raw, split-adjusted, and
total-return. For an instrument with a split in the holding period, the
raw number is wrong and the adjusted numbers are correct. This is the
concrete value of the registry.

---

## Why this exists

Consider a backtest of NVDA held from January 2024 to July 2024. NVDA
executed a 10-for-1 split on 2024-06-10.

| Method | Result | Correct? |
|--------|--------|----------|
| Raw prices, no adjustment | n/a — not available from yfinance | ❌ Wrong |
| Split-adjusted (yfinance Close) | +156% | ✅ |
| Split + dividend adjusted (yfinance Adj Close) | +157% | ✅ |

Without the registry, a backtest framework would use the raw price
series and produce a nonsense result. With the registry, the framework
can query for actions in the holding period and restate historical
prices.

The same problem applies to:

- **Dividends** affecting total-return calculations
- **Spinoffs** affecting cost basis allocation
- **Symbol changes** breaking joins keyed on ticker
- **Mergers** changing what a position represents
- **Delistings** stranding positions

Every one of these is a class of error that a well-designed data layer
can prevent. The registry is that data layer.

---

## The 8 action types

The registry supports eight corporate action types. Four are populated
in v1.1.0 (`SPLIT`, `DIVIDEND`, `SPECIAL_DIVIDEND`, `SYMBOL_CHANGE`);
four are reserved (`REVERSE_SPLIT`, `SPINOFF`, `DELISTING`, `MERGER`).

| Type | Status | Meaning |
|------|--------|---------|
| `SPLIT` | ✅ Populated | Forward stock split |
| `REVERSE_SPLIT` | Reserved | Reverse stock split |
| `DIVIDEND` | ✅ Populated | Regular cash dividend |
| `SPECIAL_DIVIDEND` | ✅ Populated | One-time cash dividend |
| `SYMBOL_CHANGE` | ✅ Populated | Ticker change (ISIN unchanged) |
| `SPINOFF` | Reserved | Subsidiary separation |
| `DELISTING` | Reserved | Removal from exchange |
| `MERGER` | Reserved | Acquisition (rejected by validator in v1.1.0) |

See [`docs/action_types.md`](./docs/action_types.md) for the full
semantics of each type, including date ordering rules, required fields,
and impact derivation.

---

## Validation

Every action in `actions.json` passes seven independent validation
layers:

| Layer | Catches |
|-------|---------|
| 1. Schema | Structural errors, missing fields, wrong types |
| 2. Temporal | Invalid date ordering per action type |
| 3. Arithmetic | Invalid ratios, negative amounts |
| 4. Cross-reference | Unknown ISINs, currencies, or exchange MICs |
| 5. Uniqueness | Duplicate `action_id` values |
| 6. Provenance | Missing or malformed source URLs |
| 7. Coverage | Too few actions for the current milestone |

Run the validator:

```bash
python3 tools/validate.py \
  --actions actions.json \
  --schema schema.json \
  --identifiers tests/fixtures/identifiers.json \
  --iso4217 tests/fixtures/iso4217.json \
  --exchange-calendar tests/fixtures/exchange_calendar.json
```

Expected output:

```
Loading Asset Identifiers registry...
  Loaded 10 ISINs
Loading ISO 4217 registry...
  Loaded 167 active currencies
Loading Exchange Calendar registry...
  Loaded 74 exchange MICs

Validating 240 actions...

OK: 240 actions validated successfully.
Cross-reference: 240 actions checked, 0 with unknown ISIN
All layers passed: schema, temporal, arithmetic, cross-reference, uniqueness, provenance, coverage
```

See [`docs/validation_layers.md`](./docs/validation_layers.md) for the
exact rules each layer enforces.

---

## Data sources

| Source | Status | Used for |
|--------|--------|----------|
| Yahoo Finance (via `yfinance`) | ✅ Working | US equity splits and dividends |
| SEC EDGAR | ✅ Working (narrow scope) | Symbol changes and delistings since 2019 |

Every action in the registry has a `provenance.source_url` pointing at a
primary source (SEC filing, exchange announcement, or company press
release) or a clearly labeled secondary source (Yahoo Finance).

See [`docs/data_sources.md`](./docs/data_sources.md) for the full
licensing and reliability analysis of each source, including sources
considered and rejected.

### Reject list

`_removed_actions.json` records every action that has been deliberately
removed from `actions.json`. The merge step
(`tools/merge_fetched.py`) refuses to re-add any action matching a
reject-list entry, matched by
`(isin, action_type_family, ex_date, amount)`.

The reject list exists because the fuzzy-dedup key alone cannot
distinguish a corrected entry from a re-fetched wrong one. A dividend
removed because its ex-date was wrong has a different fuzzy key from the
corrected entry, so without the reject list, the fetcher would re-add it
on every run.

### Source health monitoring

`.github/workflows/check-sources.yml` runs weekly and probes each source
with a real request. If a source fails, a GitHub issue is opened
automatically. When the source recovers, the issue is closed.

---

## Wrapper contract

The four wrappers implement one written contract:
[`docs/wrapper_contract.md`](./docs/wrapper_contract.md).

It specifies, for every public method:

- The exact signature in each language
- The return type (value vs. reference, and copy semantics)
- The error type and message format
- The sort order for range queries
- The behaviour on missing fields
- The behaviour on malformed input

The contract is the source of truth. When a wrapper disagrees with the
contract, the wrapper is wrong. When the contract disagrees with the
tests, the tests win and the contract is updated.

A shared fixture at `tests/wrapper_contract.json` is read by all four
wrapper test suites. Adding a language does not require editing the
fixture. Adding a contract rule does.

---

## Repository structure

```
corporate-actions/
├── actions.json                 # The registry (240 actions)
├── schema.json                  # JSON Schema
├── _removed_actions.json        # Durable reject list for merges
├── README.md                    # This file
├── CONTRIBUTING.md              # Code contribution guide
├── CHANGELOG.md                 # Version history
├── LICENSE                      # Apache 2.0
├── pyproject.toml               # Ruff config
├── requirements.txt             # Runtime dependencies
├── requirements-dev.txt         # Test dependencies
│
├── docs/                        # Long-form documentation
│   ├── action_types.md          # Semantics of the 8 action types
│   ├── validation_layers.md     # The 7 validation layers
│   ├── data_sources.md          # Source licensing and reliability
│   ├── wrapper_contract.md      # The wrapper contract
│   ├── roadmap.md               # v1.0.0 → v3.0.0
│   ├── contributing.md          # Documentation contribution guide
│   └── facts.json               # Numeric facts cited across docs
│
├── tools/                       # Python utilities
│   ├── validate.py              # 7-layer validator
│   ├── derive_impacts.py        # Compute multipliers
│   ├── build.py                 # Distribution artifacts
│   ├── merge_fetched.py         # Merge fetched actions
│   ├── update_facts.py          # Regenerate docs/facts.json
│   ├── check_doc_facts.py       # Doc-vs-fact checker
│   ├── rewrite_action_ids.py    # One-shot: canonicalize action_ids
│   └── fetch_*.py               # Data fetchers
│
├── scripts/                     # Operational scripts
│   ├── run_update.sh            # Full pipeline
│   ├── fix_duplicates.py        # One-shot: remove known duplicates
│   ├── notify_on_change.py      # Change detection
│   └── README.md
│
├── wrappers/                    # Language bindings
│   ├── python/                  # 117 tests
│   ├── javascript/              # 99 tests
│   ├── go/                      # 76 tests
│   └── rust/                    # 96 tests + 1 doctest
│
├── examples/                    # Usage examples
├── tests/                       # Root test suite
│   ├── fixtures/
│   │   └── identifiers.json     # Synthetic (TESTA..TESTJ)
│   └── wrapper_contract.json    # Shared wrapper fixture
└── .github/                     # CI and templates
```

---

## Development

### Setup

```bash
git clone https://github.com/slimissa/corporate-actions.git
cd corporate-actions

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

### Run tests

```bash
# Root suite (Python)
pytest tests/ -v -m "not network"

# Python wrapper
cd wrappers/python && pytest tests -v && cd -

# JavaScript wrapper
cd wrappers/javascript && npm test && cd -

# Go wrapper
cd wrappers/go && go test ./registry -v && cd -

# Rust wrapper
cd wrappers/rust && cargo test && cd -

# Doc-fact consistency
python3 tools/check_doc_facts.py
python3 tools/update_facts.py --check

# Lint
python3 -m ruff check tests/ tools/ examples/ scripts/
```

All test suites are also run in CI on every push and PR.

### Run the update pipeline

```bash
# Dry-run: fetch, merge, validate, no commit, no mutation
scripts/run_update.sh --fetch-source yahoo --dry-run --verbose

# Fast check: no fetch, no tests, no build
scripts/run_update.sh --skip-fetch --skip-tests --skip-build
```

See [`scripts/README.md`](./scripts/README.md) for all flags.

### Adding a new action

1. Edit `actions.json` and add the action.
2. Run `python3 tools/derive_impacts.py --actions actions.json`.
3. Run `python3 tools/validate.py ...` and resolve any errors.
4. Run `python3 -m pytest tests/` and resolve any failures.
5. Submit a PR with the source URL cited.

Every action needs a `provenance.source_url` pointing at a primary
source (SEC filing, exchange announcement, or company press release).
See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for the full guide.

### Removing an action

Add a matching entry to `_removed_actions.json` before removing the
action from `actions.json`. Otherwise the next fetcher run will re-add
it. `scripts/fix_duplicates.py` does this automatically.

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) § 10.9 for the format.

---

## Known limitations

The following are documented, deliberate limitations of v1.1.0. They are
tracked in [`docs/roadmap.md`](./docs/roadmap.md) for future versions.

### Data coverage

- **6 instruments.** The registry covers a small set of US large caps.
  Expansion to 50+ instruments is planned for v1.2.0 and depends on the
  Asset Identifiers registry reaching 500+ ISINs.
- **US only.** No international coverage. Expansion to EU, JP, HK, and
  UK is planned for v1.3.0.
- **USD only.** All current instruments trade in USD. Non-USD dividend
  amounts and currency conversion are planned for v1.3.0.
- **Historical depth.** Earliest action in the registry is from 2000.
  Extending coverage further back is planned for v2.0.0.

### Action types

- **No `MERGER` support.** Schema reserves the type, but the validator
  rejects any `MERGER` entry until the extraction pipeline supports it.
  Planned for v1.2.0.
- **No `SPINOFF` or `DELISTING` entries.** Schema reserves both types.
  No entries exist yet because the extraction pipeline does not cover
  them.
- **Announcement dates are approximated for Yahoo-sourced dividends.**
  The Yahoo API does not expose the announcement date, so it is set
  equal to the ex-date. This passes temporal validation but is not
  historically accurate.
- **Dividend amounts are split-adjusted as provided by yfinance.** A
  dividend paid before a split is reported at the post-split equivalent
  amount. Intentional for backtesting, documented as an approximation.

### Sources

- **SEC EDGAR fetcher is narrow.** Scope is limited to `SYMBOL_CHANGE`
  and `DELISTING` and to the last ~1,000 filings per company. Older
  filings live in archive files that the fetcher does not yet read.
  Planned for v1.2.0.
- **SEC `SYMBOL_CHANGE_TRIGGERS` blocklist can drop real tickers.**
  `COMMON_ENGLISH_WORDS` contains `AN`, `DO`, `GO`, `HE`, `IT`, `ME`,
  `ON`, `SO`, `UP`, `WE` — all real US-listed tickers. A symbol change
  to any of these is silently dropped. Fix planned for v1.2.0.

### Distribution

- **Wrappers are source-only until v3.0.0.** They are not published to
  PyPI, npm, or crates.io. Install from the repository:
  `pip install -e wrappers/python`, `npm install ./wrappers/javascript`,
  or `cargo add --path ./wrappers/rust`. The Go module is available via
  its tag because the Go proxy resolves modules from git.

### Integration

- **Cross-reference uses a partial Asset Identifiers subset.** Missing
  ISINs are warnings by default. Use `--strict-isin` to promote them to
  errors once Asset Identifiers reaches full coverage.

---

## Roadmap

| Version | Theme | Target |
|---------|-------|--------|
| v1.0.0 | Foundation | ✅ Shipped 2026-09-13 |
| v1.1.0 | Wrapper unification | ✅ Shipped 2026-09-21 |
| v1.2.0 | US completeness | Q1 2027 |
| v1.3.0 | International expansion | Q2 2027 |
| v2.0.0 | Real-time pipeline | Late 2027 |
| v3.0.0 | Global comprehensive + publish | 2028+ |

See [`docs/roadmap.md`](./docs/roadmap.md) for detailed success criteria,
effort estimates, and dependencies.

---

## Versioning

The registry follows [Semantic Versioning](https://semver.org/):

- **Major** — breaking changes to the schema, the wrapper contract, or
  the tool CLIs.
- **Minor** — new wrapper methods, new action types, new tooling.
- **Patch** — data corrections and non-breaking bug fixes.

The wrapper versions track the registry version. All four wrappers are
at `1.1.0` for this release.

### The v1.0.0 tag was rewritten

The `v1.0.0` tag was force-pushed on 2026-09-14 as part of a history
rewrite that removed licensed identifier data from the repository. Any
consumer who pinned `v1.0.0` before that date should re-pin. The
rewritten tag is the authoritative `v1.0.0`.

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) § 10.7 for the full policy on
licensed identifier data and why the rewrite was necessary.

---

## Ecosystem

The Corporate Actions Registry is one of four registries in the QuantOS
Ledger Foundation:

| Registry | Purpose | Status |
|----------|---------|--------|
| [ISO 4217](https://github.com/slimissa/iso4217) | Currency codes | v1.5.3 |
| [Exchange Calendar](https://github.com/slimissa/exchange-calendar) | Trading calendars | v2.2.2 |
| [Asset Identifiers](https://github.com/slimissa/asset-identifiers) | ISIN/CUSIP/FIGI | schema 1.2.1 |
| **Corporate Actions** | **This registry** | **v1.1.0** |

The four registries cross-reference each other. Every corporate action's
`isin` is validated against Asset Identifiers. Every dividend's
`currency` is validated against ISO 4217. Every exchange reference is
validated against Exchange Calendar.

A future QLF Orchestrator will unify queries across all four.

---

## License

Apache 2.0. See [`LICENSE`](./LICENSE).

The registry data is factual information sourced from public filings and
announcements. The compilation, schema, tooling, wrappers, and
documentation are licensed works.

---

## Contributing

Contributions are welcome. See [`CONTRIBUTING.md`](./CONTRIBUTING.md)
for the full guide. The short version:

1. Open an issue before starting large changes.
2. Keep PRs focused.
3. Run the relevant tests locally before pushing.
4. Follow the commit message convention.
5. All PRs are squash-merged.

For specific contribution types:

- **Report a missing or incorrect action**:
  [Action update template](./.github/ISSUE_TEMPLATE/action_update.md)
- **Propose a new data source**:
  [Data source template](./.github/ISSUE_TEMPLATE/data_source.md)
- **Fix a broken fetcher**: see the
  [roadmap](./docs/roadmap.md) for the current list

---

## Author

**Le P'tit** — [github.com/slimissa](https://github.com/slimissa)

---

## Links

- [GitHub Repository](https://github.com/slimissa/corporate-actions)
- [Issue Tracker](https://github.com/slimissa/corporate-actions/issues)
- [CI Status](https://github.com/slimissa/corporate-actions/actions)
- [CHANGELOG](./CHANGELOG.md)
- [Wrapper Contract](./docs/wrapper_contract.md)
- [Roadmap](./docs/roadmap.md)
- [Contributing](./CONTRIBUTING.md)


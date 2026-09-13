# Corporate Actions Registry

[![Validate](https://github.com/slimissa/corporate-actions/actions/workflows/validate.yml/badge.svg)](https://github.com/slimissa/corporate-actions/actions/workflows/validate.yml)
[![Check Sources](https://github.com/slimissa/corporate-actions/actions/workflows/check-sources.yml/badge.svg)](https://github.com/slimissa/corporate-actions/actions/workflows/check-sources.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)
[![Registry](https://img.shields.io/badge/registry-v1.0.0-orange.svg)](./CHANGELOG.md)
[![Actions](https://img.shields.io/badge/actions-242-green.svg)](./actions.json)
[![Languages](https://img.shields.io/badge/wrappers-4-purple.svg)](./wrappers/)
[![Tests](https://img.shields.io/badge/tests-225-success.svg)](./tests/)

**A canonical, versioned, machine-readable registry of corporate actions.**
One JSON file as the source of truth. Four language wrappers. Seven-layer
validation. Zero runtime dependencies.

---

## What this is

Corporate actions are the events that change what a financial instrument is,
how much of it exists, and what it is worth: stock splits, dividends, mergers,
spinoffs, symbol changes, and delistings.

Every trading system, backtest framework, and portfolio tool needs this data.
Most projects hand-roll their own list, which becomes stale, inconsistent, or
silently wrong. A missed 10-for-1 split makes a 700% gain look like a 20% loss.
A mislabeled dividend corrupts total-return calculations.

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

**Version**: v1.0.0
**Actions**: 242
**Instruments**: ~10 US large caps
**Action types populated**: 4 of 8
**Wrappers**: Python, JavaScript, Go, Rust
**Total tests**: 225 (143 root + 82 wrapper)
**CI**: All three workflows green

### Coverage

| Category | Count | Notes |
|----------|-------|-------|
| Actions | 242 | Splits and dividends dominate |
| Instruments | ~10 | AAPL, MSFT, GOOGL, AMZN, META, NVDA, and a few more |
| Action types populated | 4 of 8 | `SPLIT`, `REVERSE_SPLIT`, `DIVIDEND`, `SPECIAL_DIVIDEND` |
| Action types reserved | 4 of 8 | `SYMBOL_CHANGE` (populated), `SPINOFF`, `DELISTING`, `MERGER` |
| Currencies | 1 | USD only |
| Exchanges | 1 | US equities (XNAS, XNYS) |
| Historical depth | 1987+ | For the longest-history instruments |

### What works, what does not

| Component | Status |
|-----------|--------|
| Yahoo Finance fetcher | ✅ Working |
| SEC EDGAR fetcher | ❌ Broken (endpoint retired) |
| Nasdaq dividends fetcher | ❌ Broken (times out) |
| Validator | ✅ All 7 layers |
| Python wrapper | ✅ 23 tests |
| JavaScript wrapper | ✅ 16 tests |
| Go wrapper | ✅ 17 tests |
| Rust wrapper | ✅ 26 tests |
| CI workflows | ✅ 3 green |

See [Known limitations](#known-limitations) for the full list.

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

Each wrapper provides idiomatic lookups on top of the JSON.

**Python**

```bash
pip install corporate-actions-registry
```

```python
from corporate_actions_registry import CorporateActionsRegistry

registry = CorporateActionsRegistry("actions.json")

# All actions for Apple
for action in registry.by_isin("US0378331005"):
    print(action.action_type, action.dates.ex_date)

# All splits in the registry
splits = registry.by_action_type("SPLIT")

# A specific action
action = registry.by_action_id("US67066G1040-SPLIT-2024-06-10-10-1")
```

**JavaScript**

```bash
npm install corporate-actions-registry
```

```javascript
const { CorporateActionsRegistry } = require('corporate-actions-registry');

const registry = new CorporateActionsRegistry('actions.json');
const aapl = registry.byIsin('US0378331005');
const splits = registry.byActionType('SPLIT');
```

**Go**

```bash
go get github.com/slimissa/corporate-actions/wrappers/go
```

```go
import registry "github.com/slimissa/corporate-actions/wrappers/go/registry"

r, _ := registry.LoadRegistry("actions.json")
aapl := r.ByISIN("US0378331005")
splits := r.ByActionType("SPLIT")
```

**Rust**

```bash
cargo add corporate-actions
```

```rust
use corporate_actions_registry::Registry;

let registry = Registry::load_from_file("actions.json")?;
let aapl = registry.by_isin("US0378331005");
let splits = registry.by_action_type("SPLIT");
```

### Run the examples

The `examples/` directory has a working CLI example for each language plus
one that demonstrates backtest price adjustment:

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
total-return. For an instrument with a split in the holding period, the raw
number is wrong and the adjusted numbers are correct. This is the concrete
value of the registry.

---

## Why this exists

Consider a backtest of NVDA held from January 2024 to July 2024. NVDA executed
a 10-for-1 split on 2024-06-10.

| Method | Result | Correct? |
|--------|--------|----------|
| Raw prices, no adjustment | +156% | ❌ Wrong |
| Split-adjusted | Correct value | ✅ |
| Split + dividend adjusted | Correct total return | ✅ |

Without the registry, a backtest framework would use the raw price series and
produce a nonsense result. With the registry, the framework can query for
actions in the holding period and restate historical prices.

The same problem applies to:

- **Dividends** affecting total-return calculations
- **Spinoffs** affecting cost basis allocation
- **Symbol changes** breaking joins keyed on ticker
- **Mergers** changing what a position represents
- **Delistings** stranding positions

Every one of these is a class of error that a well-designed data layer can
prevent. The registry is that data layer.

---

## The 8 action types

The registry supports eight corporate action types. Four are populated in
v1.0.0; four are reserved for future versions.

| Type | Status | Meaning |
|------|--------|---------|
| `SPLIT` | ✅ Populated | Forward stock split |
| `REVERSE_SPLIT` | ✅ Populated | Reverse stock split |
| `DIVIDEND` | ✅ Populated | Regular cash dividend |
| `SPECIAL_DIVIDEND` | ✅ Populated | One-time cash dividend |
| `SYMBOL_CHANGE` | ✅ Populated | Ticker change (ISIN unchanged) |
| `SPINOFF` | Reserved | Subsidiary separation |
| `DELISTING` | Reserved | Removal from exchange |
| `MERGER` | Reserved | Acquisition (rejected by validator in v1.0.0) |

See [`docs/action_types.md`](./docs/action_types.md) for the full semantics of
each type, including date ordering rules, required fields, and impact
derivation.

---

## Validation

Every action in `actions.json` passes seven independent validation layers:

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

See [`docs/validation_layers.md`](./docs/validation_layers.md) for the exact
rules each layer enforces.

---

## Data sources

| Source | Status | Used for |
|--------|--------|----------|
| Yahoo Finance (via `yfinance`) | ✅ Working | US equity splits and dividends |
| SEC EDGAR | ❌ Broken | Would cover mergers, spinoffs, delistings |
| Nasdaq dividends API | ❌ Broken | Redundant with Yahoo; scheduled for removal |

Every action in the registry has a `provenance.source_url` pointing at a
primary source (SEC filing, exchange announcement, or company press release)
or a clearly labeled secondary source (Yahoo Finance).

See [`docs/data_sources.md`](./docs/data_sources.md) for the full licensing
and reliability analysis of each source, including sources considered and
rejected.

### Source health monitoring

`.github/workflows/check-sources.yml` runs weekly and probes each source with
a real request. If a source fails, a GitHub issue is opened automatically.
When the source recovers, the issue is closed.

---

## Repository structure

```
corporate-actions/
├── actions.json                 # The registry
├── schema.json                  # JSON Schema
├── README.md                    # This file
├── CONTRIBUTING.md              # Code contribution guide
├── CHANGELOG.md                 # Version history
├── LICENSE                      # Apache 2.0
│
├── docs/                        # Long-form documentation
│   ├── action_types.md          # Semantics of the 8 action types
│   ├── validation_layers.md     # The 7 validation layers
│   ├── data_sources.md          # Source licensing and reliability
│   ├── roadmap.md               # v1.0.0 → v3.0.0
│   └── contributing.md          # Documentation contribution guide
│
├── tools/                       # Python utilities
│   ├── validate.py              # 7-layer validator
│   ├── derive_impacts.py        # Compute multipliers
│   ├── build.py                 # Distribution artifacts
│   └── fetch_*.py               # Data fetchers
│
├── scripts/                     # Operational scripts
│   ├── run_update.sh            # Full pipeline
│   ├── notify_on_change.py      # Change detection
│   └── README.md
│
├── wrappers/                    # Language bindings
│   ├── python/
│   ├── javascript/
│   ├── go/
│   └── rust/
│
├── examples/                    # Usage examples
├── tests/                       # Root test suite
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
pip install --upgrade pip
pip install pytest jsonschema yfinance requests
```

### Run tests

```bash
# Root suite (Python)
pytest tests/ -v

# Python wrapper
cd wrappers/python && pytest tests/ -v && cd -

# JavaScript wrapper
cd wrappers/javascript && npm test && cd -

# Go wrapper
cd wrappers/go && go test ./registry -v && cd -

# Rust wrapper
cd wrappers/rust && cargo test && cd -
```

### Run the update pipeline

```bash
# Dry-run: fetch, merge, validate, no commit
scripts/run_update.sh --fetch-source yahoo --dry-run --verbose

# Fast check: no fetch, no tests, no build
scripts/run_update.sh --skip-fetch --skip-tests --skip-build
```

See [`scripts/README.md`](./scripts/README.md) for all flags.

### Contribute

Read [`CONTRIBUTING.md`](./CONTRIBUTING.md) before opening a PR. For
documentation contributions, read [`docs/contributing.md`](./docs/contributing.md).

For specific contribution types:

- **Report a missing or incorrect action**:
  [Action update template](./.github/ISSUE_TEMPLATE/action_update.md)
- **Propose a new data source**:
  [Data source template](./.github/ISSUE_TEMPLATE/data_source.md)
- **Fix a broken fetcher**:
  See [roadmap v1.1.0](./docs/roadmap.md#v110--us-completeness)

---

## Known limitations

The following are documented, deliberate limitations of v1.0.0. They are
tracked in [`docs/roadmap.md`](./docs/roadmap.md) for future versions.

### Data coverage

- **10 instruments.** The registry covers a small set of US large caps. It
  is not yet a comprehensive US equity registry. Expansion to 50+ instruments
  is planned for v1.1.0 and depends on the Asset Identifiers registry
  reaching 500+ ISINs.

- **US only.** No international coverage. Expansion to EU, JP, HK, and UK
  is planned for v1.2.0.

- **USD only.** All current instruments trade in USD. Non-USD dividend
  amounts and currency conversion are planned for v1.2.0.

- **Historical depth varies.** Some instruments have data going back to the
  1980s; others only to the 2000s. Coverage is data-source dependent.

### Action types

- **No `MERGER` support.** Schema reserves the type, but the validator
  explicitly rejects any `MERGER` entry in v1.0.0. Extraction from SEC S-4
  filings is planned for v1.1.0.

- **No `SPINOFF` or `DELISTING` entries.** Schema reserves both types. No
  entries exist yet because the extraction pipeline does not cover them.

- **Announcement dates are approximated for Yahoo-sourced dividends.** The
  Yahoo API does not expose the announcement date, so it is set equal to the
  ex-date. This passes temporal validation but is not historically accurate.

- **Dividend amounts are split-adjusted as provided by yfinance.** A dividend
  paid before a split is reported at the post-split equivalent amount. This
  is intentional for backtesting but is a documented approximation.

### Sources

- **SEC EDGAR fetcher is broken.** The legacy full-text search endpoint was
  retired. Recovery is planned for v1.1.0 using the `data.sec.gov`
  submissions API.

- **Nasdaq fetcher is broken.** The API blocks non-US IPs and CI runners.
  Scheduled for removal in v1.1.0.

### Integration

- **Cross-reference uses a partial Asset Identifiers subset.** Missing ISINs
  are warnings by default. Use `--strict-isin` to promote them to errors once
  Asset Identifiers reaches full coverage.

- **Ticker-to-ISIN lookup is heuristic.** The example scripts scan
  `provenance.source_url` for the ticker. A proper lookup depends on Asset
  Identifiers exposing a ticker→ISIN index (planned for their v1.1.0).

- **Cross-language consistency is not automatically tested in CI.** Wrapper
  suites validate each language independently. A cross-wrapper comparison
  test is planned for v1.1.0.

---

## Roadmap

| Version | Theme | Target |
|---------|-------|--------|
| v1.0.0 | Foundation | ✅ Shipped 2026-09-13 |
| v1.1.0 | US completeness | Q4 2026 |
| v1.2.0 | International expansion | Q1 2027 |
| v2.0.0 | Real-time pipeline | Mid 2027 |
| v3.0.0 | Global comprehensive | 2028+ |

See [`docs/roadmap.md`](./docs/roadmap.md) for detailed success criteria,
effort estimates, and dependencies.

---

## Ecosystem

The Corporate Actions Registry is one of four registries in the QuantOS
Ledger Foundation:

| Registry | Purpose | Status |
|----------|---------|--------|
| [ISO 4217](https://github.com/slimissa/iso4217) | Currency codes | v1.3.0 |
| [Exchange Calendar](https://github.com/slimissa/exchange-calendar) | Trading calendars | v2.1.2 |
| [Asset Identifiers](https://github.com/slimissa/asset-identifiers) | ISIN/CUSIP/FIGI | v1.0.1 |
| **Corporate Actions** | **This registry** | **v1.0.0** |

The four registries cross-reference each other. Every corporate action's
`isin` is validated against Asset Identifiers. Every dividend's `currency`
is validated against ISO 4217. Every exchange reference is validated against
Exchange Calendar.

A future QLF Orchestrator will unify queries across all four.

---

## License

Apache 2.0. See [`LICENSE`](./LICENSE).

The registry data is factual information sourced from public filings and
announcements. The compilation, schema, tooling, wrappers, and documentation
are licensed works.

---

## Contributing

Contributions are welcome. See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for the
full guide. The short version:

1. Open an issue before starting large changes.
2. Keep PRs focused.
3. Run the relevant tests locally before pushing.
4. Follow the commit message convention.
5. All PRs are squash-merged.

---

## Author

**Le P'tit** — [github.com/slimissa](https://github.com/slimissa)

---

## Links

- [GitHub Repository](https://github.com/slimissa/corporate-actions)
- [Issue Tracker](https://github.com/slimissa/corporate-actions/issues)
- [CI Status](https://github.com/slimissa/corporate-actions/actions)
- [CHANGELOG](./CHANGELOG.md)
- [Roadmap](./docs/roadmap.md)
- [Contributing](./CONTRIBUTING.md)
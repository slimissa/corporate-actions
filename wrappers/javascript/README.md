# Corporate Actions Registry — JavaScript Wrapper

This is the official JavaScript wrapper for the **Corporate Actions Registry** (part of the QuantOS Ledger Foundation). It loads `actions.json` and provides a simple, dependency‑free interface to query corporate actions such as stock splits, dividends, symbol changes, and more.

## Features

- **Zero runtime dependencies** (uses only Node.js built‑in modules)
- **Fast in‑memory indexes** for O(1) lookups by ISIN, action ID, and action type
- **Date range filtering** on any date field
- **Serialization** to JSON (via `toJSON()` and `save()`)
- **Works with Node.js 14+**
- **CommonJS** module (compatible with `require`)

## Installation

```bash
npm install corporate-actions-registry
```

Or install from source:

```bash
git clone https://github.com/slimissa/corporate-actions.git
cd corporate-actions/wrappers/javascript
npm install
```

## Quick Start

```javascript
const { CorporateActionsRegistry } = require('corporate-actions-registry');

// Load the registry from actions.json
const registry = new CorporateActionsRegistry('actions.json');

// Get all actions for Apple Inc.
const aaplActions = registry.byIsin('US0378331005');
console.log(aaplActions); // array of action objects

// Find a specific action by its unique ID
const nvdaSplit = registry.byActionId('US67066G1040-SPLIT-2024-06-10-0001');
console.log(nvdaSplit.ratio); // "10:1"

// Get all splits
const allSplits = registry.byActionType('SPLIT');
```

## Loading the Registry

You can load from a file path:

```javascript
const registry = new CorporateActionsRegistry('actions.json');
```

Or from an already parsed object:

```javascript
const data = require('./actions.json');
const registry = new CorporateActionsRegistry(data);
```

## API Reference

### `constructor(source)`
- `source` can be a file path (string) or a plain object containing `{ meta, actions }`.
- Throws if `source` is not provided or if the data is invalid.

### `byIsin(isin)`
Returns an array of actions for the given ISIN.

```javascript
const actions = registry.byIsin('US0378331005');
```

### `byActionId(actionId)`
Returns a single action object or `null` if not found.

```javascript
const action = registry.byActionId('US0378331005-DIVIDEND-2024-05-16-0002');
```

### `byActionType(actionType)`
Returns an array of all actions of a given type (`'SPLIT'`, `'DIVIDEND'`, `'SYMBOL_CHANGE'`, etc.).

```javascript
const dividends = registry.byActionType('DIVIDEND');
```

### `byDateRange(startDate, endDate, dateField)`
Filters actions by a date range on a specified date field.

- `startDate` (optional): include actions with date >= startDate.
- `endDate` (optional): include actions with date <= endDate.
- `dateField` (optional, default `'ex_date'`): one of `'announcement'`, `'ex_date'`, `'record_date'`, `'effective_date'`.

```javascript
const actions = registry.byDateRange('2020-01-01', '2023-12-31', 'ex_date');
```

### `allActionTypes()`
Returns a sorted array of all unique action types.

```javascript
const types = registry.allActionTypes();
// -> ["DIVIDEND", "SPLIT", "SYMBOL_CHANGE"]
```

### `count()`
Returns the total number of actions.

```javascript
console.log(registry.count()); // 4
```

### `toJSON()`
Returns a plain object `{ meta, actions }`.

```javascript
const data = registry.toJSON();
```

### `save(filePath)`
Writes the registry to a JSON file.

```javascript
registry.save('output.json');
```

### `length` (getter)
Returns the number of actions.

```javascript
console.log(registry.length); // 4
```

## Data Structure

Each action object follows the schema defined in `actions.json`. Example:

```javascript
{
  isin: 'US0378331005',
  action_id: 'US0378331005-DIVIDEND-2024-05-16-0002',
  action_type: 'DIVIDEND',
  amount: 0.25,
  currency: 'USD',
  dates: {
    announcement: '2024-05-02',
    ex_date: '2024-05-16',
    record_date: '2024-05-17',
    effective_date: '2024-05-23'
  },
  status: 'COMPLETED',
  provenance: {
    source: 'Apple',
    source_url: 'https://example.com/aapl-div'
  },
  impact: {
    cash_adjustment: 0.25,
    price_multiplier: 1.0,
    share_multiplier: 1.0
  }
}
```

All fields are optional and may be `undefined` if not present.

## Testing

Run the test suite using Node's built‑in test runner:

```bash
npm test
```

Or directly:

```bash
node --test test/test_wrapper.js
```

## License

Apache 2.0. See [LICENSE](../../LICENSE) in the repository root.
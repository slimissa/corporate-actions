# Corporate Actions Registry — Python Wrapper

This is the official Python wrapper for the **Corporate Actions Registry** (part of the QuantOS Ledger Foundation). It loads `actions.json` and provides an intuitive, dependency‑free interface to query corporate actions such as stock splits, dividends, symbol changes, and more.

## Features

- **Zero runtime dependencies** (only the Python standard library)
- **Typed data models** (dataclasses) for `Action`, `Dates`, `Provenance`, `Impact`, and `RegistryMeta`
- **Fast in‑memory indexes** for O(1) lookups by ISIN, action ID, and action type
- **Date range filtering** on any date field (announcement, ex‑date, record date, effective date)
- **Serialization** back to JSON (via `to_dict()` and `save()`)
- **Works with Python 3.8+**

## Installation

```bash
pip install corporate-actions-registry
```

Or install from source:

```bash
git clone https://github.com/slimissa/corporate-actions.git
cd corporate-actions/wrappers/python
pip install .
```

## Quick Start

```python
from corporate_actions_registry import CorporateActionsRegistry

# Load the registry from actions.json
registry = CorporateActionsRegistry("path/to/actions.json")

# Get all actions for Apple Inc.
aapl_actions = registry.by_isin("US0378331005")
for action in aapl_actions:
    print(action.action_type, action.dates.ex_date)

# Find a specific action by its unique ID
nvda_split = registry.by_action_id("US67066G1040-SPLIT-2024-06-10-0001")
print(nvda_split.ratio)  # "10:1"

# Get all splits in the registry
all_splits = registry.by_action_type("SPLIT")
```

## Loading the Registry

You can load from a file path:

```python
registry = CorporateActionsRegistry("actions.json")
```

Or from an already loaded dictionary:

```python
import json
with open("actions.json") as f:
    data = json.load(f)
registry = CorporateActionsRegistry(actions_data=data)
```

## Lookup Methods

### `by_isin(isin: str) -> List[Action]`
Returns all actions for the given ISIN.

```python
actions = registry.by_isin("US0378331005")
```

### `by_action_id(action_id: str) -> Optional[Action]`
Returns a single action by its unique `action_id`, or `None` if not found.

```python
action = registry.by_action_id("US0378331005-DIVIDEND-2024-05-16-0002")
```

### `by_action_type(action_type: str) -> List[Action]`
Returns all actions of a given type (e.g., `"SPLIT"`, `"DIVIDEND"`, `"SYMBOL_CHANGE"`).

```python
splits = registry.by_action_type("SPLIT")
dividends = registry.by_action_type("DIVIDEND")
```

### `by_date_range(start_date=None, end_date=None, date_field="ex_date") -> List[Action]`
Filters actions by a date range on a specified date field.

Date fields can be:
- `"announcement"`
- `"ex_date"`
- `"record_date"`
- `"effective_date"`

Example: get all actions with ex‑date between 2020 and 2023:

```python
actions = registry.by_date_range(start_date="2020-01-01", end_date="2023-12-31", date_field="ex_date")
```

### `all_action_types() -> List[str]`
Returns a sorted list of all unique action types present in the registry.

```python
types = registry.all_action_types()
# ["DIVIDEND", "SPLIT", "SYMBOL_CHANGE"]
```

## Data Models

The wrapper uses lightweight dataclasses. Each model has `from_dict()` and `to_dict()` methods for serialization.

- **`Action`** – the core object with `isin`, `action_id`, `action_type`, `ratio`, `amount`, `currency`, `dates`, `status`, `provenance`, and `impact`.
- **`Dates`** – contains `announcement`, `ex_date`, `record_date`, `effective_date`.
- **`Provenance`** – source and verification info: `source`, `source_url`, `verification_source`, `verification_url`.
- **`Impact`** – multipliers for backtesting: `price_multiplier`, `share_multiplier`, `cash_adjustment`.
- **`RegistryMeta`** – metadata from the JSON file: `version`, `generated_at`, `source`, `notes`.

Example of accessing nested data:

```python
action = registry.by_action_id("US0378331005-DIVIDEND-2024-05-16-0002")
print(action.dates.ex_date)        # "2024-05-16"
print(action.provenance.source)    # "Apple Inc."
print(action.impact.cash_adjustment)  # 0.25
```

All fields are optional and may be `None` if not present in the JSON. The `to_dict()` method omits `None` values.

## Serialization

You can convert the entire registry back to a dictionary and save it:

```python
data = registry.to_dict()
registry.save("output.json")
```

## Testing

The wrapper includes a comprehensive test suite covering loading, lookups, serialization, and data models.

To run tests from the repository root:

```bash
pytest wrappers/python/tests/test_wrapper.py
```

Or from the `wrappers/python` directory:

```bash
pytest tests/test_wrapper.py
```

## License

Apache 2.0. See the [LICENSE](../../LICENSE) file in the root repository.
```

This README is comprehensive and accurate, matching the code we provided. It includes all necessary sections and examples.```markdown
# Corporate Actions Registry — Python Wrapper

This is the official Python wrapper for the **Corporate Actions Registry** (part of the QuantOS Ledger Foundation). It loads `actions.json` and provides an intuitive, dependency‑free interface to query corporate actions such as stock splits, dividends, symbol changes, and more.

## Features

- **Zero runtime dependencies** (only the Python standard library)
- **Typed data models** (dataclasses) for `Action`, `Dates`, `Provenance`, `Impact`, and `RegistryMeta`
- **Fast in‑memory indexes** for O(1) lookups by ISIN, action ID, and action type
- **Date range filtering** on any date field (announcement, ex‑date, record date, effective date)
- **Serialization** back to JSON (via `to_dict()` and `save()`)
- **Works with Python 3.8+**

## Installation

```bash
pip install corporate-actions-registry
```

Or install from source:

```bash
git clone https://github.com/slimissa/corporate-actions.git
cd corporate-actions/wrappers/python
pip install .
```

## Quick Start

```python
from corporate_actions_registry import CorporateActionsRegistry

# Load the registry from actions.json
registry = CorporateActionsRegistry("path/to/actions.json")

# Get all actions for Apple Inc.
aapl_actions = registry.by_isin("US0378331005")
for action in aapl_actions:
    print(action.action_type, action.dates.ex_date)

# Find a specific action by its unique ID
nvda_split = registry.by_action_id("US67066G1040-SPLIT-2024-06-10-0001")
print(nvda_split.ratio)  # "10:1"

# Get all splits in the registry
all_splits = registry.by_action_type("SPLIT")
```

## Loading the Registry

You can load from a file path:

```python
registry = CorporateActionsRegistry("actions.json")
```

Or from an already loaded dictionary:

```python
import json
with open("actions.json") as f:
    data = json.load(f)
registry = CorporateActionsRegistry(actions_data=data)
```

## Lookup Methods

### `by_isin(isin: str) -> List[Action]`
Returns all actions for the given ISIN.

```python
actions = registry.by_isin("US0378331005")
```

### `by_action_id(action_id: str) -> Optional[Action]`
Returns a single action by its unique `action_id`, or `None` if not found.

```python
action = registry.by_action_id("US0378331005-DIVIDEND-2024-05-16-0002")
```

### `by_action_type(action_type: str) -> List[Action]`
Returns all actions of a given type (e.g., `"SPLIT"`, `"DIVIDEND"`, `"SYMBOL_CHANGE"`).

```python
splits = registry.by_action_type("SPLIT")
dividends = registry.by_action_type("DIVIDEND")
```

### `by_date_range(start_date=None, end_date=None, date_field="ex_date") -> List[Action]`
Filters actions by a date range on a specified date field.

Date fields can be:
- `"announcement"`
- `"ex_date"`
- `"record_date"`
- `"effective_date"`

Example: get all actions with ex‑date between 2020 and 2023:

```python
actions = registry.by_date_range(start_date="2020-01-01", end_date="2023-12-31", date_field="ex_date")
```

### `all_action_types() -> List[str]`
Returns a sorted list of all unique action types present in the registry.

```python
types = registry.all_action_types()
# ["DIVIDEND", "SPLIT", "SYMBOL_CHANGE"]
```

## Data Models

The wrapper uses lightweight dataclasses. Each model has `from_dict()` and `to_dict()` methods for serialization.

- **`Action`** – the core object with `isin`, `action_id`, `action_type`, `ratio`, `amount`, `currency`, `dates`, `status`, `provenance`, and `impact`.
- **`Dates`** – contains `announcement`, `ex_date`, `record_date`, `effective_date`.
- **`Provenance`** – source and verification info: `source`, `source_url`, `verification_source`, `verification_url`.
- **`Impact`** – multipliers for backtesting: `price_multiplier`, `share_multiplier`, `cash_adjustment`.
- **`RegistryMeta`** – metadata from the JSON file: `version`, `generated_at`, `source`, `notes`.

Example of accessing nested data:

```python
action = registry.by_action_id("US0378331005-DIVIDEND-2024-05-16-0002")
print(action.dates.ex_date)        # "2024-05-16"
print(action.provenance.source)    # "Apple Inc."
print(action.impact.cash_adjustment)  # 0.25
```

All fields are optional and may be `None` if not present in the JSON. The `to_dict()` method omits `None` values.

## Serialization

You can convert the entire registry back to a dictionary and save it:

```python
data = registry.to_dict()
registry.save("output.json")
```

## Testing

The wrapper includes a comprehensive test suite covering loading, lookups, serialization, and data models.

To run tests from the repository root:

```bash
pytest wrappers/python/tests/test_wrapper.py
```

Or from the `wrappers/python` directory:

```bash
pytest tests/test_wrapper.py
```

## License

Apache 2.0. See the [LICENSE](../../LICENSE) file in the root repository.
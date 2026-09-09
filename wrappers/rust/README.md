# Corporate Actions Registry — Rust Wrapper

This is the official Rust crate for the **Corporate Actions Registry** (part of the QuantOS Ledger Foundation). It loads `actions.json` and provides a typed, dependency‑light interface to query corporate actions such as stock splits, dividends, symbol changes, and more.

## Features

- **Typed data models** (`Action`, `Dates`, `Provenance`, `Impact`, `Meta`) with serde support
- **Fast in‑memory indexes** for O(1) lookups by ISIN, action ID, and action type
- **Date range filtering** on any date field
- **Serialization** back to JSON (via `to_json()` and `save()`)
- **Error handling** with `thiserror` for clear messages
- **Works with Rust 2021 edition and later**

## Installation

Add this to your `Cargo.toml`:

```toml
[dependencies]
corporate-actions = "1.0.0"
```

Or from source:

```bash
git clone https://github.com/slimissa/corporate-actions.git
cd corporate-actions/wrappers/rust
cargo build
```

## Quick Start

```rust
use corporate_actions::Registry;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let registry = Registry::load_from_file("actions.json")?;

    // Get all actions for Apple Inc.
    let aapl_actions = registry.by_isin("US0378331005");
    for action in aapl_actions {
        println!("{:?} {:?}", action.action_type, action.dates);
    }

    // Find a specific action by its unique ID
    if let Some(split) = registry.by_action_id("US67066G1040-SPLIT-2024-06-10-0001") {
        println!("Split ratio: {:?}", split.ratio);
    }

    // Get all splits
    let all_splits = registry.by_action_type("SPLIT");
    println!("Found {} splits", all_splits.len());

    Ok(())
}
```

## Loading the Registry

You can load from a file path:

```rust
let registry = Registry::load_from_file("actions.json")?;
```

Or from an already parsed `serde_json::Value`:

```rust
let data: serde_json::Value = serde_json::from_str(&file_content)?;
let registry = Registry::from_value(data)?;
```

## API Reference

### `Registry::load_from_file<P: AsRef<Path>>(path: P) -> Result<Registry, RegistryError>`
Loads and parses the registry from a file.

### `Registry::from_value(data: serde_json::Value) -> Result<Registry, RegistryError>`
Constructs the registry from a `serde_json::Value`.

### `by_isin(&self, isin: &str) -> Vec<Action>`
Returns all actions for the given ISIN. Returns an empty vector if none.

### `by_action_id(&self, action_id: &str) -> Option<Action>`
Returns a single action by its unique `action_id`, or `None` if not found.

### `by_action_type(&self, action_type: &str) -> Vec<Action>`
Returns all actions of a given type (e.g., `"SPLIT"`, `"DIVIDEND"`, `"SYMBOL_CHANGE"`).

### `by_date_range(&self, start_date: Option<&str>, end_date: Option<&str>, date_field: &str) -> Vec<Action>`
Filters actions by a date range on a specified date field.

- `date_field` can be `"announcement"`, `"ex_date"`, `"record_date"`, or `"effective_date"`.
- Dates are compared lexicographically (ISO `YYYY-MM-DD` format).
- If `start_date` or `end_date` is `None`, that bound is ignored.

Example:
```rust
let actions = registry.by_date_range(Some("2020-01-01"), Some("2023-12-31"), "ex_date");
```

### `all_action_types(&self) -> Vec<String>`
Returns a sorted vector of all unique action types.

### `count(&self) -> usize`
Returns the total number of actions.

### `meta(&self) -> &Meta`
Returns a reference to the registry metadata.

### `to_json(&self) -> serde_json::Value`
Converts the registry back to a JSON value.

### `save<P: AsRef<Path>>(&self, path: P) -> Result<(), RegistryError>`
Saves the registry to a file.

## Data Models

The crate defines the following structs:

- **`Action`** – `isin`, `action_id`, `action_type`, `ratio`, `amount`, `currency`, `dates`, `status`, `provenance`, `impact`.
- **`Dates`** – `announcement`, `ex_date`, `record_date`, `effective_date`.
- **`Provenance`** – `source`, `source_url`, `verification_source`, `verification_url`.
- **`Impact`** – `price_multiplier`, `share_multiplier`, `cash_adjustment`.
- **`Meta`** – `version`, `generated_at`, `source`, `notes`.

All fields are `Option<T>` and may be `None` if absent in the JSON.

## Error Handling

The crate uses `thiserror` to define `RegistryError`:

- `RegistryError::Io` – file I/O errors.
- `RegistryError::Json` – JSON parsing errors.
- `RegistryError::InvalidStructure` – missing or malformed registry keys.

All methods that load or parse return `Result<_, RegistryError>`.

## Testing

Run the included integration tests:

```bash
cargo test
```

The tests cover loading, lookups, date filtering, serialization, and error cases.

## License

Apache 2.0. See [LICENSE](../../LICENSE) in the repository root.
# Corporate Actions Registry — Go Wrapper

This is the official Go wrapper for the **Corporate Actions Registry** (part of the QuantOS Ledger Foundation). It loads `actions.json` and provides a typed, dependency‑free interface to query corporate actions such as stock splits, dividends, symbol changes, and more.

## Features

- **Typed data structures** (`Action`, `Dates`, `Provenance`, `Impact`, `Meta`)
- **Fast in‑memory indexes** for O(1) lookups by ISIN, action ID, and action type
- **Date range filtering** on any date field
- **Serialization** back to JSON (via `ToJSON()` and `Save()`)
- **No external dependencies** (uses only the Go standard library)
- **Works with Go 1.21+**

## Installation

Add this to your `go.mod`:

```go
require github.com/slimissa/corporate-actions/wrappers/go v1.0.0
```

Or install from source:

```bash
git clone https://github.com/slimissa/corporate-actions.git
cd corporate-actions/wrappers/go
go build ./...
```

## Quick Start

```go
package main

import (
    "fmt"
    registry "github.com/slimissa/corporate-actions/wrappers/go/registry"
)

func main() {
    r, err := registry.LoadRegistry("actions.json")
    if err != nil {
        panic(err)
    }

    // Get all actions for Apple Inc.
    aaplActions := r.ByISIN("US0378331005")
    for _, action := range aaplActions {
        fmt.Println(*action.ActionType, *action.Dates.ExDate)
    }

    // Find a specific action by its unique ID
    nvdaSplit := r.ByActionID("US67066G1040-SPLIT-2024-06-10-0001")
    if nvdaSplit != nil {
        fmt.Println("Split ratio:", *nvdaSplit.Ratio)
    }

    // Get all splits
    allSplits := r.ByActionType("SPLIT")
    fmt.Println("Number of splits:", len(allSplits))
}
```

## Loading the Registry

You can load from a file path:

```go
r, err := registry.LoadRegistry("actions.json")
```

Or parse from raw JSON bytes:

```go
data, _ := os.ReadFile("actions.json")
r, err := registry.FromJSON(data)
```

## API Reference

### `LoadRegistry(path string) (*Registry, error)`
Loads the registry from a JSON file.

### `FromJSON(data []byte) (*Registry, error)`
Parses the registry from raw JSON bytes.

### `ByISIN(isin string) []Action`
Returns all actions for the given ISIN. Returns `nil` if none found.

### `ByActionID(actionID string) *Action`
Returns a pointer to a single action by its unique `action_id`, or `nil` if not found.

### `ByActionType(actionType string) []Action`
Returns all actions of a given type (e.g., `"SPLIT"`, `"DIVIDEND"`, `"SYMBOL_CHANGE"`).

### `ByDateRange(startDate, endDate, dateField string) []Action`
Filters actions by a date range on a specified date field.

- `dateField` can be `"announcement"`, `"ex_date"`, `"record_date"`, or `"effective_date"`.
- Dates are compared lexicographically (ISO `YYYY-MM-DD` format).
- Empty `startDate` or `endDate` means no bound on that side.

Example:

```go
actions := r.ByDateRange("2020-01-01", "2023-12-31", "ex_date")
```

### `AllActionTypes() []string`
Returns a sorted slice of all unique action types.

### `Count() int`
Returns the total number of actions.

### `Meta() *Meta`
Returns a pointer to the registry metadata.

### `ToJSON() ([]byte, error)`
Marshals the registry back to indented JSON.

### `Save(path string) error`
Writes the registry to a file.

## Data Structures

All fields are pointers (`*string`, `*float64`) to allow omission when not present.

- **`Action`** – `ISIN`, `ActionID`, `ActionType`, `Ratio`, `Amount`, `Currency`, `Dates`, `Status`, `Provenance`, `Impact`.
- **`Dates`** – `Announcement`, `ExDate`, `RecordDate`, `EffectiveDate`.
- **`Provenance`** – `Source`, `SourceURL`, `VerificationSource`, `VerificationURL`.
- **`Impact`** – `PriceMultiplier`, `ShareMultiplier`, `CashAdjustment`.
- **`Meta`** – `Version`, `GeneratedAt`, `Source`, `Notes`.

Example of accessing nested data:

```go
action := r.ByActionID("US0378331005-DIVIDEND-2024-05-16-0002")
if action.Dates.ExDate != nil {
    fmt.Println("Ex date:", *action.Dates.ExDate)
}
if action.Impact.CashAdjustment != nil {
    fmt.Println("Cash adjustment:", *action.Impact.CashAdjustment)
}
```

## Testing

Run the included tests:

```bash
go test ./registry
```

The tests cover loading, lookups, date range filtering, serialization, and edge cases.

## License

Apache 2.0. See [LICENSE](../../LICENSE) in the repository root.
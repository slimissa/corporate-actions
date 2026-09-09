//! Integration tests for the Corporate Actions Registry Rust wrapper.
//!
//! These tests cover loading from file and JSON value, error handling,
//! all query methods, serialization round-trip, and edge cases.

use corporate_actions_registry::{Registry, RegistryError};
use serde_json::json;
use std::fs;
use std::io::Write;
use std::path::PathBuf;

/// Create a temporary file with the given content and return its path.
fn write_temp_file(name: &str, content: &str) -> PathBuf {
    let mut path = std::env::temp_dir();
    path.push(name);
    let mut file = fs::File::create(&path).expect("failed to create temp file");
    file.write_all(content.as_bytes())
        .expect("failed to write temp file");
    path
}

/// Remove a temporary file.
fn remove_temp_file(path: &PathBuf) {
    let _ = fs::remove_file(path);
}

/// Return a sample JSON value representing a valid registry.
fn sample_data() -> serde_json::Value {
    json!({
        "meta": {
            "version": "1.0.0",
            "generated_at": "2026-09-09T12:00:00Z",
            "source": "Test",
            "notes": "Sample data for testing"
        },
        "actions": [
            {
                "isin": "US67066G1040",
                "action_id": "US67066G1040-SPLIT-2024-06-10-0001",
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
                    "source": "NVIDIA",
                    "source_url": "https://example.com/nvda-split",
                    "verification_source": "SEC EDGAR"
                },
                "impact": {
                    "price_multiplier": 0.1,
                    "share_multiplier": 10.0
                }
            },
            {
                "isin": "US0378331005",
                "action_id": "US0378331005-DIVIDEND-2024-05-16-0002",
                "action_type": "DIVIDEND",
                "amount": 0.25,
                "currency": "USD",
                "dates": {
                    "announcement": "2024-05-02",
                    "ex_date": "2024-05-16",
                    "record_date": "2024-05-17",
                    "effective_date": "2024-05-23"
                },
                "status": "COMPLETED",
                "provenance": {
                    "source": "Apple",
                    "source_url": "https://example.com/aapl-div"
                },
                "impact": {
                    "cash_adjustment": 0.25,
                    "price_multiplier": 1.0,
                    "share_multiplier": 1.0
                }
            },
            {
                "isin": "US0378331005",
                "action_id": "US0378331005-SPLIT-2020-08-31-0003",
                "action_type": "SPLIT",
                "ratio": "4:1",
                "dates": {
                    "announcement": "2020-07-30",
                    "ex_date": "2020-08-31",
                    "record_date": "2020-08-24",
                    "effective_date": "2020-08-31"
                },
                "status": "COMPLETED",
                "provenance": {
                    "source": "Apple",
                    "source_url": "https://example.com/aapl-split"
                },
                "impact": {
                    "price_multiplier": 0.25,
                    "share_multiplier": 4.0
                }
            },
            {
                "isin": "US30303M1027",
                "action_id": "US30303M1027-SYMBOL_CHANGE-2022-06-09-0004",
                "action_type": "SYMBOL_CHANGE",
                "dates": {
                    "announcement": "2022-06-09",
                    "effective_date": "2022-06-09"
                },
                "status": "COMPLETED",
                "provenance": {
                    "source": "Meta",
                    "source_url": "https://example.com/meta-symbol"
                },
                "impact": {}
            }
        ]
    })
}

// ---------------------------------------------------------------------
// Loading tests
// ---------------------------------------------------------------------

#[test]
fn load_from_file_works() {
    let data = sample_data().to_string();
    let path = write_temp_file("test_actions_load.json", &data);
    let registry = Registry::load_from_file(&path).expect("failed to load from file");
    assert_eq!(registry.count(), 4);
    assert_eq!(registry.meta().version.as_deref(), Some("1.0.0"));
    remove_temp_file(&path);
}

#[test]
fn load_from_value_works() {
    let registry = Registry::from_value(sample_data()).expect("failed to load from value");
    assert_eq!(registry.count(), 4);
    assert_eq!(registry.meta().source.as_deref(), Some("Test"));
}

#[test]
fn load_missing_file_returns_io_error() {
    let result = Registry::load_from_file("/nonexistent/path/actions.json");
    assert!(matches!(result, Err(RegistryError::Io(_))));
}

#[test]
fn load_invalid_json_returns_json_error() {
    let path = write_temp_file("invalid_actions.json", "not valid json");
    let result = Registry::load_from_file(&path);
    assert!(matches!(result, Err(RegistryError::Json(_))));
    remove_temp_file(&path);
}

#[test]
fn load_missing_actions_key_returns_invalid_structure() {
    let data = json!({ "meta": { "version": "1.0.0" } });
    let result = Registry::from_value(data);
    assert!(matches!(result, Err(RegistryError::InvalidStructure(_))));
}

#[test]
fn load_actions_not_array_returns_invalid_structure() {
    let data = json!({ "actions": "not array" });
    let result = Registry::from_value(data);
    assert!(matches!(result, Err(RegistryError::InvalidStructure(_))));
}

#[test]
fn load_invalid_action_entry_returns_invalid_structure() {
    let data = json!({
        "actions": [ { "bad": "data" } ]
    });
    let result = Registry::from_value(data);
    assert!(matches!(result, Err(RegistryError::InvalidStructure(_))));
}

#[test]
fn load_empty_actions_is_ok() {
    let data = json!({ "actions": [] });
    let registry = Registry::from_value(data).expect("empty actions should be valid");
    assert_eq!(registry.count(), 0);
    assert!(registry.all_action_types().is_empty());
}

// ---------------------------------------------------------------------
// Lookup tests
// ---------------------------------------------------------------------

#[test]
fn by_isin_returns_correct_actions() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let aapl = registry.by_isin("US0378331005");
    assert_eq!(aapl.len(), 2);
    assert!(aapl.iter().all(|a| a.isin.as_deref() == Some("US0378331005")));
}

#[test]
fn by_isin_unknown_returns_empty() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry.by_isin("US0000000000");
    assert!(actions.is_empty());
}

#[test]
fn by_action_id_found() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let action = registry.by_action_id("US67066G1040-SPLIT-2024-06-10-0001");
    assert!(action.is_some());
    let action = action.unwrap();
    assert_eq!(action.action_type.as_deref(), Some("SPLIT"));
    assert_eq!(action.ratio.as_deref(), Some("10:1"));
}

#[test]
fn by_action_id_not_found_returns_none() {
    let registry = Registry::from_value(sample_data()).unwrap();
    assert!(registry.by_action_id("NONEXISTENT").is_none());
}

#[test]
fn by_action_type_returns_all_of_type() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let splits = registry.by_action_type("SPLIT");
    assert_eq!(splits.len(), 2);
    assert!(splits.iter().all(|a| a.action_type.as_deref() == Some("SPLIT")));
}

#[test]
fn by_action_type_unknown_returns_empty() {
    let registry = Registry::from_value(sample_data()).unwrap();
    assert!(registry.by_action_type("MERGER").is_empty());
}

#[test]
fn by_date_range_filters_on_ex_date() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry.by_date_range(Some("2020-01-01"), Some("2023-12-31"), "ex_date");
    assert_eq!(actions.len(), 1);
    assert_eq!(
        actions[0].action_id.as_deref(),
        Some("US0378331005-SPLIT-2020-08-31-0003")
    );
}

#[test]
fn by_date_range_filters_on_effective_date() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry.by_date_range(Some("2024-01-01"), Some("2024-12-31"), "effective_date");
    assert_eq!(actions.len(), 2);
    // The two actions with effective_date in 2024: NVDA split (2024-06-10) and AAPL dividend (2024-05-23)
    assert!(actions.iter().any(|a| a.action_id.as_deref() == Some("US67066G1040-SPLIT-2024-06-10-0001")));
    assert!(actions.iter().any(|a| a.action_id.as_deref() == Some("US0378331005-DIVIDEND-2024-05-16-0002")));
}

#[test]
fn by_date_range_with_invalid_field_returns_empty() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry.by_date_range(None, None, "invalid_field");
    assert!(actions.is_empty());
}

#[test]
fn by_date_range_with_no_dates_returns_empty() {
    let data = json!({
        "actions": [
            {
                "isin": "US1234567890",
                "action_id": "ID-1",
                "action_type": "SPLIT"
                // No dates field
            }
        ]
    });
    let registry = Registry::from_value(data).unwrap();
    let actions = registry.by_date_range(None, None, "ex_date");
    assert!(actions.is_empty());
}

#[test]
fn all_action_types_sorted() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let types = registry.all_action_types();
    assert_eq!(types, vec!["DIVIDEND", "SPLIT", "SYMBOL_CHANGE"]);
}

#[test]
fn count_returns_total() {
    let registry = Registry::from_value(sample_data()).unwrap();
    assert_eq!(registry.count(), 4);
}

// ---------------------------------------------------------------------
// Serialization tests
// ---------------------------------------------------------------------

#[test]
fn to_json_and_from_value_roundtrip() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let json_value = registry.to_json();
    let registry2 = Registry::from_value(json_value).expect("roundtrip failed");
    assert_eq!(registry.count(), registry2.count());
    assert_eq!(registry.meta().version, registry2.meta().version);
    // Compare serialized forms for exact equality
    let json1 = serde_json::to_value(&registry.to_json()).unwrap();
    let json2 = serde_json::to_value(&registry2.to_json()).unwrap();
    assert_eq!(json1, json2);
}

#[test]
fn save_and_reload_from_file() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let path = write_temp_file("output_actions.json", "");
    registry.save(&path).expect("save failed");
    let loaded = Registry::load_from_file(&path).expect("reload failed");
    assert_eq!(loaded.count(), registry.count());
    // Compare meta versions
    assert_eq!(loaded.meta().version, registry.meta().version);
    remove_temp_file(&path);
}

#[test]
fn save_creates_valid_json_file() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let path = write_temp_file("save_test.json", "");
    registry.save(&path).unwrap();
    let content = fs::read_to_string(&path).unwrap();
    let parsed: serde_json::Value = serde_json::from_str(&content).unwrap();
    assert!(parsed.get("meta").is_some());
    assert!(parsed.get("actions").is_some());
    remove_temp_file(&path);
}

// ---------------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------------

#[test]
fn registry_with_no_meta_is_ok() {
    let data = json!({ "actions": [] });
    let registry = Registry::from_value(data).unwrap();
    assert_eq!(registry.count(), 0);
    assert_eq!(registry.meta().version, None);
}

#[test]
fn action_fields_are_optional() {
    let data = json!({
        "actions": [ { "isin": "US1234567890" } ]
    });
    let registry = Registry::from_value(data).unwrap();
    let action = &registry.by_isin("US1234567890")[0];
    assert_eq!(action.action_id, None);
    assert_eq!(action.action_type, None);
    assert_eq!(action.dates, None);
    assert_eq!(action.provenance, None);
    assert_eq!(action.impact, None);
}   
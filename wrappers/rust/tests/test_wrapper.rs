//! Integration tests for the Corporate Actions Registry Rust wrapper.
//!
//! These tests exercise the public API only: they build a `Registry`
//! from JSON and check its behaviour. They never touch private fields,
//! so an internal refactor does not break them.
//!
//! The tests encode the contract in `docs/wrapper_contract.md`. A
//! failing test means either the wrapper has drifted from the contract
//! or the contract needs to change; the failure message says which.

use corporate_actions_registry::{Registry, RegistryError};
use serde_json::json;
use std::fs;
use std::io::Write;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};

// ----------------------------------------------------------------------
// Temp file helpers
// ----------------------------------------------------------------------

/// Process-wide counter for unique temp filenames.
///
/// `cargo test` runs integration tests in parallel by default, so two
/// tests writing to the same fixed temp path would collide. Including
/// a monotonic counter in the filename removes that class of
/// flakiness.
static TEMP_COUNTER: AtomicU64 = AtomicU64::new(0);

/// Return a unique path under the system temp directory.
fn unique_temp_path(suffix: &str) -> PathBuf {
    let n = TEMP_COUNTER.fetch_add(1, Ordering::SeqCst);
    let pid = std::process::id();
    std::env::temp_dir().join(format!("tempus_test_{}_{}_{}", pid, n, suffix))
}

/// Write `content` to a fresh temp file and return its path.
fn write_temp_file(suffix: &str, content: &[u8]) -> PathBuf {
    let path = unique_temp_path(suffix);
    let mut f = fs::File::create(&path).expect("create temp file");
    f.write_all(content).expect("write temp file");
    path
}

/// Best-effort cleanup so a failing test does not leave files behind.
fn remove_temp_file(path: &PathBuf) {
    let _ = fs::remove_file(path);
}

// ----------------------------------------------------------------------
// Fixtures
// ----------------------------------------------------------------------

/// A four-action fixture.
///
/// Actions:
///   - NVDA 10:1 split on 2024-06-10
///   - AAPL dividend on 2024-05-16
///   - AAPL 4:1 split on 2020-08-31
///   - META symbol change on 2022-06-09 (no ex_date, no record_date)
///
/// The spread of dates and the missing `ex_date` let the date-range
/// tests exercise inclusive bounds, missing fields, and sort order.
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
                "action_id": "US0378331005-DIVIDEND-2024-05-16-0.2500",
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
                "action_id": "US0378331005-SPLIT-2020-08-31-4-1",
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
                "action_id": "US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL",
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

/// Two actions sharing an `ex_date`, to prove the sort breaks ties on
/// `action_id` rather than on insertion order.
fn tiebreak_data() -> serde_json::Value {
    json!({
        "meta": {"version": "1.0.0"},
        "actions": [
            {
                "isin": "US0000000001",
                "action_id": "US0000000001-DIVIDEND-2024-05-16-0.2500",
                "action_type": "DIVIDEND",
                "dates": {
                    "announcement": "2024-05-02",
                    "ex_date": "2024-05-16",
                    "effective_date": "2024-05-23"
                }
            },
            {
                "isin": "US0000000002",
                "action_id": "US0000000002-DIVIDEND-2024-05-16-0.3000",
                "action_type": "DIVIDEND",
                "dates": {
                    "announcement": "2024-05-02",
                    "ex_date": "2024-05-16",
                    "effective_date": "2024-05-23"
                }
            }
        ]
    })
}

// ----------------------------------------------------------------------
// Loading: load_from_file
// ----------------------------------------------------------------------

#[test]
fn load_from_file_works() {
    let path = write_temp_file("load.json", sample_data().to_string().as_bytes());
    let registry = Registry::load_from_file(&path).expect("load from file");
    assert_eq!(registry.count(), 4);
    assert_eq!(registry.meta().version.as_deref(), Some("1.0.0"));
    remove_temp_file(&path);
}

#[test]
fn load_missing_file_returns_io_error() {
    let result = Registry::load_from_file("/nonexistent/path/actions.json");
    assert!(matches!(result, Err(RegistryError::Io(_))));
}

#[test]
fn load_invalid_json_returns_json_error() {
    let path = write_temp_file("invalid.json", b"not valid json");
    let result = Registry::load_from_file(&path);
    assert!(matches!(result, Err(RegistryError::Json(_))));
    remove_temp_file(&path);
}

#[test]
fn load_from_file_strips_utf8_bom() {
    let mut bytes = b"\xEF\xBB\xBF".to_vec();
    bytes.extend(sample_data().to_string().as_bytes());
    let path = write_temp_file("bom.json", &bytes);
    let registry = Registry::load_from_file(&path).expect("BOM should be stripped");
    assert_eq!(registry.count(), 4);
    remove_temp_file(&path);
}

#[test]
fn load_from_file_empty_actions_is_ok() {
    let path = write_temp_file("empty.json", br#"{"actions": []}"#);
    let registry = Registry::load_from_file(&path).expect("empty actions valid");
    assert_eq!(registry.count(), 0);
    remove_temp_file(&path);
}

// ----------------------------------------------------------------------
// Loading: from_value
// ----------------------------------------------------------------------

#[test]
fn load_from_value_works() {
    let registry = Registry::from_value(sample_data()).expect("load from value");
    assert_eq!(registry.count(), 4);
    assert_eq!(registry.meta().source.as_deref(), Some("Test"));
}

#[test]
fn load_missing_actions_key_returns_invalid_structure() {
    let result = Registry::from_value(json!({"meta": {"version": "1.0.0"}}));
    match result {
        Err(RegistryError::InvalidStructure(msg)) => {
            assert!(msg.contains("missing 'actions' key"), "got: {}", msg);
        }
        Err(other) => panic!("expected InvalidStructure, got {:?}", other),
        Ok(_) => panic!("expected an error, got Ok"),
    }
}

#[test]
fn load_actions_not_array_returns_invalid_structure() {
    let cases = [
        json!({"actions": "string"}),
        json!({"actions": 42}),
        json!({"actions": true}),
        json!({"actions": null}),
        json!({"actions": {"not": "an array"}}),
    ];
    for case in &cases {
        let result = Registry::from_value(case.clone());
        assert!(
            matches!(result, Err(RegistryError::InvalidStructure(_))),
            "expected error for {}",
            case
        );
    }
}

#[test]
fn load_non_object_entry_returns_invalid_structure() {
    let cases = [
        json!({"actions": ["string"]}),
        json!({"actions": [42]}),
        json!({"actions": [true]}),
        json!({"actions": [null]}),
        json!({"actions": [[]]}),
    ];
    for case in &cases {
        let result = Registry::from_value(case.clone());
        match result {
            Err(RegistryError::InvalidStructure(msg)) => {
                assert!(
                    msg.contains("not an object"),
                    "expected 'not an object' in message, got: {}",
                    msg
                );
            }
            Err(other) => panic!("expected InvalidStructure, got {:?}", other),
            Ok(_) => panic!("expected an error for {}", case),
        }
    }
}

#[test]
fn load_non_object_entry_names_the_index() {
    let result = Registry::from_value(json!({
        "actions": [
            {"isin": "US0000000001", "action_id": "ok"},
            "bad"
        ]
    }));
    match result {
        Err(RegistryError::InvalidStructure(msg)) => {
            assert!(msg.contains("index 1"), "got: {}", msg);
        }
        _ => panic!("expected InvalidStructure with index"),
    }
}

#[test]
fn load_action_missing_isin_and_action_id_returns_error() {
    let result = Registry::from_value(json!({
        "actions": [{"action_type": "SPLIT", "ratio": "2:1"}]
    }));
    match result {
        Err(RegistryError::InvalidStructure(msg)) => {
            assert!(
                msg.contains("missing both") || msg.contains("isin"),
                "got: {}",
                msg
            );
        }
        _ => panic!("expected error for missing identifiers"),
    }
}

#[test]
fn load_empty_actions_is_ok() {
    let registry = Registry::from_value(json!({"actions": []})).expect("empty valid");
    assert_eq!(registry.count(), 0);
    assert!(registry.all_action_types().is_empty());
    assert!(registry.by_isin("US0378331005").is_empty());
}

#[test]
fn load_missing_meta_is_ok() {
    let registry = Registry::from_value(json!({"actions": []})).expect("missing meta ok");
    assert_eq!(registry.meta().version, None);
    assert_eq!(registry.meta().source, None);
}

#[test]
fn load_null_meta_is_ok() {
    let registry =
        Registry::from_value(json!({"actions": [], "meta": null})).expect("null meta ok");
    assert_eq!(registry.meta().version, None);
}

// ----------------------------------------------------------------------
// by_isin
// ----------------------------------------------------------------------

#[test]
fn by_isin_returns_correct_actions() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let aapl = registry.by_isin("US0378331005");
    assert_eq!(aapl.len(), 2);
    assert!(aapl
        .iter()
        .all(|a| a.isin.as_deref() == Some("US0378331005")));
}

#[test]
fn by_isin_unknown_returns_empty() {
    let registry = Registry::from_value(sample_data()).unwrap();
    assert!(registry.by_isin("US0000000000").is_empty());
}

#[test]
fn by_isin_is_case_sensitive() {
    let registry = Registry::from_value(sample_data()).unwrap();
    assert!(registry.by_isin("us0378331005").is_empty());
}

#[test]
fn by_isin_preserves_insertion_order() {
    let registry = Registry::from_value(sample_data()).unwrap();
    // Bind the Vec so the &str references inside it stay alive for the
    // duration of the assert.
    let actions = registry.by_isin("US0378331005");
    let ids: Vec<&str> = actions
        .iter()
        .filter_map(|a| a.action_id.as_deref())
        .collect();
    assert_eq!(
        ids,
        vec![
            "US0378331005-DIVIDEND-2024-05-16-0.2500",
            "US0378331005-SPLIT-2020-08-31-4-1",
        ]
    );
}

#[test]
fn by_isin_returns_fresh_vec() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let mut first = registry.by_isin("US0378331005");
    first.clear();
    let second = registry.by_isin("US0378331005");
    assert_eq!(second.len(), 2);
}

// ----------------------------------------------------------------------
// by_action_id
// ----------------------------------------------------------------------

#[test]
fn by_action_id_found() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let action = registry
        .by_action_id("US67066G1040-SPLIT-2024-06-10-10-1")
        .expect("found");
    assert_eq!(action.action_type.as_deref(), Some("SPLIT"));
    assert_eq!(action.ratio.as_deref(), Some("10:1"));
}

#[test]
fn by_action_id_not_found_returns_none() {
    let registry = Registry::from_value(sample_data()).unwrap();
    assert!(registry.by_action_id("NONEXISTENT").is_none());
}

#[test]
fn by_action_id_returns_deep_copy_of_top_level_fields() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let mut action = registry
        .by_action_id("US67066G1040-SPLIT-2024-06-10-10-1")
        .unwrap();
    action.ratio = Some("999:1".into());
    let again = registry
        .by_action_id("US67066G1040-SPLIT-2024-06-10-10-1")
        .unwrap();
    assert_eq!(again.ratio.as_deref(), Some("10:1"));
}

#[test]
fn by_action_id_returns_deep_copy_of_dates() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let mut action = registry
        .by_action_id("US67066G1040-SPLIT-2024-06-10-10-1")
        .unwrap();
    if let Some(d) = action.dates.as_mut() {
        d.ex_date = Some("1900-01-01".into());
    }
    let again = registry
        .by_action_id("US67066G1040-SPLIT-2024-06-10-10-1")
        .unwrap();
    assert_eq!(again.dates.unwrap().ex_date.as_deref(), Some("2024-06-10"));
}

#[test]
fn by_action_id_returns_deep_copy_of_provenance() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let mut action = registry
        .by_action_id("US0378331005-DIVIDEND-2024-05-16-0.2500")
        .unwrap();
    if let Some(p) = action.provenance.as_mut() {
        p.source = Some("mutated".into());
    }
    let again = registry
        .by_action_id("US0378331005-DIVIDEND-2024-05-16-0.2500")
        .unwrap();
    assert_eq!(again.provenance.unwrap().source.as_deref(), Some("Apple"));
}

#[test]
fn by_action_id_returns_deep_copy_of_impact() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let mut action = registry
        .by_action_id("US0378331005-DIVIDEND-2024-05-16-0.2500")
        .unwrap();
    if let Some(i) = action.impact.as_mut() {
        i.cash_adjustment = Some(999.0);
    }
    let again = registry
        .by_action_id("US0378331005-DIVIDEND-2024-05-16-0.2500")
        .unwrap();
    assert_eq!(again.impact.unwrap().cash_adjustment, Some(0.25));
}

// ----------------------------------------------------------------------
// by_action_type
// ----------------------------------------------------------------------

#[test]
fn by_action_type_returns_all_of_type() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let splits = registry.by_action_type("SPLIT");
    assert_eq!(splits.len(), 2);
    assert!(splits
        .iter()
        .all(|a| a.action_type.as_deref() == Some("SPLIT")));
}

#[test]
fn by_action_type_dividends() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let divs = registry.by_action_type("DIVIDEND");
    assert_eq!(divs.len(), 1);
    assert_eq!(divs[0].amount, Some(0.25));
}

#[test]
fn by_action_type_unknown_returns_empty() {
    let registry = Registry::from_value(sample_data()).unwrap();
    assert!(registry.by_action_type("MERGER").is_empty());
}

#[test]
fn by_action_type_is_case_sensitive() {
    let registry = Registry::from_value(sample_data()).unwrap();
    assert!(registry.by_action_type("split").is_empty());
}

#[test]
fn by_action_type_returns_fresh_vec() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let mut first = registry.by_action_type("SPLIT");
    first.clear();
    let second = registry.by_action_type("SPLIT");
    assert_eq!(second.len(), 2);
}

// ----------------------------------------------------------------------
// by_date_range
// ----------------------------------------------------------------------

#[test]
fn by_date_range_ex_date() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry
        .by_date_range(Some("2020-01-01"), Some("2023-12-31"), "ex_date")
        .unwrap();
    assert_eq!(actions.len(), 1);
    assert_eq!(
        actions[0].action_id.as_deref(),
        Some("US0378331005-SPLIT-2020-08-31-4-1")
    );
}

#[test]
fn by_date_range_effective_date() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry
        .by_date_range(Some("2020-01-01"), Some("2023-12-31"), "effective_date")
        .unwrap();
    assert_eq!(actions.len(), 2);
    let ids: Vec<&str> = actions
        .iter()
        .filter_map(|a| a.action_id.as_deref())
        .collect();
    assert!(ids.contains(&"US0378331005-SPLIT-2020-08-31-4-1"));
    assert!(ids.contains(&"US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL"));
}

#[test]
fn by_date_range_announcement() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry
        .by_date_range(Some("2022-01-01"), Some("2023-12-31"), "announcement")
        .unwrap();
    assert_eq!(actions.len(), 1);
    assert_eq!(
        actions[0].action_id.as_deref(),
        Some("US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL")
    );
}

#[test]
fn by_date_range_record_date() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry
        .by_date_range(Some("2020-01-01"), Some("2024-12-31"), "record_date")
        .unwrap();
    // Three of four have record_date; SYMBOL_CHANGE does not.
    assert_eq!(actions.len(), 3);
}

#[test]
fn by_date_range_invalid_field_returns_err() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let result = registry.by_date_range(None, None, "invalid_field");
    match result {
        Err(RegistryError::InvalidDateField(field)) => {
            assert_eq!(field, "invalid_field");
        }
        Err(other) => panic!("expected InvalidDateField, got {:?}", other),
        Ok(_) => panic!("expected an error, got Ok"),
    }
}

#[test]
fn by_date_range_invalid_field_error_names_value() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let err = registry
        .by_date_range(None, None, "exdate")
        .expect_err("expected an error");
    assert!(err.to_string().contains("exdate"), "got: {}", err);
}

#[test]
fn by_date_range_invalid_field_loops_over_candidates() {
    let registry = Registry::from_value(sample_data()).unwrap();
    for bad in &[
        "exdate",
        "ex-date",
        "effective",
        "Ex_Date",
        "EX_DATE",
        "",
        " ex_date",
    ] {
        let result = registry.by_date_range(None, None, bad);
        assert!(
            matches!(result, Err(RegistryError::InvalidDateField(_))),
            "expected InvalidDateField for {:?}",
            bad
        );
    }
}

#[test]
fn by_date_range_start_bound_is_inclusive() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry
        .by_date_range(Some("2024-05-16"), Some("2024-12-31"), "ex_date")
        .unwrap();
    let ids: Vec<&str> = actions
        .iter()
        .filter_map(|a| a.action_id.as_deref())
        .collect();
    assert!(ids.contains(&"US0378331005-DIVIDEND-2024-05-16-0.2500"));
}

#[test]
fn by_date_range_end_bound_is_inclusive() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry
        .by_date_range(Some("2020-01-01"), Some("2024-05-16"), "ex_date")
        .unwrap();
    let ids: Vec<&str> = actions
        .iter()
        .filter_map(|a| a.action_id.as_deref())
        .collect();
    assert!(ids.contains(&"US0378331005-DIVIDEND-2024-05-16-0.2500"));
}

#[test]
fn by_date_range_single_day() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry
        .by_date_range(Some("2024-05-16"), Some("2024-05-16"), "ex_date")
        .unwrap();
    assert_eq!(actions.len(), 1);
    assert_eq!(
        actions[0].action_id.as_deref(),
        Some("US0378331005-DIVIDEND-2024-05-16-0.2500")
    );
}

#[test]
fn by_date_range_open_start() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry
        .by_date_range(None, Some("2024-01-01"), "ex_date")
        .unwrap();
    assert_eq!(actions.len(), 1);
    assert_eq!(
        actions[0].action_id.as_deref(),
        Some("US0378331005-SPLIT-2020-08-31-4-1")
    );
}

#[test]
fn by_date_range_open_end() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry
        .by_date_range(Some("2024-01-01"), None, "ex_date")
        .unwrap();
    assert_eq!(actions.len(), 2);
}

#[test]
fn by_date_range_both_open() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry.by_date_range(None, None, "ex_date").unwrap();
    // Three of four have ex_date; SYMBOL_CHANGE does not.
    assert_eq!(actions.len(), 3);
}

#[test]
fn by_date_range_skips_missing_ex_date() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry.by_date_range(None, None, "ex_date").unwrap();
    let ids: Vec<&str> = actions
        .iter()
        .filter_map(|a| a.action_id.as_deref())
        .collect();
    assert!(!ids.contains(&"US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL"));
}

#[test]
fn by_date_range_skips_missing_record_date() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry.by_date_range(None, None, "record_date").unwrap();
    let ids: Vec<&str> = actions
        .iter()
        .filter_map(|a| a.action_id.as_deref())
        .collect();
    assert!(!ids.contains(&"US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL"));
}

#[test]
fn by_date_range_skips_action_with_no_dates_object() {
    let data = json!({
        "actions": [
            {
                "isin": "US1234567890",
                "action_id": "US1234567890-SPLIT-2024-01-01-2-1",
                "action_type": "SPLIT"
                // no dates key at all
            }
        ]
    });
    let registry = Registry::from_value(data).unwrap();
    let actions = registry.by_date_range(None, None, "ex_date").unwrap();
    assert!(actions.is_empty());
}

#[test]
fn by_date_range_sorted_by_ex_date() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry.by_date_range(None, None, "ex_date").unwrap();
    let dates: Vec<&str> = actions
        .iter()
        .filter_map(|a| a.dates.as_ref()?.ex_date.as_deref())
        .collect();
    let mut sorted = dates.clone();
    sorted.sort();
    assert_eq!(dates, sorted);
}

#[test]
fn by_date_range_sorted_by_effective_date() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry
        .by_date_range(None, None, "effective_date")
        .unwrap();
    let dates: Vec<&str> = actions
        .iter()
        .filter_map(|a| a.dates.as_ref()?.effective_date.as_deref())
        .collect();
    let mut sorted = dates.clone();
    sorted.sort();
    assert_eq!(dates, sorted);
}

#[test]
fn by_date_range_tiebreak_on_action_id() {
    let registry = Registry::from_value(tiebreak_data()).unwrap();
    let actions = registry.by_date_range(None, None, "ex_date").unwrap();
    let ids: Vec<&str> = actions
        .iter()
        .filter_map(|a| a.action_id.as_deref())
        .collect();
    assert_eq!(
        ids,
        vec![
            "US0000000001-DIVIDEND-2024-05-16-0.2500",
            "US0000000002-DIVIDEND-2024-05-16-0.3000",
        ]
    );
}

#[test]
fn by_date_range_sorted_regardless_of_input_order() {
    // Reverse the actions before loading.
    let mut data = sample_data();
    if let Some(arr) = data.get_mut("actions").and_then(|v| v.as_array_mut()) {
        arr.reverse();
    }
    let registry = Registry::from_value(data).unwrap();
    let actions = registry.by_date_range(None, None, "ex_date").unwrap();
    let dates: Vec<&str> = actions
        .iter()
        .filter_map(|a| a.dates.as_ref()?.ex_date.as_deref())
        .collect();
    let mut sorted = dates.clone();
    sorted.sort();
    assert_eq!(dates, sorted);
}

#[test]
fn by_date_range_returns_fresh_vec() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let mut first = registry.by_date_range(None, None, "ex_date").unwrap();
    first.clear();
    let second = registry.by_date_range(None, None, "ex_date").unwrap();
    assert_eq!(second.len(), 3);
}

#[test]
fn by_date_range_empty_window_returns_empty() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let actions = registry
        .by_date_range(Some("1900-01-01"), Some("1900-12-31"), "ex_date")
        .unwrap();
    assert!(actions.is_empty());
}

// ----------------------------------------------------------------------
// all_action_types
// ----------------------------------------------------------------------

#[test]
fn all_action_types_sorted_unique() {
    let registry = Registry::from_value(sample_data()).unwrap();
    assert_eq!(
        registry.all_action_types(),
        vec!["DIVIDEND", "SPLIT", "SYMBOL_CHANGE"]
    );
}

#[test]
fn all_action_types_empty_registry() {
    let registry = Registry::from_value(json!({"actions": []})).unwrap();
    assert!(registry.all_action_types().is_empty());
}

#[test]
fn all_action_types_reflects_only_present_types() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let types = registry.all_action_types();
    assert!(!types.iter().any(|t| t == "MERGER"));
    assert!(!types.iter().any(|t| t == "SPINOFF"));
    assert!(!types.iter().any(|t| t == "REVERSE_SPLIT"));
}

// ----------------------------------------------------------------------
// count
// ----------------------------------------------------------------------

#[test]
fn count_returns_total() {
    let registry = Registry::from_value(sample_data()).unwrap();
    assert_eq!(registry.count(), 4);
}

#[test]
fn count_empty_registry() {
    let registry = Registry::from_value(json!({"actions": []})).unwrap();
    assert_eq!(registry.count(), 0);
}

// ----------------------------------------------------------------------
// meta
// ----------------------------------------------------------------------

#[test]
fn meta_fields_loaded() {
    let registry = Registry::from_value(sample_data()).unwrap();
    assert_eq!(registry.meta().version.as_deref(), Some("1.0.0"));
    assert_eq!(registry.meta().source.as_deref(), Some("Test"));
    assert_eq!(
        registry.meta().generated_at.as_deref(),
        Some("2026-09-09T12:00:00Z")
    );
}

#[test]
fn meta_default_when_absent() {
    let registry = Registry::from_value(json!({"actions": []})).unwrap();
    assert_eq!(registry.meta().version, None);
    assert_eq!(registry.meta().source, None);
}

// ----------------------------------------------------------------------
// all_actions
// ----------------------------------------------------------------------

#[test]
fn all_actions_returns_slice_of_all() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let all = registry.all_actions();
    assert_eq!(all.len(), 4);
}

#[test]
fn all_actions_empty_registry() {
    let registry = Registry::from_value(json!({"actions": []})).unwrap();
    assert!(registry.all_actions().is_empty());
}

// ----------------------------------------------------------------------
// to_json / save
// ----------------------------------------------------------------------

#[test]
fn to_json_has_two_top_level_keys() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let value = registry.to_json();
    let obj = value.as_object().expect("object");
    assert_eq!(obj.len(), 2, "expected exactly two top-level keys");
    assert!(obj.contains_key("meta"));
    assert!(obj.contains_key("actions"));
}

#[test]
fn to_json_preserves_fields() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let value = registry.to_json();
    assert_eq!(value["meta"]["version"], "1.0.0");
    let actions = value["actions"].as_array().expect("array");
    assert_eq!(actions.len(), 4);
    assert_eq!(actions[0]["isin"], "US67066G1040");
}

#[test]
fn to_json_and_from_value_roundtrip() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let json_value = registry.to_json();
    let registry2 = Registry::from_value(json_value).expect("roundtrip");
    assert_eq!(registry.count(), registry2.count());
    assert_eq!(registry.meta().version, registry2.meta().version);
    assert_eq!(
        serde_json::to_value(registry.to_json()).unwrap(),
        serde_json::to_value(registry2.to_json()).unwrap()
    );
}

#[test]
fn save_and_reload_from_file() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let path = write_temp_file("out.json", b"");
    registry.save(&path).expect("save");
    let loaded = Registry::load_from_file(&path).expect("reload");
    assert_eq!(loaded.count(), registry.count());
    assert_eq!(loaded.meta().version, registry.meta().version);
    remove_temp_file(&path);
}

#[test]
fn save_produces_valid_json() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let path = write_temp_file("valid.json", b"");
    registry.save(&path).expect("save");
    let content = fs::read_to_string(&path).expect("read");
    let parsed: serde_json::Value = serde_json::from_str(&content).expect("parse");
    assert!(parsed.get("meta").is_some());
    assert!(parsed.get("actions").is_some());
    remove_temp_file(&path);
}

#[test]
fn save_writes_no_bom() {
    let registry = Registry::from_value(sample_data()).unwrap();
    let path = write_temp_file("nobom.json", b"");
    registry.save(&path).expect("save");
    let bytes = fs::read(&path).expect("read");
    assert!(
        !(bytes.len() >= 3 && bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF),
        "saved file carries a BOM"
    );
    remove_temp_file(&path);
}

#[test]
fn save_empty_registry_round_trips() {
    let registry = Registry::from_value(json!({"actions": []})).unwrap();
    let path = write_temp_file("empty_out.json", b"");
    registry.save(&path).expect("save");
    let loaded = Registry::load_from_file(&path).expect("reload");
    assert_eq!(loaded.count(), 0);
    remove_temp_file(&path);
}

// ----------------------------------------------------------------------
// RegistryError display
// ----------------------------------------------------------------------

#[test]
fn invalid_date_field_error_displays_offending_value() {
    let err = RegistryError::InvalidDateField("exdate".into());
    assert_eq!(err.to_string(), "invalid date_field: exdate");
}

#[test]
fn invalid_structure_error_displays_message() {
    let err = RegistryError::InvalidStructure("missing 'actions' key".into());
    assert_eq!(
        err.to_string(),
        "invalid registry structure: missing 'actions' key"
    );
}

#[test]
fn by_ticker_resolves() {
    corporate_actions_registry::reset_cache();
    let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/fixtures/identifiers.json");
    if !path.exists() {
        eprintln!("skipping: fixture missing");
        return;
    }
    let doc = serde_json::json!({"actions": [
        {"isin": "US0000000002", "action_id": "X", "action_type": "DIVIDEND"},
    ]});
    let r = Registry::from_value(doc).unwrap();
    let got = r
        .by_ticker("TESTB", "XNAS", Some(path.to_str().unwrap()))
        .unwrap();
    assert_eq!(got.len(), 1);
    assert_eq!(got[0].isin.as_deref(), Some("US0000000002"));
}

#[test]
fn by_ticker_case_insensitive() {
    corporate_actions_registry::reset_cache();
    let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/fixtures/identifiers.json");
    if !path.exists() {
        eprintln!("skipping: fixture missing");
        return;
    }
    let r = Registry::from_value(serde_json::json!({"actions": []})).unwrap();
    let a = r
        .by_ticker("testb", "xnas", Some(path.to_str().unwrap()))
        .unwrap();
    let b = r
        .by_ticker("TESTB", "XNAS", Some(path.to_str().unwrap()))
        .unwrap();
    assert_eq!(a.len(), b.len());
}

#[test]
fn by_ticker_unknown_returns_empty() {
    let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/fixtures/identifiers.json");
    if !path.exists() {
        eprintln!("skipping: fixture missing");
        return;
    }
    let r = Registry::from_value(serde_json::json!({"actions": []})).unwrap();
    let got = r
        .by_ticker("NOTREAL", "XNAS", Some(path.to_str().unwrap()))
        .unwrap();
    assert!(got.is_empty());
}

#[test]
fn by_ticker_missing_file_returns_missing_data() {
    let r = Registry::from_value(serde_json::json!({"actions": []})).unwrap();
    let err = r
        .by_ticker("TESTB", "XNAS", Some("/nonexistent/identifiers.json"))
        .unwrap_err();
    assert!(err.to_string().contains("missing identifier data"));
}

#[test]
fn by_ticker_unknown_exchange_returns_empty() {
    let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/fixtures/identifiers.json");
    if !path.exists() {
        eprintln!("skipping: fixture missing");
        return;
    }
    let r = Registry::from_value(serde_json::json!({"actions": []})).unwrap();
    let got = r
        .by_ticker("TESTB", "NOTEXCH", Some(path.to_str().unwrap()))
        .unwrap();
    assert!(got.is_empty());
}
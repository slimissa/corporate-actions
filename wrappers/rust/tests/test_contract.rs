//! Contract tests for the Rust wrapper.
//!
//! These tests read `tests/wrapper_contract.json` and verify that this
//! wrapper's `by_date_range` agrees with the shared fixture. The same
//! fixture is read by the Python, JavaScript, and Go wrappers, so a
//! regression in any one wrapper shows up in all four suites.
//!
//! The fixture at `tests/wrapper_contract.json` is committed to the
//! repository and read by all four wrappers. A missing fixture panics
//! rather than skipping: a broken checkout must fail loudly, not
//! silently hide the contract tests.
//!
//! Fixture shape is specified in `docs/wrapper_contract.md` section 8.2.
//!
//! Run:
//!     cargo test --test test_contract

use corporate_actions_registry::{Action, Registry, RegistryError};
use serde::Deserialize;
use serde_json::json;
use std::fs;
use std::path::Path;

/// Path to the shared fixture, resolved from this test file's directory.
///
/// `wrappers/rust/tests/test_contract.rs` → repo root is three levels up.
/// Path to the shared fixture, resolved relative to this crate's root.
///
/// `CARGO_MANIFEST_DIR` is `wrappers/rust/`, so `../../tests/` climbs
/// to the repository root. Using the compile-time variable rather than
/// a runtime-relative path means the test works regardless of cwd.
const FIXTURE_PATH: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../tests/wrapper_contract.json"
);

/// One query entry from the fixture.
#[derive(Debug, Deserialize)]
struct ContractQuery {
    date_field: String,
    #[serde(default)]
    start: Option<String>,
    #[serde(default)]
    end: Option<String>,
    expected_action_ids: Vec<String>,
}

/// The full shape of `tests/wrapper_contract.json`.
///
/// Actions are deserialized directly into the crate's `Action` type.
/// That is deliberate: if the fixture ever carries an action shape the
/// crate cannot parse, the failure surfaces here rather than in a
/// language-specific adapter.
#[derive(Debug, Deserialize)]
struct ContractFixture {
    actions: Vec<Action>,
    queries: Vec<ContractQuery>,
    #[serde(default)]
    invalid_date_fields: Vec<String>,
}

/// Load the fixture, or return `None` if it is absent.
///
/// A missing fixture causes the calling test to return early with a
/// message on stderr. A malformed fixture is a panic: that is a bug in
/// the fixture, not a reason to skip.
fn load_fixture() -> ContractFixture {
    let path = Path::new(FIXTURE_PATH);
    if !path.exists() {
        panic!("contract fixture required but missing: {}", FIXTURE_PATH);
    }
    let content =
        fs::read_to_string(path).unwrap_or_else(|e| panic!("read fixture {}: {}", FIXTURE_PATH, e));
    serde_json::from_str(&content)
        .unwrap_or_else(|e| panic!("parse fixture {}: {}", FIXTURE_PATH, e))
}

/// Build a `Registry` from the fixture's actions.
///
/// Goes through `Registry::from_value`, so the loader is exercised as
/// part of the contract check. A bug in the loader surfaces here rather
/// than hiding behind a hand-built registry.
fn build_registry(fixture: &ContractFixture) -> Registry {
    let doc = json!({
        "meta": {},
        "actions": fixture.actions,
    });
    match Registry::from_value(doc) {
        Ok(r) => r,
        Err(e) => panic!("loader rejected fixture actions: {:?}", e),
    }
}

/// Extract the `action_id` of every action, using an empty string for
/// a missing ID so the result is always comparable.
fn action_ids(actions: &[Action]) -> Vec<String> {
    actions
        .iter()
        .map(|a| a.action_id.clone().unwrap_or_default())
        .collect()
}

// ----------------------------------------------------------------------
// Shape
// ----------------------------------------------------------------------

#[test]
fn contract_fixture_shape_is_valid() {
    let fixture = load_fixture();

    assert!(!fixture.actions.is_empty(), "fixture has no actions");
    assert!(!fixture.queries.is_empty(), "fixture has no queries");
    assert!(
        !fixture.invalid_date_fields.is_empty(),
        "fixture has no invalid_date_fields"
    );

    for (i, a) in fixture.actions.iter().enumerate() {
        assert!(a.action_id.is_some(), "action {} missing action_id", i);
        assert!(a.isin.is_some(), "action {} missing isin", i);
    }

    for (i, q) in fixture.queries.iter().enumerate() {
        assert!(!q.date_field.is_empty(), "query {} missing date_field", i);
    }
}

#[test]
fn contract_fixture_is_self_consistent() {
    let fixture = load_fixture();

    let known: std::collections::HashSet<&str> = fixture
        .actions
        .iter()
        .filter_map(|a| a.action_id.as_deref())
        .collect();

    for (i, q) in fixture.queries.iter().enumerate() {
        let mut seen = std::collections::HashSet::new();
        for id in &q.expected_action_ids {
            assert!(
                known.contains(id.as_str()),
                "query {}: expected action_id {:?} is not in the fixture's actions",
                i,
                id
            );
            assert!(
                seen.insert(id.as_str()),
                "query {}: action_id {:?} appears twice in expected_action_ids",
                i,
                id
            );
        }
    }
}

// ----------------------------------------------------------------------
// Queries
// ----------------------------------------------------------------------

#[test]
fn contract_queries_match() {
    let fixture = load_fixture();
    let registry = build_registry(&fixture);

    for (i, q) in fixture.queries.iter().enumerate() {
        let result = registry.by_date_range(q.start.as_deref(), q.end.as_deref(), &q.date_field);
        let actions = match result {
            Ok(a) => a,
            Err(e) => panic!(
                "query {} (field {:?}, start {:?}, end {:?}) returned error: {}",
                i, q.date_field, q.start, q.end, e
            ),
        };
        let got = action_ids(&actions);
        assert_eq!(
            got, q.expected_action_ids,
            "query {} (field {:?}, start {:?}, end {:?})",
            i, q.date_field, q.start, q.end
        );
    }
}

// ----------------------------------------------------------------------
// Invalid fields
// ----------------------------------------------------------------------

#[test]
fn contract_invalid_date_fields_rejected() {
    let fixture = load_fixture();
    let registry = build_registry(&fixture);

    for bad in &fixture.invalid_date_fields {
        let result = registry.by_date_range(None, None, bad);
        match result {
            Err(RegistryError::InvalidDateField(field)) => {
                assert_eq!(&field, bad, "error carried {:?}, expected {:?}", field, bad);
            }
            Err(other) => panic!(
                "field {:?}: expected InvalidDateField, got {:?}",
                bad, other
            ),
            Ok(_) => panic!("field {:?}: expected an error, got Ok", bad),
        }
    }
}


// ----------------------------------------------------------------------
// adjust_prices (wrapper contract § 4.10)
// ----------------------------------------------------------------------

#[test]
fn adjust_prices_matches_fixture() {
    use corporate_actions_registry::{AdjustedBar, PriceBar, Registry};
    use std::fs;

    let manifest = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
    let root = manifest.parent().unwrap().parent().unwrap();
    let fixture_path = root.join("tests").join("wrapper_contract.json");
    let content = fs::read_to_string(&fixture_path).expect("fixture must exist");
    let data: serde_json::Value = serde_json::from_str(&content).unwrap();

    let actions_json = data["actions"].clone();
    let reg = Registry::from_value(serde_json::json!({ "actions": actions_json })).unwrap();

    let cases = data["price_adjustments"]
        .as_array()
        .expect("price_adjustments must be an array");
    assert!(!cases.is_empty(), "fixture must have price_adjustments cases");

    for c in cases {
        let isin = c
            .get("override_isin")
            .and_then(|v| v.as_str())
            .or_else(|| c.get("isin").and_then(|v| v.as_str()))
            .expect("case must have isin or override_isin");

        let prices: Vec<PriceBar> =
            serde_json::from_value(c["prices"].clone()).expect("prices parse");
        let expected: Vec<AdjustedBar> =
            serde_json::from_value(c["expected"].clone()).expect("expected parse");

        let result = reg
            .adjust_prices(isin, &prices, None)
            .expect("adjust_prices should succeed");

        assert_eq!(
            result, expected,
            "case: {}",
            c.get("description").and_then(|v| v.as_str()).unwrap_or("?")
        );
    }
}

#[test]
fn adjust_prices_unknown_isin_returns_empty() {
    use corporate_actions_registry::{PriceBar, Registry};
    let reg = Registry::from_value(serde_json::json!({ "actions": [] })).unwrap();
    let prices = vec![PriceBar { date: "2024-01-15".into(), raw: 100.0 }];
    let out = reg.adjust_prices("US9999999999", &prices, None).unwrap();
    assert!(out.is_empty());
}

#[test]
fn adjust_prices_rejects_malformed_date() {
    use corporate_actions_registry::{PriceBar, Registry};
    let reg = Registry::from_value(serde_json::json!({ "actions": [
        {"isin": "X", "action_id": "X-SPLIT", "action_type": "SPLIT"}
    ]})).unwrap();
    let prices = vec![PriceBar { date: "2024-6-10".into(), raw: 100.0 }];
    let err = reg.adjust_prices("X", &prices, None).unwrap_err();
    assert!(err.to_string().contains("invalid price"), "unexpected: {}", err);
}

//! Contract tests for the Rust wrapper.
//!
//! These tests read `tests/wrapper_contract.json` and verify that this
//! wrapper's `by_date_range` agrees with the shared fixture. The same
//! fixture is read by the Python, JavaScript, and Go wrappers, so a
//! regression in any one wrapper shows up in all four suites.
//!
//! The fixture is not yet in the repository; it arrives in Session 3.5.
//! Until it does, every test in this file returns early with a message
//! on stderr. Rust's test framework has no `skip` attribute, so the
//! early-return is the idiomatic substitute. Once the fixture is added,
//! no change to this file is required.
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
const FIXTURE_PATH: &str = "../../../tests/wrapper_contract.json";

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
fn load_fixture() -> Option<ContractFixture> {
    let path = Path::new(FIXTURE_PATH);
    if !path.exists() {
        eprintln!(
            "skipping: contract fixture not found at {} (Session 3.5 adds it)",
            FIXTURE_PATH
        );
        return None;
    }
    let content = fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("read fixture {}: {}", FIXTURE_PATH, e));
    let fixture: ContractFixture = serde_json::from_str(&content)
        .unwrap_or_else(|e| panic!("parse fixture {}: {}", FIXTURE_PATH, e));
    Some(fixture)
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
    Registry::from_value(doc).expect("loader accepts fixture actions")
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
    let fixture = match load_fixture() {
        Some(f) => f,
        None => return,
    };

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
        assert!(
            !q.date_field.is_empty(),
            "query {} missing date_field",
            i
        );
    }
}

#[test]
fn contract_fixture_is_self_consistent() {
    let fixture = match load_fixture() {
        Some(f) => f,
        None => return,
    };

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
    let fixture = match load_fixture() {
        Some(f) => f,
        None => return,
    };
    let registry = build_registry(&fixture);

    for (i, q) in fixture.queries.iter().enumerate() {
        let result = registry.by_date_range(
            q.start.as_deref(),
            q.end.as_deref(),
            &q.date_field,
        );
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
    let fixture = match load_fixture() {
        Some(f) => f,
        None => return,
    };
    let registry = build_registry(&fixture);

    for bad in &fixture.invalid_date_fields {
        let result = registry.by_date_range(None, None, bad);
        match result {
            Err(RegistryError::InvalidDateField(field)) => {
                assert_eq!(
                    &field, bad,
                    "error carried {:?}, expected {:?}",
                    field, bad
                );
            }
            Err(other) => panic!(
                "field {:?}: expected InvalidDateField, got {:?}",
                bad, other
            ),
            Ok(_) => panic!(
                "field {:?}: expected an error, got Ok",
                bad
            ),
        }
    }
}
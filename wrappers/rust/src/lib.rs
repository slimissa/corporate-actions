//! Corporate Actions Registry Rust Wrapper
//!
//! This crate provides a typed, dependency-light interface to load and
//! query the Corporate Actions Registry (`actions.json`). It builds
//! in-memory indexes for fast lookups by ISIN, action ID, action type,
//! and ticker, and supports date-range filtering.
//!
//! The behaviour of every public method is specified by
//! `docs/wrapper_contract.md`. When the code disagrees with that
//! document, the code is wrong.
//!
//! # Example
//!
//! ```rust,no_run
//! use corporate_actions_registry::Registry;
//!
//! # fn main() -> Result<(), Box<dyn std::error::Error>> {
//! let registry = Registry::load_from_file("actions.json")?;
//! let aapl_actions = registry.by_isin("US0378331005");
//! for action in aapl_actions {
//!     println!("{:?} {:?}", action.action_type, action.dates);
//! }
//! # Ok(())
//! # }
//! ```

mod ticker_index;

// Re-export the test helper so external integration tests can reset the
// per-path ticker index cache. See docs/wrapper_contract.md section 8.3.
pub use ticker_index::reset_cache;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::Path;

// ---------------------------------------------------------------------------
// Exported constants (wrapper contract section 4.9)
// ---------------------------------------------------------------------------

/// The value the Python and JavaScript wrappers use when the
/// `date_field` argument to `by_date_range` is omitted. Rust requires
/// the argument; use this constant rather than hard-coding the string.
pub const DEFAULT_DATE_FIELD: &str = "ex_date";

/// The closed set of date field names accepted by
/// [`Registry::by_date_range`]. Callers who want to enumerate the
/// choices should read this slice rather than duplicating the list.
pub const VALID_DATE_FIELDS: &[&str] = &[
    "announcement",
    "ex_date",
    "record_date",
    "effective_date",
];

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/// Errors that can occur when loading or using the registry.
///
/// This enum is `#[non_exhaustive]`: new variants may be added in a
/// minor release, so downstream `match` statements must include a
/// wildcard arm.
#[non_exhaustive]
#[derive(Debug, thiserror::Error)]
pub enum RegistryError {
    /// An I/O failure while reading or writing a file.
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    /// A JSON parse or serialization failure.
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),

    /// The document does not have the required structure: missing
    /// `actions` key, `actions` not an array, an entry in `actions`
    /// that is not a JSON object, an action missing both `isin` and
    /// `action_id`, or two actions sharing an `action_id`.
    #[error("invalid registry structure: {0}")]
    InvalidStructure(String),

    /// The `date_field` argument to [`Registry::by_date_range`] is not
    /// one of `announcement`, `ex_date`, `record_date`, or
    /// `effective_date`. The contained string is the offending value.
    #[error("invalid date_field: {0}")]
    InvalidDateField(String),

    /// The Asset Identifiers file required by [`Registry::by_ticker`]
    /// could not be resolved or read. The contained string names the
    /// environment variable that would fix it.
    #[error("missing identifier data: {0}")]
    MissingData(String),
}

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

/// Represents the dates of a corporate action. Every field is optional.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Dates {
    pub announcement: Option<String>,
    pub ex_date: Option<String>,
    pub record_date: Option<String>,
    pub effective_date: Option<String>,
}

/// Source and verification information for an action.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Provenance {
    pub source: Option<String>,
    pub source_url: Option<String>,
    pub verification_source: Option<String>,
    pub verification_url: Option<String>,
}

/// Financial impact multipliers for backtesting.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Impact {
    pub price_multiplier: Option<f64>,
    pub share_multiplier: Option<f64>,
    pub cash_adjustment: Option<f64>,
}

/// A single corporate action entry.
///
/// `PartialEq` is derived so consumers can compare two actions in their
/// own tests. `Eq` is not derivable because `amount` is an `f64`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Action {
    pub isin: Option<String>,
    pub action_id: Option<String>,
    pub action_type: Option<String>,
    pub ratio: Option<String>,
    pub amount: Option<f64>,
    pub currency: Option<String>,
    pub dates: Option<Dates>,
    pub status: Option<String>,
    pub provenance: Option<Provenance>,
    pub impact: Option<Impact>,
}

/// Metadata about the registry file.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Meta {
    pub version: Option<String>,
    pub generated_at: Option<String>,
    pub source: Option<String>,
    pub notes: Option<String>,
}

/// Return the requested date from an action, or `None` if the action has
/// no dates object or the requested field is absent.
///
/// Extracted from `by_date_range` because Rust closures cannot express
/// the "output borrows from input" relationship that the elided lifetime
/// on `Option<&str>` requires. A free function with explicit lifetimes
/// can.
fn date_field_value<'a>(action: &'a Action, date_field: &str) -> Option<&'a str> {
    let dates = action.dates.as_ref()?;
    match date_field {
        "announcement" => dates.announcement.as_deref(),
        "ex_date" => dates.ex_date.as_deref(),
        "record_date" => dates.record_date.as_deref(),
        "effective_date" => dates.effective_date.as_deref(),
        _ => None,
    }
}

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

/// The main registry container.
///
/// A `Registry` is immutable after construction. Every lookup returns a
/// fresh `Vec` or a fresh `Action` clone, so a caller cannot corrupt the
/// registry's internal state by mutating a returned value.
#[derive(Debug)]
pub struct Registry {
    meta: Meta,
    actions: Vec<Action>,

    // Indexes. Each maps a key to one or more positions in `actions`.
    // Positions are stable for the lifetime of the `Registry`.
    index_isin: HashMap<String, Vec<usize>>,
    index_type: HashMap<String, Vec<usize>>,
    index_id: HashMap<String, usize>,
}

impl Registry {
    /// Load the registry from a JSON file.
    ///
    /// A UTF-8 BOM at the start of the file is ignored. Any other
    /// leading bytes are passed through to `serde_json::from_str`.
    pub fn load_from_file<P: AsRef<Path>>(path: P) -> Result<Self, RegistryError> {
        let content = fs::read_to_string(path)?;
        // Strip a leading UTF-8 BOM if present. `serde_json::from_str`
        // rejects it otherwise.
        let content = content.strip_prefix('\u{FEFF}').unwrap_or(&content);
        let data: serde_json::Value = serde_json::from_str(content)?;
        Self::from_value(data)
    }

    /// Build the registry from an already-parsed JSON value.
    ///
    /// The document must be an object with an `actions` array. The
    /// `meta` object is optional. Each entry in `actions` must itself be
    /// a JSON object; a string, number, boolean, null, or array entry is
    /// a structural error, reported with its index.
    ///
    /// Structural validation, before any index is built:
    ///
    ///   - Every entry must carry at least one of `isin` or `action_id`.
    ///   - No two entries may share a non-empty `action_id`.
    pub fn from_value(data: serde_json::Value) -> Result<Self, RegistryError> {
        // Extract meta (optional).
        let meta: Meta = match data.get("meta") {
            Some(m) if !m.is_null() => serde_json::from_value(m.clone())?,
            _ => Meta::default(),
        };

        // Extract the actions array.
        let actions_value = data
            .get("actions")
            .ok_or_else(|| RegistryError::InvalidStructure("missing 'actions' key".into()))?;
        let actions_array = actions_value
            .as_array()
            .ok_or_else(|| RegistryError::InvalidStructure("'actions' must be an array".into()))?;

        let mut actions = Vec::with_capacity(actions_array.len());
        let mut seen_ids: HashMap<String, usize> = HashMap::new();

        for (idx, item) in actions_array.iter().enumerate() {
            // Reject anything that is not a JSON object before attempting
            // to deserialize into `Action`. This gives a clearer message
            // than serde's "invalid type" default.
            if !item.is_object() {
                return Err(RegistryError::InvalidStructure(format!(
                    "action at index {} is not an object",
                    idx
                )));
            }

            let action: Action = serde_json::from_value(item.clone()).map_err(|e| {
                RegistryError::InvalidStructure(format!("invalid action at index {}: {}", idx, e))
            })?;

            // Duplicate action_id check (wrapper contract section 5.5).
            if let Some(id) = action.action_id.as_deref() {
                if !id.is_empty() {
                    if let Some(&prev) = seen_ids.get(id) {
                        return Err(RegistryError::InvalidStructure(format!(
                            "duplicate action_id at index {}: {} (first seen at index {})",
                            idx, id, prev
                        )));
                    }
                    seen_ids.insert(id.to_string(), idx);
                }
            }

            // Missing-identifier check (wrapper contract section 5.6).
            let has_isin = action.isin.as_deref().map_or(false, |s| !s.is_empty());
            let has_id = action.action_id.as_deref().map_or(false, |s| !s.is_empty());
            if !has_isin && !has_id {
                return Err(RegistryError::InvalidStructure(format!(
                    "action at index {} has neither 'isin' nor 'action_id'",
                    idx
                )));
            }

            actions.push(action);
        }

        // Build the indexes.
        let mut index_isin: HashMap<String, Vec<usize>> = HashMap::new();
        let mut index_type: HashMap<String, Vec<usize>> = HashMap::new();
        let mut index_id: HashMap<String, usize> = HashMap::new();

        for (i, action) in actions.iter().enumerate() {
            if let Some(isin) = &action.isin {
                index_isin.entry(isin.clone()).or_default().push(i);
            }
            if let Some(action_type) = &action.action_type {
                index_type.entry(action_type.clone()).or_default().push(i);
            }
            if let Some(id) = &action.action_id {
                // The loader already rejected duplicates, so a plain
                // insert is safe here.
                index_id.insert(id.clone(), i);
            }
        }

        Ok(Registry {
            meta,
            actions,
            index_isin,
            index_type,
            index_id,
        })
    }

    /// Return all actions for a given ISIN.
    ///
    /// Returns an empty vector when no action matches. Matching is exact
    /// and case-sensitive.
    pub fn by_isin(&self, isin: &str) -> Vec<Action> {
        self.index_isin
            .get(isin)
            .map(|indices| indices.iter().map(|&i| self.actions[i].clone()).collect())
            .unwrap_or_default()
    }

    /// Return a single action by its unique `action_id`, or `None` when
    /// no action matches. Matching is exact and case-sensitive.
    ///
    /// The returned `Action` is a fresh clone; mutating it does not
    /// affect the registry.
    pub fn by_action_id(&self, action_id: &str) -> Option<Action> {
        self.index_id
            .get(action_id)
            .map(|&i| self.actions[i].clone())
    }

    /// Return all actions of a given type (e.g., `"SPLIT"`,
    /// `"DIVIDEND"`). Matching is exact and case-sensitive.
    pub fn by_action_type(&self, action_type: &str) -> Vec<Action> {
        self.index_type
            .get(action_type)
            .map(|indices| indices.iter().map(|&i| self.actions[i].clone()).collect())
            .unwrap_or_default()
    }

    /// Return actions whose `date_field` falls in the inclusive range
    /// `[start_date, end_date]`.
    ///
    /// `date_field` must be one of [`VALID_DATE_FIELDS`]. Any other
    /// value returns [`RegistryError::InvalidDateField`].
    ///
    /// A `None` or empty-string bound means "no bound on that side".
    /// Actions whose `date_field` is absent (or whose `dates` object is
    /// `None`) are silently skipped. Dates are compared as ISO-8601
    /// strings, so lexicographic comparison is chronological.
    ///
    /// The result is sorted by `(date_field, action_id)`, ascending.
    pub fn by_date_range(
        &self,
        start_date: Option<&str>,
        end_date: Option<&str>,
        date_field: &str,
    ) -> Result<Vec<Action>, RegistryError> {
        if !VALID_DATE_FIELDS.contains(&date_field) {
            return Err(RegistryError::InvalidDateField(date_field.into()));
        }

        // Empty string is treated the same as None: "no bound on that side".
        let start = start_date.filter(|s| !s.is_empty());
        let end = end_date.filter(|s| !s.is_empty());

        let mut result: Vec<Action> = self
            .actions
            .iter()
            .filter(|a| {
                let v = match date_field_value(a, date_field) {
                    Some(v) => v,
                    None => return false,
                };
                if let Some(s) = start {
                    if v < s {
                        return false;
                    }
                }
                if let Some(e) = end {
                    if v > e {
                        return false;
                    }
                }
                true
            })
            .cloned()
            .collect();

        result.sort_by(|a, b| {
            let av = date_field_value(a, date_field).unwrap_or("");
            let bv = date_field_value(b, date_field).unwrap_or("");
            av.cmp(bv).then_with(|| a.action_id.cmp(&b.action_id))
        });

        Ok(result)
    }

    /// Return all actions for a ticker on an exchange.
    ///
    /// Resolves `(ticker, exchange)` to an ISIN using the Asset
    /// Identifiers registry, then returns the same list as
    /// [`Self::by_isin`].
    ///
    /// Path resolution when `identifiers_path` is `None` or empty:
    ///
    ///   1. `$CORP_ACTIONS_IDENTIFIERS_PATH`
    ///   2. `$LAS_DATA_HOME/identifiers.json`
    ///
    /// Ticker and exchange are uppercased before lookup. An unknown
    /// `(ticker, exchange)` pair returns an empty vector, not an error.
    /// A missing identifiers file returns
    /// [`RegistryError::MissingData`].
    ///
    /// See `docs/wrapper_contract.md` section 4.8.
    pub fn by_ticker(
        &self,
        ticker: &str,
        exchange: &str,
        identifiers_path: Option<&str>,
    ) -> Result<Vec<Action>, RegistryError> {
        match ticker_index::lookup(ticker, exchange, identifiers_path)? {
            Some(isin) => Ok(self.by_isin(&isin)),
            None => Ok(Vec::new()),
        }
    }

    /// Return a sorted list of all unique action types present in the
    /// registry. Reserved types that are not in the data do not appear.
    pub fn all_action_types(&self) -> Vec<String> {
        let mut types: Vec<String> = self.index_type.keys().cloned().collect();
        types.sort();
        types
    }

    /// Return the total number of actions.
    pub fn count(&self) -> usize {
        self.actions.len()
    }

    /// Return a slice of all actions, for iteration and inspection.
    ///
    /// The slice borrows the registry's internal state; consumers who
    /// need to mutate a returned action must use [`Self::by_action_id`]
    /// instead, which returns a fresh clone.
    pub fn all_actions(&self) -> &[Action] {
        &self.actions
    }

    /// Return a reference to the registry metadata.
    pub fn meta(&self) -> &Meta {
        &self.meta
    }

    /// Convert the registry to a JSON value with exactly two top-level
    /// keys: `"meta"` and `"actions"`.
    pub fn to_json(&self) -> serde_json::Value {
        serde_json::json!({
            "meta": self.meta,
            "actions": self.actions,
        })
    }

    /// Save the registry to a file as pretty-printed JSON.
    ///
    /// The output is UTF-8 without a BOM. Any existing file at the same
    /// path is overwritten.
    pub fn save<P: AsRef<Path>>(&self, path: P) -> Result<(), RegistryError> {
        let json = self.to_json();
        let content = serde_json::to_string_pretty(&json)?;
        fs::write(path, content)?;
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Tests (in-crate)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_data() -> serde_json::Value {
        serde_json::json!({
            "meta": {
                "version": "1.0.0",
                "generated_at": "2026-09-09T12:00:00Z",
                "source": "Test"
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
                        "source_url": "https://example.com/nvda-split"
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
                    }
                }
            ]
        })
    }

    #[test]
    fn load_and_basic_queries() {
        let reg = Registry::from_value(sample_data()).unwrap();
        assert_eq!(reg.count(), 4);
        assert_eq!(reg.meta().version.as_deref(), Some("1.0.0"));

        let aapl = reg.by_isin("US0378331005");
        assert_eq!(aapl.len(), 2);

        let split = reg
            .by_action_id("US67066G1040-SPLIT-2024-06-10-10-1")
            .unwrap();
        assert_eq!(split.ratio.as_deref(), Some("10:1"));

        let splits = reg.by_action_type("SPLIT");
        assert_eq!(splits.len(), 2);

        let types = reg.all_action_types();
        assert_eq!(types, vec!["DIVIDEND", "SPLIT", "SYMBOL_CHANGE"]);
    }

    #[test]
    fn by_date_range_returns_result_and_sorts() {
        let reg = Registry::from_value(sample_data()).unwrap();
        let range = reg
            .by_date_range(None, None, "ex_date")
            .expect("valid field");
        assert_eq!(range.len(), 3);
        let dates: Vec<&str> = range
            .iter()
            .filter_map(|a| a.dates.as_ref()?.ex_date.as_deref())
            .collect();
        let mut sorted = dates.clone();
        sorted.sort();
        assert_eq!(dates, sorted);
    }

    #[test]
    fn by_date_range_invalid_field_returns_err() {
        let reg = Registry::from_value(sample_data()).unwrap();
        let err = reg.by_date_range(None, None, "exdate").unwrap_err();
        match err {
            RegistryError::InvalidDateField(field) => assert_eq!(field, "exdate"),
            other => panic!("expected InvalidDateField, got {:?}", other),
        }
    }

    #[test]
    fn by_date_range_inclusive_bounds() {
        let reg = Registry::from_value(sample_data()).unwrap();
        let range = reg
            .by_date_range(Some("2024-05-16"), Some("2024-05-16"), "ex_date")
            .unwrap();
        assert_eq!(range.len(), 1);
        assert_eq!(
            range[0].action_id.as_deref(),
            Some("US0378331005-DIVIDEND-2024-05-16-0.2500")
        );
    }

    #[test]
    fn by_date_range_empty_string_bound_means_no_bound() {
        let reg = Registry::from_value(sample_data()).unwrap();
        let with_empty = reg.by_date_range(Some(""), Some(""), "ex_date").unwrap();
        let with_none = reg.by_date_range(None, None, "ex_date").unwrap();
        assert_eq!(with_empty.len(), with_none.len());
    }

    #[test]
    fn by_date_range_skips_missing_field() {
        let reg = Registry::from_value(sample_data()).unwrap();
        let range = reg.by_date_range(None, None, "ex_date").unwrap();
        let ids: Vec<&str> = range
            .iter()
            .filter_map(|a| a.action_id.as_deref())
            .collect();
        assert!(!ids.contains(&"US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL"));
    }

    #[test]
    fn from_value_rejects_non_object_action() {
        let doc = serde_json::json!({"actions": ["not an object"]});
        let err = Registry::from_value(doc).unwrap_err();
        let msg = err.to_string();
        assert!(msg.contains("not an object"), "unexpected message: {}", msg);
    }

    #[test]
    fn from_value_rejects_missing_actions_key() {
        let doc = serde_json::json!({"meta": {"version": "1.0.0"}});
        let err = Registry::from_value(doc).unwrap_err();
        assert!(err.to_string().contains("missing 'actions' key"));
    }

    #[test]
    fn from_value_rejects_duplicate_action_id() {
        let doc = serde_json::json!({"actions": [
            {"isin": "X", "action_id": "A", "action_type": "SPLIT"},
            {"isin": "Y", "action_id": "A", "action_type": "SPLIT"},
        ]});
        let err = Registry::from_value(doc).unwrap_err();
        assert!(err.to_string().contains("duplicate action_id"));
    }

    #[test]
    fn from_value_rejects_missing_identifier() {
        let doc = serde_json::json!({"actions": [{"action_type": "SPLIT"}]});
        let err = Registry::from_value(doc).unwrap_err();
        assert!(err.to_string().contains("neither"));
    }

    #[test]
    fn load_from_file_strips_bom() {
        use std::io::Write;
        let dir = std::env::temp_dir();
        let path = dir.join(format!(
            "tempus_bom_test_actions_{}.json",
            std::process::id()
        ));
        let mut f = fs::File::create(&path).unwrap();
        f.write_all(b"\xEF\xBB\xBF").unwrap();
        f.write_all(serde_json::to_string(&sample_data()).unwrap().as_bytes())
            .unwrap();
        drop(f);

        let reg = Registry::load_from_file(&path).expect("BOM should be stripped");
        assert_eq!(reg.count(), 4);
        let _ = fs::remove_file(&path);
    }

    #[test]
    fn from_value_empty_actions_is_ok() {
        let reg = Registry::from_value(serde_json::json!({"actions": []})).unwrap();
        assert_eq!(reg.count(), 0);
        assert!(reg.all_action_types().is_empty());
        assert!(reg.by_isin("US0378331005").is_empty());
    }

    #[test]
    fn default_date_field_is_ex_date() {
        assert_eq!(DEFAULT_DATE_FIELD, "ex_date");
    }

    #[test]
    fn valid_date_fields_match_contract() {
        assert!(VALID_DATE_FIELDS.contains(&"announcement"));
        assert!(VALID_DATE_FIELDS.contains(&"ex_date"));
        assert!(VALID_DATE_FIELDS.contains(&"record_date"));
        assert!(VALID_DATE_FIELDS.contains(&"effective_date"));
    }
}
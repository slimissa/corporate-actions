//! Corporate Actions Registry Rust Wrapper
//!
//! This crate provides a typed, dependency-light interface to load and query
//! the Corporate Actions Registry (`actions.json`). It builds in‑memory
//! indexes for fast lookups by ISIN, action ID, and action type, and supports
//! date‑range filtering.
//!
//! # Example
//!
//! ```rust,no_run
//! use corporate_actions_registry::Registry;
//!
//! let registry = Registry::load_from_file("actions.json")?;
//! let aapl_actions = registry.by_isin("US0378331005");
//! for action in aapl_actions {
//!     println!("{:?} {:?}", action.action_type, action.dates);
//! }
//! # Ok::<(), Box<dyn std::error::Error>>(())
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::Path;

/// Errors that can occur when loading or using the registry.
#[derive(Debug, thiserror::Error)]
pub enum RegistryError {
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("invalid registry structure: {0}")]
    InvalidStructure(String),
}

/// Represents the dates of a corporate action.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Dates {
    pub announcement: Option<String>,
    pub ex_date: Option<String>,
    pub record_date: Option<String>,
    pub effective_date: Option<String>,
}

/// Source and verification information.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Provenance {
    pub source: Option<String>,
    pub source_url: Option<String>,
    pub verification_source: Option<String>,
    pub verification_url: Option<String>,
}

/// Financial impact multipliers.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Impact {
    pub price_multiplier: Option<f64>,
    pub share_multiplier: Option<f64>,
    pub cash_adjustment: Option<f64>,
}

/// A single corporate action entry.
#[derive(Debug, Clone, Serialize, Deserialize)]
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
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Meta {
    pub version: Option<String>,
    pub generated_at: Option<String>,
    pub source: Option<String>,
    pub notes: Option<String>,
}

/// The main registry container.
pub struct Registry {
    meta: Meta,
    actions: Vec<Action>,
    // Indexes: map from key to indices in `actions`
    index_isin: HashMap<String, Vec<usize>>,
    index_type: HashMap<String, Vec<usize>>,
    index_id: HashMap<String, usize>,
}

impl Registry {
    /// Load the registry from a JSON file.
    ///
    /// # Arguments
    /// * `path` – Path to the `actions.json` file.
    pub fn load_from_file<P: AsRef<Path>>(path: P) -> Result<Self, RegistryError> {
        let content = fs::read_to_string(path)?;
        let data: serde_json::Value = serde_json::from_str(&content)?;
        Self::from_value(data)
    }

    /// Build the registry from an already parsed JSON value.
    ///
    /// The JSON must have the structure:
    /// ```json
    /// {
    ///   "meta": { ... },
    ///   "actions": [ ... ]
    /// }
    /// ```
    pub fn from_value(data: serde_json::Value) -> Result<Self, RegistryError> {
        // Extract meta (optional)
        let meta: Meta = data
            .get("meta")
            .map(|m| serde_json::from_value(m.clone()))
            .transpose()?
            .unwrap_or_default();

        // Extract actions array
        let actions_value = data
            .get("actions")
            .ok_or_else(|| RegistryError::InvalidStructure("missing 'actions' key".into()))?;
        let actions_array = actions_value
            .as_array()
            .ok_or_else(|| RegistryError::InvalidStructure("'actions' must be an array".into()))?;

        let mut actions = Vec::with_capacity(actions_array.len());
        for (idx, item) in actions_array.iter().enumerate() {
            let action: Action = serde_json::from_value(item.clone()).map_err(|e| {
                RegistryError::InvalidStructure(format!("invalid action at index {}: {}", idx, e))
            })?;

            // Ensure the action has at least an ISIN or an action_id.
            if action.isin.is_none() && action.action_id.is_none() {
                return Err(RegistryError::InvalidStructure(format!(
                    "action at index {} missing both 'isin' and 'action_id'",
                    idx
                )));
            }

            actions.push(action);
        }

        // Build indexes
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
    pub fn by_isin(&self, isin: &str) -> Vec<Action> {
        self.index_isin
            .get(isin)
            .map(|indices| indices.iter().map(|&i| self.actions[i].clone()).collect())
            .unwrap_or_default()
    }

    /// Return a single action by its unique `action_id`.
    pub fn by_action_id(&self, action_id: &str) -> Option<Action> {
        self.index_id
            .get(action_id)
            .map(|&i| self.actions[i].clone())
    }

    /// Return all actions of a given type (e.g., `"SPLIT"`, `"DIVIDEND"`).
    pub fn by_action_type(&self, action_type: &str) -> Vec<Action> {
        self.index_type
            .get(action_type)
            .map(|indices| indices.iter().map(|&i| self.actions[i].clone()).collect())
            .unwrap_or_default()
    }

    /// Filter actions by a date range on a specified date field.
    ///
    /// The date field can be `"announcement"`, `"ex_date"`, `"record_date"`,
    /// or `"effective_date"`. Dates are compared lexicographically, which
    /// works for ISO `YYYY-MM-DD` strings.
    ///
    /// # Arguments
    /// * `start_date` – Include actions with date >= start_date (inclusive).
    /// * `end_date`   – Include actions with date <= end_date (inclusive).
    /// * `date_field` – Which date field to use (default `"ex_date"`).
    pub fn by_date_range(
        &self,
        start_date: Option<&str>,
        end_date: Option<&str>,
        date_field: &str,
    ) -> Vec<Action> {
        self.actions
            .iter()
            .filter(|action| {
                if let Some(dates) = &action.dates {
                    let date_value = match date_field {
                        "announcement" => dates.announcement.as_deref(),
                        "ex_date" => dates.ex_date.as_deref(),
                        "record_date" => dates.record_date.as_deref(),
                        "effective_date" => dates.effective_date.as_deref(),
                        _ => return false,
                    };
                    if let Some(d) = date_value {
                        if let Some(start) = start_date {
                            if d < start {
                                return false;
                            }
                        }
                        if let Some(end) = end_date {
                            if d > end {
                                return false;
                            }
                        }
                        return true;
                    }
                }
                false
            })
            .cloned()
            .collect()
    }

    /// Return a sorted list of all unique action types.
    pub fn all_action_types(&self) -> Vec<String> {
        let mut types: Vec<String> = self.index_type.keys().cloned().collect();
        types.sort();
        types
    }

    /// Return the total number of actions.
    pub fn count(&self) -> usize {
        self.actions.len()
    }

    /// Return a slice of all actions (for iteration and inspection).
    pub fn all_actions(&self) -> &[Action] {
        &self.actions
    }

    /// Return a reference to the registry metadata.
    pub fn meta(&self) -> &Meta {
        &self.meta
    }

    /// Convert the registry to a JSON value.
    pub fn to_json(&self) -> serde_json::Value {
        serde_json::json!({
            "meta": self.meta,
            "actions": self.actions,
        })
    }

    /// Save the registry to a file.
    pub fn save<P: AsRef<Path>>(&self, path: P) -> Result<(), RegistryError> {
        let json = self.to_json();
        let content = serde_json::to_string_pretty(&json)?;
        fs::write(path, content)?;
        Ok(())
    }
}

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
                        "source_url": "https://example.com/nvda-split"
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
                    }
                }
            ]
        })
    }

    #[test]
    fn load_and_query() {
        let reg = Registry::from_value(sample_data()).unwrap();
        assert_eq!(reg.count(), 4);
        assert_eq!(reg.meta().version.as_deref(), Some("1.0.0"));

        let aapl = reg.by_isin("US0378331005");
        assert_eq!(aapl.len(), 2);

        let split = reg
            .by_action_id("US67066G1040-SPLIT-2024-06-10-0001")
            .unwrap();
        assert_eq!(split.ratio.as_deref(), Some("10:1"));

        let splits = reg.by_action_type("SPLIT");
        assert_eq!(splits.len(), 2);

        let range = reg.by_date_range(Some("2020-01-01"), Some("2023-12-31"), "ex_date");
        assert_eq!(range.len(), 1);
        assert_eq!(
            range[0].action_id.as_deref(),
            Some("US0378331005-SPLIT-2020-08-31-0003")
        );

        let types = reg.all_action_types();
        assert_eq!(types, vec!["DIVIDEND", "SPLIT", "SYMBOL_CHANGE"]);
    }
}

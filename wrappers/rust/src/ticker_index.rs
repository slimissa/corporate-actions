//! Ticker-index support for [`crate::Registry::by_ticker`].
//!
//! Loads `identifiers.json` (the Asset Identifiers registry) and
//! returns a map from `"TICKER|EXCHANGE"` to ISIN. Results are cached
//! per canonical path for the life of the process.
//!
//! See `docs/wrapper_contract.md` section 4.8.

use crate::RegistryError;
use serde::Deserialize;
use std::collections::HashMap;
use std::fs;
use std::path::Path;
use std::sync::{Mutex, OnceLock};

// ---------------------------------------------------------------------------
// Cache
// ---------------------------------------------------------------------------

type Index = HashMap<String, String>;
type Cache = HashMap<String, Index>;

/// Per-process cache, keyed by canonical path. A `OnceLock<Mutex<_>>`
/// is the simplest way to get a lazily-initialised, thread-safe
/// process-global map without pulling in a dependency.
fn cache() -> &'static Mutex<Cache> {
    static CACHE: OnceLock<Mutex<Cache>> = OnceLock::new();
    CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

/// Clear the per-path ticker index cache. For tests only.
///
/// Not part of the public contract. Tests that load a different
/// identifiers file between cases should call this to avoid seeing a
/// stale index.
pub fn reset_cache() {
    if let Ok(mut c) = cache().lock() {
        c.clear();
    }
}

// ---------------------------------------------------------------------------
// identifiers.json shape
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
struct IdentifierDocument {
    #[serde(default)]
    instruments: Vec<IdentifierInstrument>,
}

#[derive(Debug, Deserialize)]
struct IdentifierInstrument {
    ticker: Option<String>,
    exchange: Option<String>,
    isin: Option<String>,
}

// ---------------------------------------------------------------------------
// Path resolution
// ---------------------------------------------------------------------------

/// Resolve the identifiers file path.
///
/// Priority:
///   1. Explicit argument
///   2. `$CORP_ACTIONS_IDENTIFIERS_PATH`
///   3. `$LAS_DATA_HOME/identifiers.json`
///
/// The returned error wraps [`RegistryError::MissingData`] so callers
/// can match on the variant.
pub(crate) fn resolve_path(explicit: Option<&str>) -> Result<String, RegistryError> {
    if let Some(p) = explicit {
        if !p.is_empty() {
            return Ok(p.to_string());
        }
    }

    if let Ok(p) = std::env::var("CORP_ACTIONS_IDENTIFIERS_PATH") {
        if !p.is_empty() {
            return Ok(p);
        }
    }

    if let Ok(home) = std::env::var("LAS_DATA_HOME") {
        if !home.is_empty() {
            return Ok(format!("{}/identifiers.json", home));
        }
    }

    Err(RegistryError::MissingData(
        "neither CORP_ACTIONS_IDENTIFIERS_PATH nor LAS_DATA_HOME is set, \
         and no identifiers_path was provided"
            .into(),
    ))
}

// ---------------------------------------------------------------------------
// Load and lookup
// ---------------------------------------------------------------------------

/// Load and cache the ticker index for the given path.
///
/// The returned error is [`RegistryError::MissingData`] for a missing
/// or malformed file. A path that does not exist is reported verbatim
/// in the message.
fn load_index(path: &str) -> Result<Index, RegistryError> {
    // Canonicalise when possible so `./foo.json` and `foo.json` share a
    // cache slot. If the file does not exist, fall back to the given
    // path so the error message names what the caller passed.
    let key = match Path::new(path).canonicalize() {
        Ok(p) => p.to_string_lossy().into_owned(),
        Err(_) => path.to_string(),
    };

    // Fast path: cached hit. Clone the index so the lock is released
    // before returning.
    {
        let c = cache()
            .lock()
            .expect("ticker cache mutex poisoned");
        if let Some(idx) = c.get(&key) {
            return Ok(idx.clone());
        }
    }

    // Slow path: read and parse.
    let content = fs::read_to_string(&key).map_err(|_| {
        RegistryError::MissingData(format!(
            "{} not found; set CORP_ACTIONS_IDENTIFIERS_PATH or LAS_DATA_HOME",
            key
        ))
    })?;

    let content = content.strip_prefix('\u{FEFF}').unwrap_or(&content);

    let doc: IdentifierDocument = serde_json::from_str(content).map_err(|e| {
        RegistryError::MissingData(format!("parsing {}: {}", key, e))
    })?;

    let mut index: Index = HashMap::with_capacity(doc.instruments.len());
    for inst in doc.instruments {
        if let (Some(t), Some(x), Some(i)) = (inst.ticker, inst.exchange, inst.isin) {
            if !t.is_empty() && !x.is_empty() && !i.is_empty() {
                index.insert(
                    format!("{}|{}", t.to_uppercase(), x.to_uppercase()),
                    i,
                );
            }
        }
    }

    // Store in cache.
    {
        let mut c = cache()
            .lock()
            .expect("ticker cache mutex poisoned");
        c.insert(key, index.clone());
    }

    Ok(index)
}

/// Resolve `(ticker, exchange)` to an ISIN using the Asset Identifiers
/// registry.
///
/// Returns `Ok(None)` when the pair is not in the index. Returns
/// `Err(RegistryError::MissingData)` when the file cannot be resolved
/// or read.
pub(crate) fn lookup(
    ticker: &str,
    exchange: &str,
    explicit_path: Option<&str>,
) -> Result<Option<String>, RegistryError> {
    let path = resolve_path(explicit_path)?;
    let index = load_index(&path)?;
    let key = format!("{}|{}", ticker.to_uppercase(), exchange.to_uppercase());
    Ok(index.get(&key).cloned())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolve_path_uses_explicit_argument() {
        let p = resolve_path(Some("/tmp/explicit.json")).unwrap();
        assert_eq!(p, "/tmp/explicit.json");
    }

    #[test]
    fn resolve_path_rejects_empty_arguments_without_env() {
        // Unset env vars for this test only.
        let saved_ident = std::env::var("CORP_ACTIONS_IDENTIFIERS_PATH").ok();
        let saved_home = std::env::var("LAS_DATA_HOME").ok();
        std::env::remove_var("CORP_ACTIONS_IDENTIFIERS_PATH");
        std::env::remove_var("LAS_DATA_HOME");

        let result = resolve_path(None);

        // Restore before asserting so a panic does not leave the
        // environment polluted for other tests.
        if let Some(v) = saved_ident {
            std::env::set_var("CORP_ACTIONS_IDENTIFIERS_PATH", v);
        }
        if let Some(v) = saved_home {
            std::env::set_var("LAS_DATA_HOME", v);
        }

        match result {
            Err(RegistryError::MissingData(msg)) => {
                assert!(msg.contains("CORP_ACTIONS_IDENTIFIERS_PATH"));
            }
            other => panic!("expected MissingData, got {:?}", other),
        }
    }

    #[test]
    fn lookup_missing_file_returns_missing_data() {
        let result = lookup("X", "Y", Some("/nonexistent/identifiers.json"));
        match result {
            Err(RegistryError::MissingData(msg)) => {
                assert!(msg.contains("not found"));
            }
            other => panic!("expected MissingData, got {:?}", other),
        }
    }
}
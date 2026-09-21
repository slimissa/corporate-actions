/**
 * Corporate Actions Registry JavaScript Wrapper
 *
 * Provides a clean interface to load and query the Corporate Actions
 * Registry (actions.json) in Node.js. Builds in-memory indexes for
 * fast lookups by ISIN, action ID, action type, and ticker.
 *
 * Usage:
 *   const { CorporateActionsRegistry } = require('corporate-actions-registry');
 *   const registry = new CorporateActionsRegistry('actions.json');
 *   const aaplActions = registry.byIsin('US0378331005');
 *
 * The wrapper is dependency-free and works with CommonJS.
 *
 * Behaviour is specified by docs/wrapper_contract.md. When this file
 * and that document disagree, the document wins.
 */

'use strict';

const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Exported constants (wrapper contract section 4.9)
// ---------------------------------------------------------------------------

const DEFAULT_DATE_FIELD = 'ex_date';

const VALID_DATE_FIELDS = Object.freeze([
  'announcement',
  'ex_date',
  'record_date',
  'effective_date',
]);

// ---------------------------------------------------------------------------
// Ticker index (wrapper contract section 4.8)
//
// A module-level cache keyed by absolute path. A caller who passes an
// explicit identifiersPath gets the index for that path; a caller who
// relies on the environment gets the index for whichever path the
// environment resolves to.
// ---------------------------------------------------------------------------

const _tickerIndexCache = new Map();

/**
 * Resolve the identifiers file path.
 *
 * Priority:
 *   1. Explicit argument
 *   2. $CORP_ACTIONS_IDENTIFIERS_PATH
 *   3. $LAS_DATA_HOME/identifiers.json
 *
 * @param {string|null|undefined} explicit
 * @returns {string} absolute path
 * @throws {Error} when none is available
 */
function _resolveIdentifiersPath(explicit) {
  if (explicit) return path.resolve(explicit);

  const envPath = process.env.CORP_ACTIONS_IDENTIFIERS_PATH;
  if (envPath) return path.resolve(envPath);

  const lasHome = process.env.LAS_DATA_HOME;
  if (lasHome) return path.resolve(path.join(lasHome, 'identifiers.json'));

  throw new Error(
    'Cannot resolve ticker: neither CORP_ACTIONS_IDENTIFIERS_PATH ' +
    'nor LAS_DATA_HOME is set, and no identifiersPath was provided.'
  );
}

/**
 * Load identifiers.json and return a Map from "TICKER|EXCHANGE" to ISIN.
 * Cached per absolute path.
 *
 * @param {string} p
 * @returns {Map<string,string>}
 * @throws {Error} when the file cannot be read
 */
function _buildTickerIndex(p) {
  const abs = path.resolve(p);
  const cached = _tickerIndexCache.get(abs);
  if (cached) return cached;

  let content;
  try {
    content = fs.readFileSync(abs, 'utf8');
  } catch (e) {
    if (e.code === 'ENOENT') {
      throw new Error(
        `Cannot resolve ticker: ${abs} not found. ` +
        `Set CORP_ACTIONS_IDENTIFIERS_PATH or LAS_DATA_HOME.`
      );
    }
    throw e;
  }

  // Strip UTF-8 BOM if present.
  if (content.charCodeAt(0) === 0xFEFF) content = content.slice(1);

  const data = JSON.parse(content);
  const index = new Map();
  const instruments = Array.isArray(data.instruments) ? data.instruments : [];

  for (const inst of instruments) {
    if (!inst || typeof inst !== 'object') continue;
    const t = inst.ticker;
    const x = inst.exchange;
    const i = inst.isin;
    if (t && x && i) {
      const key = `${String(t).toUpperCase()}|${String(x).toUpperCase()}`;
      index.set(key, String(i));
    }
  }

  _tickerIndexCache.set(abs, index);
  return index;
}

/**
 * Clear the per-path ticker index cache. For tests only.
 */
function _resetTickerCache() {
  _tickerIndexCache.clear();
}

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

class CorporateActionsRegistry {
  /**
   * Create a registry instance.
   *
   * @param {string|object} source - Path to actions.json or an already
   *   loaded object.
   * @throws {Error} If source is invalid or structurally wrong.
   */
  constructor(source) {
    if (!source) {
      throw new Error('Either a file path or a data object must be provided.');
    }

    let rawData;
    if (typeof source === 'string') {
      const filePath = path.resolve(source);
      let fileContent = fs.readFileSync(filePath, 'utf8');
      if (fileContent.charCodeAt(0) === 0xFEFF) {
        fileContent = fileContent.slice(1);
      }
      rawData = JSON.parse(fileContent);
    } else if (typeof source === 'object') {
      rawData = source;
    } else {
      throw new Error('Source must be a string path or an object.');
    }

    if (!rawData || typeof rawData !== 'object' || !Array.isArray(rawData.actions)) {
      throw new Error('Invalid actions data: expected object with "actions" array.');
    }

    // Per-item structural validation, single pass.
    const seenIds = new Map();
    for (let i = 0; i < rawData.actions.length; i++) {
      const a = rawData.actions[i];
      if (!a || typeof a !== 'object' || Array.isArray(a)) {
        throw new Error(
          `Invalid actions data: action at index ${i} is not an object.`
        );
      }

      const aid = a.action_id;
      if (aid) {
        if (seenIds.has(aid)) {
          throw new Error(
            `duplicate action_id at index ${i}: ${JSON.stringify(aid)} ` +
            `(first seen at index ${seenIds.get(aid)})`
          );
        }
        seenIds.set(aid, i);
      }

      if (!a.isin && !aid) {
        throw new Error(
          `Invalid actions data: action at index ${i} has ` +
          `neither "isin" nor "action_id"`
        );
      }
    }

    this.meta = (rawData.meta && typeof rawData.meta === 'object' && !Array.isArray(rawData.meta))
      ? { ...rawData.meta }
      : {};
    this.actions = rawData.actions;
    this._buildIndexes();
  }

  /**
   * Build internal indexes for fast lookup.
   * @private
   */
  _buildIndexes() {
    this._indexByIsin = new Map();
    this._indexByType = new Map();
    this._indexById = new Map();

    for (const action of this.actions) {
      if (action.action_id) {
        // The constructor already rejects duplicates.
        this._indexById.set(action.action_id, action);
      }
      if (action.isin) {
        if (!this._indexByIsin.has(action.isin)) {
          this._indexByIsin.set(action.isin, []);
        }
        this._indexByIsin.get(action.isin).push(action);
      }
      if (action.action_type) {
        if (!this._indexByType.has(action.action_type)) {
          this._indexByType.set(action.action_type, []);
        }
        this._indexByType.get(action.action_type).push(action);
      }
    }
  }

  /**
   * Return all actions for a given ISIN.
   * @param {string} isin - The ISIN (e.g., 'US0378331005').
   * @returns {Array<object>} Fresh list of action objects.
   */
  byIsin(isin) {
    return (this._indexByIsin.get(isin) || []).map((a) => structuredClone(a));
  }

  /**
   * Return a single action by its unique action_id.
   * @param {string} actionId
   * @returns {object|null} Deep copy of the action, or null.
   */
  byActionId(actionId) {
    const action = this._indexById.get(actionId);
    return action ? structuredClone(action) : null;
  }

  /**
   * Return all actions of a given type (e.g., 'SPLIT', 'DIVIDEND').
   * @param {string} actionType
   * @returns {Array<object>} Fresh list of action objects.
   */
  byActionType(actionType) {
    return (this._indexByType.get(actionType) || []).map((a) => structuredClone(a));
  }

  /**
   * Filter actions by a date range on a specified date field.
   *
   * Dates are compared as ISO strings (YYYY-MM-DD), so lexicographic
   * comparison works correctly.
   *
   * @param {string|null} [startDate] - Include actions with date >= startDate.
   * @param {string|null} [endDate] - Include actions with date <= endDate.
   * @param {string} [dateField=DEFAULT_DATE_FIELD]
   * @returns {Array<object>} Fresh list, sorted by (date, action_id).
   * @throws {Error} If dateField is invalid.
   */
  byDateRange(startDate, endDate, dateField = DEFAULT_DATE_FIELD) {
    if (!VALID_DATE_FIELDS.includes(dateField)) {
      throw new Error(
        `invalid dateField '${dateField}'; expected one of ` +
        `${VALID_DATE_FIELDS.join(', ')}`
      );
    }

    const result = this.actions.filter((action) => {
      const dates = action.dates || {};
      const value = dates[dateField];
      if (!value) return false;
      if (startDate && value < startDate) return false;
      if (endDate && value > endDate) return false;
      return true;
    });

    result.sort((a, b) => {
      const av = (a.dates || {})[dateField] || '';
      const bv = (b.dates || {})[dateField] || '';
      if (av !== bv) return av < bv ? -1 : 1;
      const aid = a.action_id || '';
      const bid = b.action_id || '';
      return aid < bid ? -1 : aid > bid ? 1 : 0;
    });

    return result.map((a) => structuredClone(a));
  }

  /**
   * Return all actions for a ticker on an exchange.
   *
   * Resolves (ticker, exchange) -> ISIN using the Asset Identifiers
   * registry, then returns the same list as `byIsin(isin)`.
   *
   * Path resolution when identifiersPath is null/undefined:
   *   1. $CORP_ACTIONS_IDENTIFIERS_PATH
   *   2. $LAS_DATA_HOME/identifiers.json
   *
   * Ticker and exchange are uppercased before lookup. An unknown
   * (ticker, exchange) pair returns an empty list, not an error.
   * A missing identifiers file throws.
   *
   * @param {string} ticker
   * @param {string} exchange
   * @param {string|null} [identifiersPath=null]
   * @returns {Array<object>}
   */
  byTicker(ticker, exchange, identifiersPath = null) {
    const p = _resolveIdentifiersPath(identifiersPath);
    const index = _buildTickerIndex(p);

    const key = `${String(ticker).toUpperCase()}|${String(exchange).toUpperCase()}`;
    const isin = index.get(key);
    if (!isin) return [];
    return this.byIsin(isin);
  }

  /**
   * Return a sorted list of all unique action types.
   * @returns {string[]}
   */
  allActionTypes() {
    return Array.from(this._indexByType.keys()).sort();
  }

  /**
   * Return the total number of actions.
   * @returns {number}
   */
  count() {
    return this.actions.length;
  }

  /**
   * Convert the registry back to a plain object.
   * @returns {{meta: object, actions: Array<object>}}
   */
  toJSON() {
    return {
      meta: { ...this.meta },
      actions: this.actions.map((a) => structuredClone(a)),
    };
  }

  /**
   * Save the registry to a JSON file.
   * @param {string} filePath - Destination path.
   */
  save(filePath) {
    const data = JSON.stringify(this.toJSON(), null, 2);
    fs.writeFileSync(path.resolve(filePath), data, 'utf8');
  }

  /**
   * Get number of actions.
   * @returns {number}
   */
  get length() {
    return this.actions.length;
  }
}

module.exports = {
  CorporateActionsRegistry,
  DEFAULT_DATE_FIELD,
  VALID_DATE_FIELDS,
  _resetTickerCache,
};
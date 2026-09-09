/**
 * Corporate Actions Registry JavaScript Wrapper
 *
 * Provides a clean interface to load and query the Corporate Actions
 * Registry (actions.json) in Node.js. The class builds in-memory
 * indexes for fast lookups by ISIN, action ID, and action type.
 *
 * Usage:
 *   const { CorporateActionsRegistry } = require('corporate-actions-registry');
 *   const registry = new CorporateActionsRegistry('actions.json');
 *   const aaplActions = registry.byIsin('US0378331005');
 *
 * The wrapper is dependency-free and works with CommonJS.
 */

'use strict';

const fs = require('fs');
const path = require('path');

class CorporateActionsRegistry {
  /**
   * Create a registry instance.
   * @param {string|object} source - Path to actions.json or an already loaded object.
   * @throws {Error} If source is not provided or file cannot be read.
   */
  constructor(source) {
    if (!source) {
      throw new Error('Either a file path or a data object must be provided.');
    }

    let rawData;
    if (typeof source === 'string') {
      // It's a file path: read synchronously
      const filePath = path.resolve(source);
      const fileContent = fs.readFileSync(filePath, 'utf8');
      rawData = JSON.parse(fileContent);
    } else if (typeof source === 'object') {
      rawData = source;
    } else {
      throw new Error('Source must be a string path or an object.');
    }

    if (!rawData || typeof rawData !== 'object' || !Array.isArray(rawData.actions)) {
      throw new Error('Invalid actions data: expected object with "actions" array.');
    }

    this.meta = rawData.meta || {};
    this.actions = rawData.actions || [];
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
   * @returns {Array<object>} List of action objects (possibly empty).
   */
  byIsin(isin) {
    return this._indexByIsin.get(isin) || [];
  }

  /**
   * Return a single action by its unique action_id.
   * @param {string} actionId - The unique action identifier.
   * @returns {object|null} Action object if found, otherwise null.
   */
  byActionId(actionId) {
    return this._indexById.get(actionId) || null;
  }

  /**
   * Return all actions of a given type.
   * @param {string} actionType - e.g., 'SPLIT', 'DIVIDEND'.
   * @returns {Array<object>} List of action objects (possibly empty).
   */
  byActionType(actionType) {
    return this._indexByType.get(actionType) || [];
  }

  /**
   * Filter actions by a date range on a specified date field.
   * Dates are compared as ISO strings (YYYY-MM-DD), so lexicographic
   * comparison works correctly.
   *
   * @param {string} [startDate] - Include actions with date >= startDate.
   * @param {string} [endDate] - Include actions with date <= endDate.
   * @param {string} [dateField='ex_date'] - Which date field to use:
   *   'announcement', 'ex_date', 'record_date', 'effective_date'.
   * @returns {Array<object>} Actions matching the date range.
   */
  byDateRange(startDate, endDate, dateField = 'ex_date') {
    return this.actions.filter((action) => {
      const dates = action.dates || {};
      const dateValue = dates[dateField];
      if (!dateValue) return false;
      if (startDate && dateValue < startDate) return false;
      if (endDate && dateValue > endDate) return false;
      return true;
    });
  }

  /**
   * Return a sorted list of all unique action types.
   * @returns {string[]} Sorted array of action types.
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
      meta: this.meta,
      actions: this.actions,
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

module.exports = { CorporateActionsRegistry };
/**
 * Comprehensive tests for the JavaScript wrapper of the Corporate Actions Registry.
 *
 * Uses Node.js built-in test runner (node:test) and assert module.
 * Run: node --test test/test_wrapper.js
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const os = require('os');

const { CorporateActionsRegistry } = require('../src/index.js');

// ----------------------------------------------------------------------
// Sample data
// ----------------------------------------------------------------------
const sampleData = {
  meta: {
    version: '1.0.0',
    generated_at: '2026-09-09T12:00:00Z',
    source: 'Test',
    notes: 'Sample data for testing',
  },
  actions: [
    {
      isin: 'US67066G1040',
      action_id: 'US67066G1040-SPLIT-2024-06-10-0001',
      action_type: 'SPLIT',
      ratio: '10:1',
      dates: {
        announcement: '2024-05-22',
        ex_date: '2024-06-10',
        record_date: '2024-06-07',
        effective_date: '2024-06-10',
      },
      status: 'COMPLETED',
      provenance: {
        source: 'NVIDIA',
        source_url: 'https://example.com/nvda-split',
        verification_source: 'SEC EDGAR',
      },
      impact: {
        price_multiplier: 0.1,
        share_multiplier: 10.0,
      },
    },
    {
      isin: 'US0378331005',
      action_id: 'US0378331005-DIVIDEND-2024-05-16-0002',
      action_type: 'DIVIDEND',
      amount: 0.25,
      currency: 'USD',
      dates: {
        announcement: '2024-05-02',
        ex_date: '2024-05-16',
        record_date: '2024-05-17',
        effective_date: '2024-05-23',
      },
      status: 'COMPLETED',
      provenance: {
        source: 'Apple',
        source_url: 'https://example.com/aapl-div',
      },
      impact: {
        cash_adjustment: 0.25,
        price_multiplier: 1.0,
        share_multiplier: 1.0,
      },
    },
    {
      isin: 'US0378331005',
      action_id: 'US0378331005-SPLIT-2020-08-31-0003',
      action_type: 'SPLIT',
      ratio: '4:1',
      dates: {
        announcement: '2020-07-30',
        ex_date: '2020-08-31',
        record_date: '2020-08-24',
        effective_date: '2020-08-31',
      },
      status: 'COMPLETED',
      provenance: {
        source: 'Apple',
        source_url: 'https://example.com/aapl-split',
      },
      impact: {
        price_multiplier: 0.25,
        share_multiplier: 4.0,
      },
    },
    {
      isin: 'US30303M1027',
      action_id: 'US30303M1027-SYMBOL_CHANGE-2022-06-09-0004',
      action_type: 'SYMBOL_CHANGE',
      dates: {
        announcement: '2022-06-09',
        effective_date: '2022-06-09',
      },
      status: 'COMPLETED',
      provenance: {
        source: 'Meta',
        source_url: 'https://example.com/meta-symbol',
      },
      impact: {},
    },
  ],
};

// ----------------------------------------------------------------------
// Tests
// ----------------------------------------------------------------------
test('Loading from object works', () => {
  const registry = new CorporateActionsRegistry(sampleData);
  assert.strictEqual(registry.count(), 4);
  assert.strictEqual(registry.meta.version, '1.0.0');
  assert.strictEqual(registry.meta.source, 'Test');
});

test('Loading from file works', () => {
  const tmpFile = path.join(os.tmpdir(), 'test-actions.json');
  fs.writeFileSync(tmpFile, JSON.stringify(sampleData));
  const registry = new CorporateActionsRegistry(tmpFile);
  assert.strictEqual(registry.count(), 4);
  assert.strictEqual(registry.meta.version, '1.0.0');
  fs.unlinkSync(tmpFile);
});

test('Invalid source types throw errors', () => {
  assert.throws(() => new CorporateActionsRegistry(), Error);
  assert.throws(() => new CorporateActionsRegistry(null), Error);
  assert.throws(() => new CorporateActionsRegistry(123), Error);
});

test('Invalid data structure throws error', () => {
  assert.throws(() => new CorporateActionsRegistry({ bad: 'data' }), Error);
  assert.throws(() => new CorporateActionsRegistry({ actions: 'not array' }), Error);
});

test('byIsin returns correct actions', () => {
  const registry = new CorporateActionsRegistry(sampleData);
  const aapl = registry.byIsin('US0378331005');
  assert.strictEqual(aapl.length, 2);
  assert.ok(aapl.every(a => a.isin === 'US0378331005'));
});

test('byIsin returns empty array for unknown ISIN', () => {
  const registry = new CorporateActionsRegistry(sampleData);
  assert.deepStrictEqual(registry.byIsin('US0000000000'), []);
});

test('byActionId returns action if found', () => {
  const registry = new CorporateActionsRegistry(sampleData);
  const action = registry.byActionId('US67066G1040-SPLIT-2024-06-10-0001');
  assert.ok(action);
  assert.strictEqual(action.action_type, 'SPLIT');
  assert.strictEqual(action.ratio, '10:1');
});

test('byActionId returns null if not found', () => {
  const registry = new CorporateActionsRegistry(sampleData);
  assert.strictEqual(registry.byActionId('NONEXISTENT'), null);
});

test('byActionType returns all actions of that type', () => {
  const registry = new CorporateActionsRegistry(sampleData);
  const splits = registry.byActionType('SPLIT');
  assert.strictEqual(splits.length, 2);
  assert.ok(splits.every(a => a.action_type === 'SPLIT'));
});

test('byActionType returns empty array for unknown type', () => {
  const registry = new CorporateActionsRegistry(sampleData);
  assert.deepStrictEqual(registry.byActionType('MERGER'), []);
});

test('byDateRange filters correctly on ex_date', () => {
  const registry = new CorporateActionsRegistry(sampleData);
  const actions = registry.byDateRange('2020-01-01', '2023-12-31', 'ex_date');
  assert.strictEqual(actions.length, 1);
  assert.strictEqual(actions[0].action_id, 'US0378331005-SPLIT-2020-08-31-0003');
});

test('byDateRange with effective_date returns expected actions', () => {
  const registry = new CorporateActionsRegistry(sampleData);
  const actions = registry.byDateRange('2024-01-01', '2024-12-31', 'effective_date');
  // NVDA split (2024-06-10), AAPL dividend (2024-05-23)
  // Symbol change is 2022, AAPL split is 2020
  assert.strictEqual(actions.length, 2);
});

test('allActionTypes returns sorted unique types', () => {
  const registry = new CorporateActionsRegistry(sampleData);
  assert.deepStrictEqual(registry.allActionTypes(), ['DIVIDEND', 'SPLIT', 'SYMBOL_CHANGE']);
});

test('toJSON returns serializable object', () => {
  const registry = new CorporateActionsRegistry(sampleData);
  const json = registry.toJSON();
  assert.strictEqual(json.actions.length, 4);
  assert.strictEqual(json.meta.version, '1.0.0');
});

test('save writes a file that can be reloaded', () => {
  const registry = new CorporateActionsRegistry(sampleData);
  const tmpFile = path.join(os.tmpdir(), 'output-actions.json');
  registry.save(tmpFile);
  const loaded = new CorporateActionsRegistry(tmpFile);
  assert.strictEqual(loaded.count(), registry.count());
  assert.deepStrictEqual(loaded.toJSON(), registry.toJSON());
  fs.unlinkSync(tmpFile);
});

test('length getter returns count', () => {
  const registry = new CorporateActionsRegistry(sampleData);
  assert.strictEqual(registry.length, 4);
});
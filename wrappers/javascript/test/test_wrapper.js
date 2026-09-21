/**
 * Comprehensive tests for the JavaScript wrapper of the Corporate
 * Actions Registry.
 *
 * Uses Node's built-in test runner (node:test) and assert module.
 * No external dependencies. Each test file is hermetic: temp files are
 * created under a unique directory so parallel runs do not collide.
 *
 * The tests encode the contract in docs/wrapper_contract.md. When a
 * test fails, either the wrapper has drifted from the contract or the
 * contract needs to change; both are visible from the failure message.
 *
 * Run:
 *     node --test test/test_wrapper.js
 * or:
 *     npm test
 */

'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const os = require('os');

const { CorporateActionsRegistry } = require('../src/index.js');


// ----------------------------------------------------------------------
// Fixtures
// ----------------------------------------------------------------------

/**
 * Four actions across three ISINs:
 *
 *   - NVDA 10:1 split on 2024-06-10
 *   - AAPL dividend on 2024-05-16
 *   - AAPL 4:1 split on 2020-08-31
 *   - META symbol change on 2022-06-09 (no ex_date)
 *
 * The spread of dates and the missing ex_date let the date-range tests
 * cover inclusive bounds, missing fields, and sorting.
 */
function sampleData() {
  return {
    meta: {
      version: '1.0.0',
      generated_at: '2026-09-09T12:00:00Z',
      source: 'Test',
      notes: 'Sample data for testing',
    },
    actions: [
      {
        isin: 'US67066G1040',
        action_id: 'US67066G1040-SPLIT-2024-06-10-10-1',
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
        impact: { price_multiplier: 0.1, share_multiplier: 10.0 },
      },
      {
        isin: 'US0378331005',
        action_id: 'US0378331005-DIVIDEND-2024-05-16-0.2500',
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
        action_id: 'US0378331005-SPLIT-2020-08-31-4-1',
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
        impact: { price_multiplier: 0.25, share_multiplier: 4.0 },
      },
      {
        isin: 'US30303M1027',
        action_id: 'US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL',
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
}

/** Two actions sharing an ex_date, to exercise tiebreak ordering. */
function tiebreakData() {
  return {
    meta: { version: '1.0.0', generated_at: '2026-09-09T00:00:00Z', source: 'Test' },
    actions: [
      {
        isin: 'US0000000001',
        action_id: 'US0000000001-DIVIDEND-2024-05-16-0.2500',
        action_type: 'DIVIDEND',
        dates: {
          announcement: '2024-05-02',
          ex_date: '2024-05-16',
          effective_date: '2024-05-23',
        },
      },
      {
        isin: 'US0000000002',
        action_id: 'US0000000002-DIVIDEND-2024-05-16-0.3000',
        action_type: 'DIVIDEND',
        dates: {
          announcement: '2024-05-02',
          ex_date: '2024-05-16',
          effective_date: '2024-05-23',
        },
      },
    ],
  };
}


// ----------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------

/** Create a unique temp directory for one test. */
function makeTmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'ca-js-'));
}

/** Write a JSON file into a unique temp dir and return its path. */
function writeTempJson(content, { bom = false } = {}) {
  const dir = makeTmpDir();
  const filePath = path.join(dir, 'actions.json');
  const payload = Buffer.from(JSON.stringify(content), 'utf8');
  const bytes = bom ? Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), payload]) : payload;
  fs.writeFileSync(filePath, bytes);
  return filePath;
}

/** Return a registry built from the sample data. */
function makeRegistry() {
  return new CorporateActionsRegistry(sampleData());
}


// ----------------------------------------------------------------------
// Loading
// ----------------------------------------------------------------------

describe('Loading', () => {

  it('loads from a plain object', () => {
    const registry = makeRegistry();
    assert.strictEqual(registry.count(), 4);
    assert.strictEqual(registry.meta.version, '1.0.0');
    assert.strictEqual(registry.meta.source, 'Test');
  });

  it('loads from a file path', () => {
    const path = writeTempJson(sampleData());
    const registry = new CorporateActionsRegistry(path);
    assert.strictEqual(registry.count(), 4);
    assert.strictEqual(registry.meta.version, '1.0.0');
  });

  it('loads from a BOM-prefixed file', () => {
    const path = writeTempJson(sampleData(), { bom: true });
    const registry = new CorporateActionsRegistry(path);
    assert.strictEqual(registry.count(), 4);
  });

  it('throws when constructed with no arguments', () => {
    assert.throws(() => new CorporateActionsRegistry(), /must be provided/);
  });

  it('throws when constructed with null', () => {
    assert.throws(() => new CorporateActionsRegistry(null), /must be provided/);
  });

  it('throws when constructed with undefined', () => {
    assert.throws(() => new CorporateActionsRegistry(undefined), /must be provided/);
  });

  it('throws when constructed with a number', () => {
    assert.throws(() => new CorporateActionsRegistry(123), /string path or an object/);
  });

  it('throws when constructed with a boolean', () => {
    assert.throws(() => new CorporateActionsRegistry(true), /string path or an object/);
  });

  it('throws when the object has no actions key', () => {
    assert.throws(
      () => new CorporateActionsRegistry({ bad: 'data' }),
      /Invalid actions data/,
    );
  });

  it('throws when actions is a string', () => {
    assert.throws(
      () => new CorporateActionsRegistry({ actions: 'not an array' }),
      /Invalid actions data/,
    );
  });

  it('throws when actions is an object', () => {
    assert.throws(
      () => new CorporateActionsRegistry({ actions: { not: 'a list' } }),
      /Invalid actions data/,
    );
  });

  it('throws when actions is null', () => {
    assert.throws(
      () => new CorporateActionsRegistry({ actions: null }),
      /Invalid actions data/,
    );
  });

  it('throws when an action entry is a string', () => {
    assert.throws(
      () => new CorporateActionsRegistry({ actions: ['not an object'] }),
      /not an object/,
    );
  });

  it('throws when an action entry is a number', () => {
    assert.throws(
      () => new CorporateActionsRegistry({ actions: [42] }),
      /not an object/,
    );
  });

  it('throws when an action entry is null', () => {
    assert.throws(
      () => new CorporateActionsRegistry({ actions: [null] }),
      /not an object/,
    );
  });

  it('throws when an action entry is an array', () => {
    assert.throws(
      () => new CorporateActionsRegistry({ actions: [[]] }),
      /not an object/,
    );
  });

  it('names the index of a non-object action', () => {
    assert.throws(
      () => new CorporateActionsRegistry({
        actions: [{ action_id: 'ok' }, 'bad'],
      }),
      /index 1/,
    );
  });

  it('accepts an empty actions array', () => {
    const registry = new CorporateActionsRegistry({ actions: [] });
    assert.strictEqual(registry.count(), 0);
    assert.deepStrictEqual(registry.byIsin('US0378331005'), []);
    assert.deepStrictEqual(registry.byActionType('SPLIT'), []);
    assert.deepStrictEqual(registry.allActionTypes(), []);
  });

  it('accepts a missing meta field', () => {
    const registry = new CorporateActionsRegistry({ actions: [] });
    assert.deepStrictEqual(registry.meta, {});
  });

  it('accepts a null meta field', () => {
    const registry = new CorporateActionsRegistry({ actions: [], meta: null });
    assert.deepStrictEqual(registry.meta, {});
  });

  it('coerces a non-object meta to empty', () => {
    const registry = new CorporateActionsRegistry({
      actions: [],
      meta: 'not an object',
    });
    assert.deepStrictEqual(registry.meta, {});
  });

  it('coerces an array meta to empty', () => {
    const registry = new CorporateActionsRegistry({
      actions: [],
      meta: [1, 2, 3],
    });
    assert.deepStrictEqual(registry.meta, {});
  });

  it('throws for a file that does not exist', () => {
    assert.throws(
      () => new CorporateActionsRegistry('/nonexistent/path/actions.json'),
      (err) => err.code === 'ENOENT',
    );
  });

  it('throws for invalid JSON in a file', () => {
    const dir = makeTmpDir();
    const path = require('path').join(dir, 'bad.json');
    fs.writeFileSync(path, '{ not valid json');
    assert.throws(
      () => new CorporateActionsRegistry(path),
      (err) => err instanceof SyntaxError,
    );
  });

  it('length getter returns the count', () => {
    const registry = makeRegistry();
    assert.strictEqual(registry.length, 4);
    assert.strictEqual(registry.count(), 4);
  });

});


// ----------------------------------------------------------------------
// byIsin
// ----------------------------------------------------------------------

describe('byIsin', () => {

  it('returns the correct actions for a known ISIN', () => {
    const registry = makeRegistry();
    const aapl = registry.byIsin('US0378331005');
    assert.strictEqual(aapl.length, 2);
    assert.ok(aapl.every((a) => a.isin === 'US0378331005'));
  });

  it('returns an empty array for an unknown ISIN', () => {
    const registry = makeRegistry();
    assert.deepStrictEqual(registry.byIsin('US0000000000'), []);
  });

  it('is case-sensitive', () => {
    const registry = makeRegistry();
    assert.deepStrictEqual(registry.byIsin('us0378331005'), []);
  });

  it('returns a fresh array each call', () => {
    const registry = makeRegistry();
    const first = registry.byIsin('US0378331005');
    first.push({ fake: true });
    const second = registry.byIsin('US0378331005');
    assert.strictEqual(second.length, 2);
  });

  it('returns actions in insertion order', () => {
    const registry = makeRegistry();
    const ids = registry.byIsin('US0378331005').map((a) => a.action_id);
    assert.deepStrictEqual(ids, [
      'US0378331005-DIVIDEND-2024-05-16-0.2500',
      'US0378331005-SPLIT-2020-08-31-4-1',
    ]);
  });

});


// ----------------------------------------------------------------------
// byActionId
// ----------------------------------------------------------------------

describe('byActionId', () => {

  it('returns the action when found', () => {
    const registry = makeRegistry();
    const action = registry.byActionId('US67066G1040-SPLIT-2024-06-10-10-1');
    assert.ok(action);
    assert.strictEqual(action.action_type, 'SPLIT');
    assert.strictEqual(action.ratio, '10:1');
  });

  it('returns null for an unknown ID', () => {
    const registry = makeRegistry();
    assert.strictEqual(registry.byActionId('NONEXISTENT'), null);
  });

  it('returns a deep copy: mutating top-level fields does not corrupt state', () => {
    const registry = makeRegistry();
    const action = registry.byActionId('US67066G1040-SPLIT-2024-06-10-10-1');
    action.ratio = '999:1';
    const again = registry.byActionId('US67066G1040-SPLIT-2024-06-10-10-1');
    assert.strictEqual(again.ratio, '10:1');
  });

  it('returns a deep copy: mutating dates does not corrupt state', () => {
    const registry = makeRegistry();
    const action = registry.byActionId('US67066G1040-SPLIT-2024-06-10-10-1');
    action.dates.ex_date = '1900-01-01';
    const again = registry.byActionId('US67066G1040-SPLIT-2024-06-10-10-1');
    assert.strictEqual(again.dates.ex_date, '2024-06-10');
  });

  it('returns a deep copy: mutating provenance does not corrupt state', () => {
    const registry = makeRegistry();
    const action = registry.byActionId('US0378331005-DIVIDEND-2024-05-16-0.2500');
    action.provenance.source = 'mutated';
    const again = registry.byActionId('US0378331005-DIVIDEND-2024-05-16-0.2500');
    assert.strictEqual(again.provenance.source, 'Apple');
  });

  it('returns a deep copy: mutating impact does not corrupt state', () => {
    const registry = makeRegistry();
    const action = registry.byActionId('US0378331005-DIVIDEND-2024-05-16-0.2500');
    action.impact.cash_adjustment = 999;
    const again = registry.byActionId('US0378331005-DIVIDEND-2024-05-16-0.2500');
    assert.strictEqual(again.impact.cash_adjustment, 0.25);
  });

  it('returns distinct objects on repeated calls', () => {
    const registry = makeRegistry();
    const a = registry.byActionId('US67066G1040-SPLIT-2024-06-10-10-1');
    const b = registry.byActionId('US67066G1040-SPLIT-2024-06-10-10-1');
    assert.notStrictEqual(a, b);
    assert.strictEqual(a.action_id, b.action_id);
  });

});


// ----------------------------------------------------------------------
// byActionType
// ----------------------------------------------------------------------

describe('byActionType', () => {

  it('returns all splits', () => {
    const registry = makeRegistry();
    const splits = registry.byActionType('SPLIT');
    assert.strictEqual(splits.length, 2);
    assert.ok(splits.every((a) => a.action_type === 'SPLIT'));
  });

  it('returns all dividends', () => {
    const registry = makeRegistry();
    const divs = registry.byActionType('DIVIDEND');
    assert.strictEqual(divs.length, 1);
    assert.strictEqual(divs[0].amount, 0.25);
  });

  it('returns all symbol changes', () => {
    const registry = makeRegistry();
    const changes = registry.byActionType('SYMBOL_CHANGE');
    assert.strictEqual(changes.length, 1);
  });

  it('returns an empty array for an unknown type', () => {
    const registry = makeRegistry();
    assert.deepStrictEqual(registry.byActionType('MERGER'), []);
  });

  it('is case-sensitive', () => {
    const registry = makeRegistry();
    assert.deepStrictEqual(registry.byActionType('split'), []);
  });

  it('returns a fresh array each call', () => {
    const registry = makeRegistry();
    const first = registry.byActionType('SPLIT');
    first.push({ fake: true });
    const second = registry.byActionType('SPLIT');
    assert.strictEqual(second.length, 2);
  });

});


// ----------------------------------------------------------------------
// byDateRange
// ----------------------------------------------------------------------

describe('byDateRange', () => {

  // Default field --------------------------------------------------

  it('defaults to ex_date', () => {
    const registry = makeRegistry();
    const withDefault = registry.byDateRange('2024-01-01', '2024-12-31');
    const withExplicit = registry.byDateRange('2024-01-01', '2024-12-31', 'ex_date');
    assert.deepStrictEqual(
      withDefault.map((a) => a.action_id),
      withExplicit.map((a) => a.action_id),
    );
  });

  // Valid fields ---------------------------------------------------

  it('filters on ex_date', () => {
    const registry = makeRegistry();
    const result = registry.byDateRange('2020-01-01', '2023-12-31', 'ex_date');
    assert.strictEqual(result.length, 1);
    assert.strictEqual(result[0].action_id, 'US0378331005-SPLIT-2020-08-31-4-1');
  });

  it('filters on effective_date', () => {
    const registry = makeRegistry();
    const result = registry.byDateRange('2020-01-01', '2023-12-31', 'effective_date');
    const ids = result.map((a) => a.action_id);
    assert.strictEqual(result.length, 2);
    assert.ok(ids.includes('US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL'));
    assert.ok(ids.includes('US0378331005-SPLIT-2020-08-31-4-1'));
  });

  it('filters on announcement', () => {
    const registry = makeRegistry();
    const result = registry.byDateRange('2022-01-01', '2023-12-31', 'announcement');
    assert.strictEqual(result.length, 1);
    assert.strictEqual(result[0].action_id, 'US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL');
  });

  it('filters on record_date', () => {
    const registry = makeRegistry();
    const result = registry.byDateRange('2020-01-01', '2024-12-31', 'record_date');
    // Three of the four have a record_date; SYMBOL_CHANGE does not.
    assert.strictEqual(result.length, 3);
  });

  // Invalid fields -------------------------------------------------

  for (const bad of ['exdate', 'ex-date', 'effective', 'Ex_Date', 'EX_DATE', 'ex_date ', ' ex_date', '']) {
    it(`throws on invalid date field ${JSON.stringify(bad)}`, () => {
      const registry = makeRegistry();
      assert.throws(
        () => registry.byDateRange(null, null, bad),
        /invalid dateField/,
      );
    });
  }

  it('names the offending value in the error message', () => {
    const registry = makeRegistry();
    assert.throws(
      () => registry.byDateRange(null, null, 'exdate'),
      /'exdate'/,
    );
  });

  it('lists valid values in the error message', () => {
    const registry = makeRegistry();
    try {
      registry.byDateRange(null, null, 'exdate');
      assert.fail('expected an error');
    } catch (err) {
      for (const valid of ['announcement', 'ex_date', 'record_date', 'effective_date']) {
        assert.ok(err.message.includes(valid), `missing ${valid} in message`);
      }
    }
  });

  // Inclusive bounds -----------------------------------------------

  it('includes actions exactly on the start bound', () => {
    const registry = makeRegistry();
    const result = registry.byDateRange('2024-05-16', '2024-12-31', 'ex_date');
    const ids = result.map((a) => a.action_id);
    assert.ok(ids.includes('US0378331005-DIVIDEND-2024-05-16-0.2500'));
  });

  it('includes actions exactly on the end bound', () => {
    const registry = makeRegistry();
    const result = registry.byDateRange('2020-01-01', '2024-05-16', 'ex_date');
    const ids = result.map((a) => a.action_id);
    assert.ok(ids.includes('US0378331005-DIVIDEND-2024-05-16-0.2500'));
  });

  it('handles a single-date range', () => {
    const registry = makeRegistry();
    const result = registry.byDateRange('2024-05-16', '2024-05-16', 'ex_date');
    assert.strictEqual(result.length, 1);
    assert.strictEqual(result[0].action_id, 'US0378331005-DIVIDEND-2024-05-16-0.2500');
  });

  // Open bounds ----------------------------------------------------

  it('treats a null start as open', () => {
    const registry = makeRegistry();
    const result = registry.byDateRange(null, '2024-01-01', 'ex_date');
    assert.strictEqual(result.length, 1);
    assert.strictEqual(result[0].action_id, 'US0378331005-SPLIT-2020-08-31-4-1');
  });

  it('treats a null end as open', () => {
    const registry = makeRegistry();
    const result = registry.byDateRange('2024-01-01', null, 'ex_date');
    assert.strictEqual(result.length, 2);
  });

  it('treats both null bounds as fully open', () => {
    const registry = makeRegistry();
    const result = registry.byDateRange(null, null, 'ex_date');
    assert.strictEqual(result.length, 3);
  });

  it('treats an empty string bound the same as null', () => {
    const registry = makeRegistry();
    const withNull = registry.byDateRange(null, null, 'ex_date').map((a) => a.action_id);
    const withEmpty = registry.byDateRange('', '', 'ex_date').map((a) => a.action_id);
    assert.deepStrictEqual(withNull, withEmpty);
  });

  it('treats an undefined bound the same as null', () => {
    const registry = makeRegistry();
    const withNull = registry.byDateRange(null, null, 'ex_date').map((a) => a.action_id);
    const withUndef = registry.byDateRange(undefined, undefined, 'ex_date').map((a) => a.action_id);
    assert.deepStrictEqual(withNull, withUndef);
  });

  // Skipping actions without the field -----------------------------

  it('skips actions with no ex_date', () => {
    const registry = makeRegistry();
    const ids = registry.byDateRange(null, null, 'ex_date').map((a) => a.action_id);
    assert.ok(!ids.includes('US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL'));
  });

  it('skips actions with no record_date', () => {
    const registry = makeRegistry();
    const ids = registry.byDateRange(null, null, 'record_date').map((a) => a.action_id);
    assert.ok(!ids.includes('US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL'));
  });

  // Sorting --------------------------------------------------------

  it('sorts results by the requested field', () => {
    const registry = makeRegistry();
    const dates = registry.byDateRange(null, null, 'ex_date').map((a) => a.dates.ex_date);
    assert.deepStrictEqual(dates, [...dates].sort());
  });

  it('sorts results by effective_date', () => {
    const registry = makeRegistry();
    const dates = registry.byDateRange(null, null, 'effective_date').map((a) => a.dates.effective_date);
    assert.deepStrictEqual(dates, [...dates].sort());
  });

  it('breaks ties on action_id', () => {
    const registry = new CorporateActionsRegistry(tiebreakData());
    const ids = registry.byDateRange(null, null, 'ex_date').map((a) => a.action_id);
    assert.deepStrictEqual(ids, [
      'US0000000001-DIVIDEND-2024-05-16-0.2500',
      'US0000000002-DIVIDEND-2024-05-16-0.3000',
    ]);
  });

  it('sorts regardless of input order', () => {
    const data = sampleData();
    data.actions.reverse();
    const registry = new CorporateActionsRegistry(data);
    const dates = registry.byDateRange(null, null, 'ex_date').map((a) => a.dates.ex_date);
    assert.deepStrictEqual(dates, [...dates].sort());
  });

  // Fresh array ----------------------------------------------------

  it('returns a fresh array each call', () => {
    const registry = makeRegistry();
    const first = registry.byDateRange(null, null, 'ex_date');
    first.length = 0;
    const second = registry.byDateRange(null, null, 'ex_date');
    assert.strictEqual(second.length, 3);
  });

});


// ----------------------------------------------------------------------
// allActionTypes
// ----------------------------------------------------------------------

describe('allActionTypes', () => {

  it('returns sorted, unique types', () => {
    const registry = makeRegistry();
    assert.deepStrictEqual(
      registry.allActionTypes(),
      ['DIVIDEND', 'SPLIT', 'SYMBOL_CHANGE'],
    );
  });

  it('returns an empty array for an empty registry', () => {
    const registry = new CorporateActionsRegistry({ actions: [] });
    assert.deepStrictEqual(registry.allActionTypes(), []);
  });

  it('reflects only types present in the data', () => {
    const registry = makeRegistry();
    const types = registry.allActionTypes();
    assert.ok(!types.includes('MERGER'));
    assert.ok(!types.includes('SPINOFF'));
    assert.ok(!types.includes('REVERSE_SPLIT'));
  });

});


// ----------------------------------------------------------------------
// count
// ----------------------------------------------------------------------

describe('count', () => {

  it('returns the number of actions', () => {
    const registry = makeRegistry();
    assert.strictEqual(registry.count(), 4);
  });

  it('returns zero for an empty registry', () => {
    const registry = new CorporateActionsRegistry({ actions: [] });
    assert.strictEqual(registry.count(), 0);
  });

  it('matches the length getter', () => {
    const registry = makeRegistry();
    assert.strictEqual(registry.count(), registry.length);
  });

});


// ----------------------------------------------------------------------
// Serialization: toJSON
// ----------------------------------------------------------------------

describe('toJSON', () => {

  it('returns an object with meta and actions', () => {
    const registry = makeRegistry();
    const out = registry.toJSON();
    assert.ok(Object.prototype.hasOwnProperty.call(out, 'meta'));
    assert.ok(Object.prototype.hasOwnProperty.call(out, 'actions'));
    assert.strictEqual(out.actions.length, 4);
  });

  it('preserves meta fields', () => {
    const registry = makeRegistry();
    const out = registry.toJSON();
    assert.strictEqual(out.meta.version, '1.0.0');
    assert.strictEqual(out.meta.source, 'Test');
  });

  it('preserves action fields', () => {
    const registry = makeRegistry();
    const first = registry.toJSON().actions[0];
    assert.strictEqual(first.isin, 'US67066G1040');
    assert.strictEqual(first.action_type, 'SPLIT');
    assert.strictEqual(first.ratio, '10:1');
    assert.strictEqual(first.dates.ex_date, '2024-06-10');
  });

  it('returns fresh data: mutating meta does not corrupt state', () => {
    const registry = makeRegistry();
    const out = registry.toJSON();
    out.meta.version = 'mutated';
    const again = registry.toJSON();
    assert.strictEqual(again.meta.version, '1.0.0');
  });

  it('returns fresh data: mutating an action does not corrupt state', () => {
    const registry = makeRegistry();
    const out = registry.toJSON();
    out.actions[0].ratio = '999:1';
    out.actions[0].dates.ex_date = '1900-01-01';
    const again = registry.toJSON();
    assert.strictEqual(again.actions[0].ratio, '10:1');
    assert.strictEqual(again.actions[0].dates.ex_date, '2024-06-10');
  });

  it('returns fresh data: pushing to the returned array does not corrupt state', () => {
    const registry = makeRegistry();
    const out = registry.toJSON();
    out.actions.push({ fake: true });
    const again = registry.toJSON();
    assert.strictEqual(again.actions.length, 4);
  });

  it('is JSON-serializable', () => {
    const registry = makeRegistry();
    const json = JSON.stringify(registry.toJSON());
    const parsed = JSON.parse(json);
    assert.strictEqual(parsed.actions.length, 4);
  });

});


// ----------------------------------------------------------------------
// Serialization: save
// ----------------------------------------------------------------------

describe('save', () => {

  it('writes a file that can be reloaded', () => {
    const registry = makeRegistry();
    const dir = makeTmpDir();
    const outPath = path.join(dir, 'out.json');
    registry.save(outPath);
    const loaded = new CorporateActionsRegistry(outPath);
    assert.strictEqual(loaded.count(), registry.count());
    assert.deepStrictEqual(loaded.toJSON(), registry.toJSON());
  });

  it('produces valid JSON', () => {
    const registry = makeRegistry();
    const dir = makeTmpDir();
    const outPath = path.join(dir, 'out.json');
    registry.save(outPath);
    const parsed = JSON.parse(fs.readFileSync(outPath, 'utf8'));
    assert.strictEqual(parsed.actions.length, 4);
  });

  it('does not write a BOM', () => {
    const registry = makeRegistry();
    const dir = makeTmpDir();
    const outPath = path.join(dir, 'out.json');
    registry.save(outPath);
    const firstBytes = fs.readFileSync(outPath).subarray(0, 3);
    assert.notDeepStrictEqual(firstBytes, Buffer.from([0xef, 0xbb, 0xbf]));
  });

  it('round-trips an empty registry', () => {
    const registry = new CorporateActionsRegistry({ actions: [] });
    const dir = makeTmpDir();
    const outPath = path.join(dir, 'empty.json');
    registry.save(outPath);
    const loaded = new CorporateActionsRegistry(outPath);
    assert.strictEqual(loaded.count(), 0);
  });

  it('round-trips with two save calls to distinct paths', () => {
    const registry = makeRegistry();
    const dir1 = makeTmpDir();
    const dir2 = makeTmpDir();
    const p1 = path.join(dir1, 'a.json');
    const p2 = path.join(dir2, 'b.json');
    registry.save(p1);
    registry.save(p2);
    assert.strictEqual(fs.readFileSync(p1, 'utf8'), fs.readFileSync(p2, 'utf8'));
  });

});


// ----------------------------------------------------------------------
// Cross-language contract fixture
// ----------------------------------------------------------------------

const contractFixturePath = path.resolve(
  __dirname, '..', '..', '..', 'tests', 'wrapper_contract.json',
);

if (fs.existsSync(contractFixturePath)) {

  const fixture = JSON.parse(fs.readFileSync(contractFixturePath, 'utf8'));

  describe('ContractFixture', () => {

    it('matches every query in the shared fixture', () => {
      const registry = new CorporateActionsRegistry({
        meta: {},
        actions: fixture.actions,
      });
      for (const query of fixture.queries) {
        const result = registry.byDateRange(
          query.start, query.end, query.date_field,
        );
        const ids = result.map((a) => a.action_id);
        assert.deepStrictEqual(
          ids,
          query.expected_action_ids,
          `query ${JSON.stringify(query)} returned ${JSON.stringify(ids)}`,
        );
      }
    });

    it('rejects every invalid date field in the shared fixture', () => {
      const registry = new CorporateActionsRegistry({
        meta: {},
        actions: fixture.actions,
      });
      for (const bad of fixture.invalid_date_fields) {
        assert.throws(
          () => registry.byDateRange(null, null, bad),
          /invalid dateField/,
        );
      }
    });

  });

} else {
  describe('ContractFixture', () => {
    it('fixture must exist', () => {
      assert.fail(
        `tests/wrapper_contract.json not found at ${contractFixturePath}. ` +
        `The wrapper contract tests cannot be skipped.`
      );
    });
  });
}
#!/usr/bin/env node
/**
 * JavaScript Example: Querying the Corporate Actions Registry
 *
 * Demonstrates how to use the JavaScript wrapper
 * (`corporate-actions-registry`) to load and query actions.json.
 *
 * Prerequisites:
 *   npm install corporate-actions-registry
 *
 *   Or, from the repository root:
 *     cd wrappers/javascript && npm install && npm link
 *     cd ../../examples && npm link corporate-actions-registry
 *
 * Run:
 *   node examples/javascript_lookup.js
 *   node examples/javascript_lookup.js --isin US0378331005
 *   node examples/javascript_lookup.js --action-type DIVIDEND
 *   node examples/javascript_lookup.js --action-id US0378331005-DIVIDEND-2024-05-10-0.2500
 *   node examples/javascript_lookup.js --date-range 2020-01-01 2023-12-31
 */

'use strict';

const fs = require('fs');
const path = require('path');

// ----------------------------------------------------------------------
// Load the wrapper: try installed module first, then local fallback
// ----------------------------------------------------------------------
let CorporateActionsRegistry;
try {
  ({ CorporateActionsRegistry } = require('corporate-actions-registry'));
} catch (e) {
  // Fallback: use the local wrapper source
  const local = path.resolve(__dirname, '..', 'wrappers', 'javascript', 'src', 'index.js');
  ({ CorporateActionsRegistry } = require(local));
}

// ----------------------------------------------------------------------
// Locate actions.json
// ----------------------------------------------------------------------
function findActionsFile(cliPath) {
  if (cliPath) {
    if (!fs.existsSync(cliPath)) {
      console.error(`Error: file not found: ${cliPath}`);
      process.exit(2);
    }
    return cliPath;
  }

  const cwdFile = path.resolve(process.cwd(), 'actions.json');
  if (fs.existsSync(cwdFile)) return cwdFile;

  const repoFile = path.resolve(__dirname, '..', 'actions.json');
  if (fs.existsSync(repoFile)) return repoFile;

  console.error('Error: could not find actions.json. Use --actions PATH.');
  process.exit(2);
}

// ----------------------------------------------------------------------
// Pretty printers
// ----------------------------------------------------------------------
function printAction(action) {
  console.log(`  action_id:   ${action.action_id}`);
  console.log(`  isin:        ${action.isin}`);
  console.log(`  action_type: ${action.action_type}`);
  if (action.ratio) console.log(`  ratio:       ${action.ratio}`);
  if (action.amount !== undefined && action.amount !== null) {
    console.log(`  amount:      ${action.amount} ${action.currency || ''}`.trim());
  }
  const d = action.dates || {};
  if (d.announcement) console.log(`  announced:   ${d.announcement}`);
  if (d.ex_date) console.log(`  ex_date:     ${d.ex_date}`);
  if (d.record_date) console.log(`  record_date: ${d.record_date}`);
  if (d.effective_date) console.log(`  effective:   ${d.effective_date}`);
  if (action.provenance && action.provenance.source_url) {
    console.log(`  source:      ${action.provenance.source_url}`);
  }
  const im = action.impact || {};
  const parts = [];
  if (im.price_multiplier !== undefined && im.price_multiplier !== null) {
    parts.push(`price×${im.price_multiplier}`);
  }
  if (im.share_multiplier !== undefined && im.share_multiplier !== null) {
    parts.push(`share×${im.share_multiplier}`);
  }
  if (im.cash_adjustment !== undefined && im.cash_adjustment !== null) {
    parts.push(`cash+${im.cash_adjustment}`);
  }
  if (parts.length) console.log(`  impact:      ${parts.join(', ')}`);
}

function printActions(actions, header) {
  if (!actions || actions.length === 0) {
    console.log(`${header}: (none)`);
    return;
  }
  console.log(`${header}: ${actions.length} action(s)`);
  for (const a of actions) {
    console.log();
    printAction(a);
  }
}

// ----------------------------------------------------------------------
// Argument parsing (minimal, no external deps)
// ----------------------------------------------------------------------
function parseArgs(argv) {
  const args = {
    actions: null,
    isin: null,
    actionId: null,
    actionType: null,
    dateRange: null,
    dateField: 'ex_date',
    summary: false,
  };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case '--actions':
        args.actions = argv[++i]; break;
      case '--isin':
        args.isin = argv[++i]; break;
      case '--action-id':
        args.actionId = argv[++i]; break;
      case '--action-type':
        args.actionType = argv[++i]; break;
      case '--date-range':
        args.dateRange = [argv[++i], argv[++i]]; break;
      case '--date-field':
        args.dateField = argv[++i]; break;
      case '--summary':
        args.summary = true; break;
      case '--help':
      case '-h':
        printUsage();
        process.exit(0);
      default:
        console.error(`Unknown argument: ${a}`);
        printUsage();
        process.exit(2);
    }
  }
  return args;
}

function printUsage() {
  console.log(`Usage: node examples/javascript_lookup.js [options]

Options:
  --actions PATH                     Path to actions.json
  --isin ISIN                        Look up all actions for an ISIN
  --action-id ID                     Look up one action by action_id
  --action-type TYPE                 Filter by type (SPLIT, DIVIDEND, ...)
  --date-range START END             Filter by date range (YYYY-MM-DD)
  --date-field FIELD                 Date field to filter on
                                     (announcement, ex_date, record_date, effective_date)
  --summary                          Only print summary counts
  --help, -h                         Show this help message`);
}

// ----------------------------------------------------------------------
// Main
// ----------------------------------------------------------------------
function main() {
  const args = parseArgs(process.argv);
  const actionsPath = findActionsFile(args.actions);

  console.log(`Loading registry from: ${actionsPath}`);

  let registry;
  try {
    registry = new CorporateActionsRegistry(actionsPath);
  } catch (e) {
    console.error(`Error loading registry: ${e.message}`);
    process.exit(1);
  }

  const meta = registry.meta || {};
  console.log(`  version:       ${meta.version}`);
  console.log(`  source:        ${meta.source}`);
  console.log(`  generated_at:  ${meta.generated_at}`);
  console.log(`  total actions: ${registry.count()}`);
  console.log(`  action types:  ${registry.allActionTypes().join(', ')}`);
  console.log();

  // Targeted queries
  if (args.actionId) {
    const action = registry.byActionId(args.actionId);
    printActions(action ? [action] : [], `Lookup by action_id '${args.actionId}'`);
    return;
  }

  if (args.isin) {
    printActions(registry.byIsin(args.isin), `Lookup by ISIN '${args.isin}'`);
    return;
  }

  if (args.actionType) {
    printActions(
      registry.byActionType(args.actionType),
      `Lookup by action_type '${args.actionType}'`
    );
    return;
  }

  if (args.dateRange) {
    const [start, end] = args.dateRange;
    printActions(
      registry.byDateRange(start, end, args.dateField),
      `Lookup by ${args.dateField} between ${start} and ${end}`
    );
    return;
  }

  // Default summary
  console.log('Registry summary by action type:');
  for (const t of registry.allActionTypes()) {
    const acts = registry.byActionType(t);
    console.log(`  ${t}: ${acts.length}`);
  }

  console.log();
  console.log('First 3 actions (for illustration):');
  for (const a of registry.actions.slice(0, 3)) {
    console.log();
    printAction(a);
  }

  if (!args.summary) {
    console.log();
    console.log('Use --isin, --action-id, --action-type, or --date-range for targeted queries.');
    console.log('Run with --help for full usage.');
  }
}

main();
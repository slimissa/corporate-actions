# Scripts

Operational scripts for the Corporate Actions Registry. These are the tools
you run locally or from CI to fetch, merge, validate, and notify on changes
to `actions.json`.

The scripts in this folder are **for maintenance and automation**, not for
end-user consumption. If you are using the registry in your own project, see
the four language wrappers in `wrappers/`.

---

## Contents

| Script | Purpose | Runs in CI? |
|--------|---------|-------------|
| [`notify_on_change.py`](#notify_on_changepy) | Detect changes to `actions.json` and optionally POST to a webhook | Indirectly (`run_update.sh` calls it) |
| [`run_update.sh`](#run_update.sh) | Full pipeline: fetch → merge → derive → validate → test → build → commit | Via `.github/workflows/update-actions.yml` |

The previous `sync_wrappers.sh` was removed in v1.0.1. The wrappers load
`actions.json` by path; they do not embed a copy, so syncing was unnecessary.

---

## `notify_on_change.py`

Detects when `actions.json` has changed since the last run and, optionally,
sends a JSON payload to a webhook. Uses SHA-256 hashing and a small state
file to avoid duplicate notifications.

### When to run

- As part of a scheduled job after `run_update.sh`.
- Manually after editing `actions.json` to broadcast the change.
- In a CI workflow that wants to be notified of data drift.

### Usage

```bash
# Detect change and update the state file
python scripts/notify_on_change.py --actions actions.json

# Also POST to a webhook on change
python scripts/notify_on_change.py \
  --actions actions.json \
  --webhook-url https://hooks.example.com/corporate-actions

# Custom state file
python scripts/notify_on_change.py \
  --actions actions.json \
  --state /var/lib/quantos/corp_actions.state

# Verbose
python scripts/notify_on_change.py --actions actions.json --verbose
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--actions` | `actions.json` | Path to the file to watch |
| `--state` | `.notify_state.json` | Path to the state file that stores the last hash |
| `--webhook-url` | *(none)* | If set, POST a JSON payload on change |
| `--verbose` | `false` | Print detailed progress |

### Behavior

1. Compute SHA-256 of `actions.json`.
2. Load the previous hash from the state file (or `{}` if missing).
3. If the hash is identical → exit silently, no state write.
4. If the hash differs (or state is missing) → print a change notification,
   optionally POST to webhook, then write the new state.

The webhook payload is:

```json
{
  "event": "corporate_actions_changed",
  "actions_path": "actions.json",
  "old_hash": "abc...",
  "new_hash": "def...",
  "timestamp": "2026-09-13T01:22:25.123456+00:00"
}
```

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | No change, or change successfully processed |
| `1` | File missing, unreadable, or state write failed |
| `2` | Usage error |

Note: a webhook failure **does not** cause a non-zero exit. The state file
is still updated, so the next run will not retry the same notification.
This is intentional: webhook failures are noisy but not fatal.

### Dependencies

None beyond the Python 3.8+ standard library.

### Tests

```bash
pytest tests/test_notify_on_change.py -v
```

Covers hash computation, state persistence, webhook failure handling, and
the CLI end-to-end. 16 tests.

---

## `run_update.sh`

The end-to-end maintenance pipeline. Runs every stage required to refresh,
validate, and optionally commit an updated `actions.json`.

### When to run

- **Weekly** from cron or a scheduled GitHub Action (see `.github/workflows/update-actions.yml`).
- **Manually** before tagging a release.
- **After changing** a fetcher or the schema, to verify the pipeline is still intact.

### Usage

```bash
# Full pipeline, default source (Yahoo), no commit
scripts/run_update.sh

# Fast smoke test — no fetch, no tests, no build
scripts/run_update.sh --skip-fetch --skip-tests --skip-build --verbose

# Dry-run: fetch and validate, but do not commit or tag
scripts/run_update.sh --fetch-source yahoo --dry-run --verbose

# Full pipeline with commit
scripts/run_update.sh --commit

# Full pipeline with commit and tag
scripts/run_update.sh --commit --tag v1.0.2
```

### What it does, in order

1. Resolve input paths (Asset Identifiers, ISO 4217, Exchange Calendar, schema).
2. Refuse broken fetch sources (`sec`, `nasdaq`) with a clear error.
3. Validate all required input files exist.
4. Fetch new actions via Yahoo Finance (unless `--skip-fetch`).
5. Merge fetched actions into `actions.json` with fuzzy dedup on
   `(isin, action_type, ex_date, ratio, amount)`.
6. Derive impact multipliers via `tools/derive_impacts.py`.
7. Validate `actions.json` via `tools/validate.py`.
8. Run all test suites (root Python, Python wrapper, JavaScript, Go, Rust)
   unless `--skip-tests`.
9. Build distribution artifacts via `tools/build.py` unless `--skip-build`.
10. Send a webhook notification if `--webhook-url` is set.
11. Commit and (optionally) tag if `--commit` is set and `--dry-run` is not.

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--identifiers PATH` | auto-resolved | Asset Identifiers `identifiers.json` |
| `--iso4217 PATH` | auto-resolved | ISO 4217 `iso4217.json` |
| `--exchange-calendar PATH` | auto-resolved | Exchange Calendar `calendar.json` |
| `--actions PATH` | `actions.json` | Registry file to update |
| `--schema PATH` | `schema.json` | Schema file |
| `--fetch-source SOURCE` | `yahoo` | Only `yahoo` works today; `sec` and `nasdaq` refuse |
| `--ticker-limit N` | *(all)* | Limit fetcher to first N tickers |
| `--min-actions N` | `1` | Minimum action count for validation to pass |
| `--skip-fetch` | `false` | Skip step 4 |
| `--skip-tests` | `false` | Skip step 8 |
| `--skip-build` | `false` | Skip step 9 |
| `--dry-run` | `false` | Implies `--skip-tests --skip-build`; no commit |
| `--tests` | — | Override `--dry-run`: run tests anyway |
| `--build` | — | Override `--dry-run`: build anyway |
| `--commit` | `false` | Commit the updated `actions.json` after success |
| `--tag VERSION` | *(none)* | Create a git tag after commit |
| `--webhook-url URL` | *(none)* | Notify a webhook after validation |
| `--verbose` | `false` | Print sub-command output |
| `--help`, `-h` | — | Print the header comment |

### Input path resolution

The three cross-reference registries are resolved in this order:

1. **Explicit CLI flag** (`--identifiers`, etc.) — highest priority.
2. **Environment variable** (`CORP_ACTIONS_IDENTIFIERS_PATH`, `CORP_ACTIONS_ISO4217_PATH`, `CORP_ACTIONS_EXCHANGE_CALENDAR_PATH`).
3. **Repo-local fixtures** (`tests/fixtures/identifiers.json`, etc.) — always present, always valid for CI.
4. **Sibling directory** (`../asset-identifiers/identifiers.json`, etc.) — legacy layout.
5. For Asset Identifiers specifically: `$LAS_DATA_HOME/identifiers.json` if set and present.

The chosen paths are printed only in `--verbose` mode.

### Environment variables

| Variable | Purpose |
|----------|---------|
| `CORP_ACTIONS_IDENTIFIERS_PATH` | Override Asset Identifiers path |
| `CORP_ACTIONS_ISO4217_PATH` | Override ISO 4217 path |
| `CORP_ACTIONS_EXCHANGE_CALENDAR_PATH` | Override Exchange Calendar path |
| `CORP_ACTIONS_ACTIONS_PATH` | Override actions file path |
| `CORP_ACTIONS_SCHEMA_PATH` | Override schema path |
| `CORP_ACTIONS_MIN_ACTIONS` | Minimum action count |
| `LAS_DATA_HOME` | Directory containing `identifiers.json` |

### Fetch source status

| Source | Status | Notes |
|--------|--------|-------|
| `yahoo` | ✅ Working | Uses `yfinance`. Reliable for US equities. |
| `sec` | ❌ Broken | Endpoint returns HTTP 500. See issue tracker. |
| `nasdaq` | ❌ Broken | API times out. See issue tracker. |

Passing `--fetch-source sec` or `--fetch-source nasdaq` exits with code 1
and a message pointing to the issue tracker. This is intentional: the script
should fail loudly rather than silently produce nothing.

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Full pipeline succeeded |
| `1` | Any stage failed (validation, tests, fetch) |
| `2` | Usage error (unknown flag, missing argument) |

### Dependencies

- **Bash** ≥ 4 (uses `set -euo pipefail`).
- **Python 3.8+** with `yfinance`, `jsonschema` installed.
- **Node.js 14+** with `npm`.
- **Go 1.21+**.
- **Rust toolchain** with `cargo`.
- **Git** for commit/tag steps.

If Python tests are skipped because `pytest` is missing, the script warns
and continues. JS, Go, and Rust tests still run.

### Example: weekly automation

The GitHub Actions workflow `.github/workflows/update-actions.yml` runs this
script weekly on Monday 07:00 UTC. It fetches fresh data, merges with fuzzy
dedup, runs all tests, and opens a pull request if new actions are found.
See that workflow for the exact invocation.

---

## The `.notify_state.json` file

`notify_on_change.py` writes a small JSON file recording the last-seen hash:

```json
{
  "hash": "9f2c...",
  "updated_at": "2026-09-13T01:22:25.123456+00:00"
}
```

Add it to `.gitignore` (already done). It is state, not data. Deleting it
causes the next run to treat the registry as "changed".

---

## The `fetched_actions.json` file

`run_update.sh` writes the fetcher output to `<repo_root>/fetched_actions.json`
before merging. The file is transient:

- **Not** committed (it is in `.gitignore`).
- Safe to delete at any time.
- Overwritten on every run.

---

## Extending

### Adding a new fetch source

1. Create a new fetcher in `tools/`, e.g. `tools/fetch_alpha_vantage.py`.
2. Add a case to the `case "$FETCH_SOURCE"` block in `run_update.sh`.
3. Remove the source from the "refuse broken fetchers" list if applicable.
4. Document the source in this README and in `docs/data_sources.md`.
5. Add tests.

### Adding a post-processing step

Insert a new `log "..."` / `run_cmd ...` block in `run_update.sh` between
existing stages. Keep it behind a flag (`--skip-X`) so operators can bypass
it if needed.

### Adding a notification channel

`notify_on_change.py` currently supports one webhook. To add Slack, Discord,
or email, either:

- Add a `--slack-url`, `--discord-url`, or `--smtp-*` flag with a
  corresponding function.
- Or, send to a generic webhook that fans out to multiple destinations.

Prefer the second approach — it keeps this script dependency-free.

---

## Related files

- `tools/fetch_yahoo_actions.py` — the working fetcher.
- `tools/validate.py` — the 7-layer validator.
- `tools/derive_impacts.py` — computes price/share multipliers.
- `tools/build.py` — distribution artifacts.
- `.github/workflows/` — CI, source monitoring, and scheduled updates.
- `tests/test_notify_on_change.py` — test coverage for the notification script.

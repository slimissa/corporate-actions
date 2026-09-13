<!--
Thank you for contributing to the Corporate Actions Registry.

This template adapts to the type of change you are submitting. Fill in
the sections that apply to your PR and delete the sections that do not.
Do not submit the template unchanged.

Before opening this PR, please read CONTRIBUTING.md.
-->

## Summary

<!-- One or two sentences. What changes and why. -->

## Type of change

<!-- Check every box that applies. Most PRs touch one or two areas. -->

- [ ] **Data update** — modifying `actions.json` (adding, correcting, or removing actions)
- [ ] **Schema change** — modifying `schema.json` (only in coordination with maintainers)
- [ ] **Tool change** — modifying `tools/` (validator, fetcher, derive, build)
- [ ] **Wrapper change** — modifying one or more of `wrappers/{python,javascript,go,rust}/`
- [ ] **Test change** — modifying `tests/` or a wrapper's test suite
- [ ] **CI change** — modifying `.github/workflows/`
- [ ] **Documentation** — modifying `README.md`, `docs/`, `CHANGELOG.md`, or a wrapper README
- [ ] **Scripts** — modifying `scripts/`
- [ ] **Examples** — modifying `examples/`
- [ ] **Breaking change** — see the dedicated section below

---

## For data updates (modifying `actions.json`)

Skip this section if your PR does not touch `actions.json`.

### What changed

| Field | Before | After |
|-------|--------|-------|
| Total actions | | |
| Instruments covered | | |
| Action types populated | | |

### Source of the change

- [ ] Extracted automatically by a fetcher (`tools/fetch_*.py`)
- [ ] Manually curated from SEC filings
- [ ] Manually curated from exchange announcements
- [ ] Manually curated from company press releases
- [ ] Correction reported via an issue (link below)

**Linked issue**: #

**Source URLs** (at least one per added or corrected action):

```
https://...
https://...
```

### Verification

Every added or corrected action must be independently verifiable. Paste a
short excerpt from each source used.

```
<paste excerpt>
```

### Downstream impact

- [ ] This changes price-adjusted history for one or more instruments.
- [ ] This changes dividend-adjusted total returns.
- [ ] This affects a previously reported share count.
- [ ] This could break existing backtests that depend on the previous data.

### Validation

Run the validator before submitting:

```bash
python3 tools/validate.py \
  --actions actions.json \
  --schema schema.json \
  --identifiers tests/fixtures/identifiers.json \
  --iso4217 tests/fixtures/iso4217.json \
  --exchange-calendar tests/fixtures/exchange_calendar.json
```

- [ ] Validator passes locally (paste output below).
- [ ] If cross-reference warns about missing ISINs, those ISINs are outside the current Asset Identifiers subset (not a bug).

**Validator output**:

```
<paste>
```

---

## For schema changes

Skip this section unless you are modifying `schema.json`.

**Schema changes require maintainer approval before implementation.** Open an
issue first, get sign-off, then open the PR.

- [ ] Maintainer approval obtained (link: #)
- [ ] Schema version bumped according to semver
- [ ] `docs/action_types.md` updated to reflect the change
- [ ] All four wrappers updated if the schema change affects their parsing
- [ ] All wrapper tests updated
- [ ] Root tests updated
- [ ] Existing `actions.json` still validates against the new schema

**Migration plan for existing data**:

<!-- If existing actions.json entries need changes to conform, describe them here. -->

---

## For wrapper changes

Skip this section unless you are modifying a wrapper.

Which wrappers are affected?

- [ ] Python (`wrappers/python/`)
- [ ] JavaScript (`wrappers/javascript/`)
- [ ] Go (`wrappers/go/`)
- [ ] Rust (`wrappers/rust/`)

### Cross-language consistency

If your change affects behavior, verify that all four wrappers return
identical results for the same query on the same data.

| Language | `by_isin` returns same as Python? |
|----------|-----------------------------------|
| Python | n/a (reference) |
| JavaScript | yes / no / not applicable |
| Go | yes / no / not applicable |
| Rust | yes / no / not applicable |

### Wrapper tests

Run the wrapper's test suite before submitting:

```bash
# Python
cd wrappers/python && pytest tests/ -v

# JavaScript
cd wrappers/javascript && npm test

# Go
cd wrappers/go && go test ./registry -v

# Rust
cd wrappers/rust && cargo test
```

- [ ] All affected wrapper tests pass.
- [ ] If you changed the API surface, you added a test that fails without your change.

---

## For tool changes

Skip this section unless you are modifying `tools/`.

Which tool?

- [ ] `validate.py`
- [ ] `derive_impacts.py`
- [ ] `build.py`
- [ ] `fetch_yahoo_actions.py`
- [ ] `fetch_sec_edgar_actions.py`
- [ ] `fetch_dividends_nasdaq.py`

### Behavior change

<!-- Describe what the tool did before and what it does now. -->

### Tests

- [ ] Tests added or updated.
- [ ] Ran `pytest tests/ -v` and all tests pass.
- [ ] If the tool consumes network, verified the run does not introduce rate-limit risk.

---

## For CI changes

Skip this section unless you are modifying `.github/workflows/`.

Which workflow?

- [ ] `validate.yml`
- [ ] `check-sources.yml`
- [ ] `update-actions.yml`

### CI impact

- [ ] The change reduces CI runtime, does not increase it.
- [ ] The change does not introduce new external dependencies without justification.
- [ ] If the change adds a new job, it has a clear failure mode (not silent).
- [ ] If the change touches a scheduled workflow, the schedule has been documented in the workflow header.

### Test run

Trigger the workflow manually to verify before merging:

```bash
gh workflow run <workflow>.yml
gh run watch
```

- [ ] Manual trigger succeeded.
- [ ] Log output for the affected job pasted below.

```
<paste>
```

---

## Breaking changes

Skip this section unless the PR is a breaking change.

A breaking change is any of:

- Removing or renaming a field in `actions.json`
- Removing or renaming an action type
- Changing the schema in a way that invalidates existing data
- Changing a wrapper's public API in a way that breaks existing code
- Removing a CLI flag from a tool

- [ ] This PR contains a breaking change. Checked above.
- [ ] The `CHANGELOG.md` has a `## Unreleased → Breaking` entry.
- [ ] Migration notes are documented (link below).
- [ ] A major version bump is planned.

**Migration notes**:

<!-- How should existing users update their code? -->

---

## Checklist

Before requesting review, confirm:

- [ ] I have read `CONTRIBUTING.md`.
- [ ] I have read `docs/action_types.md` (for data PRs).
- [ ] I have read the relevant wrapper's `README.md` (for wrapper PRs).
- [ ] My changes pass all relevant test suites locally.
- [ ] I have run the validator against `actions.json` (for data PRs).
- [ ] I have not introduced any new dependency without documenting it.
- [ ] I have not modified `actions.json` by hand unless manually curating.
- [ ] I have not removed any existing action without a clear reason.
- [ ] I have not committed any file that belongs in `.gitignore` (caches, build artifacts, state files).
- [ ] I have updated `CHANGELOG.md` if the change is user-visible.
- [ ] I have updated relevant documentation.
- [ ] My commit messages are clear and describe the *why*, not just the *what*.
- [ ] My changes are scoped to this PR — no unrelated cleanup.

---

## How to test this PR locally

<!--
Give the reviewer the exact commands to reproduce your result.
-->

```bash
# Setup
git fetch origin pull/<PR_NUMBER>/head:pr-<PR_NUMBER>
git checkout pr-<PR_NUMBER>
source .venv/bin/activate

# Reproduce the change
<paste commands>

# Verify the result
<paste commands>
```

**Expected result**:

```
<paste expected output>
```

---

## Reviewer notes (for maintainers)

- [ ] Scope is correct — the change is focused and not creeping.
- [ ] Data changes verified against primary sources.
- [ ] Code changes covered by tests.
- [ ] Wrapper changes maintain cross-language consistency.
- [ ] CI changes do not introduce silent failures.
- [ ] No sensitive data, credentials, or local paths committed.
- [ ] Documentation updated where relevant.
- [ ] CHANGELOG updated if user-visible.
- [ ] Ready to squash-merge.
- [ ] Post-merge: confirm CI on `main` is green.

**Post-merge actions**:

- [ ] Delete the branch on GitHub.
- [ ] If data was added, tag a new version per semver (patch for corrections, minor for additions).
- [ ] If a fetcher was fixed, update the status table in `scripts/README.md`.

---

## Screenshots or logs

<!-- Only if relevant. For data PRs, screenshots of the source are rarely useful — link to the URL instead. -->

---

## Related issues and PRs

- Closes #
- Relates to #
- Depends on #
- Supersedes #
# Contributing to the Corporate Actions Registry

Thank you for considering a contribution. This document explains how to
contribute code, data, and tooling to the Corporate Actions Registry. It
is the code contribution guide.

**For documentation contributions**, see [`docs/contributing.md`](./docs/contributing.md).

**For reporting a specific missing or incorrect action**, use the
[Action update issue template](./.github/ISSUE_TEMPLATE/action_update.md).

**For proposing a new data source**, use the
[Data source issue template](./.github/ISSUE_TEMPLATE/data_source.md).

---

## Table of contents

1. [Ways to contribute](#1-ways-to-contribute)
2. [Before you start](#2-before-you-start)
3. [Development setup](#3-development-setup)
4. [Repository layout](#4-repository-layout)
5. [Commit message convention](#5-commit-message-convention)
6. [Branch strategy](#6-branch-strategy)
7. [Pull request workflow](#7-pull-request-workflow)
8. [Code style](#8-code-style)
9. [Testing requirements](#9-testing-requirements)
10. [Data contribution rules](#10-data-contribution-rules)
11. [Reporting bugs](#11-reporting-bugs)
12. [Security disclosure](#12-security-disclosure)
13. [Licensing of contributions](#13-licensing-of-contributions)
14. [Release process](#14-release-process)
15. [Getting help](#15-getting-help)

---

## 1. Ways to contribute

There are eight ways to contribute, in rough order of value to the project:

| # | Contribution | Effort | Skill needed |
|---|--------------|--------|--------------|
| 1 | Fix a broken fetcher | Medium | Python, HTTP APIs |
| 2 | Add a new data source | High | Python, source investigation |
| 3 | Add tests | Low–Medium | Any of the four languages |
| 4 | Report data errors | Low | Domain knowledge |
| 5 | Report bugs with reproductions | Low | Any |
| 6 | Improve documentation | Low–Medium | Writing |
| 7 | Review pull requests | Low–Medium | Familiarity with the codebase |
| 8 | Spread the word | Trivial | — |

The most valuable contributions are the ones that close roadmap items.
See [`docs/roadmap.md`](./docs/roadmap.md) for the current list.

---

## 2. Before you start

Before writing code, answer three questions:

### 2.1 Is this the right repo?

The Corporate Actions Registry is one of four QuantOS registries. If your
change is about instrument identifiers (ISIN, CUSIP, FIGI), it belongs in
**Asset Identifiers**. If it is about currency codes, it belongs in
**ISO 4217**. If it is about exchange hours or holidays, it belongs in
**Exchange Calendar**. Only corporate events (splits, dividends, mergers,
and the like) belong here.

### 2.2 Has it been discussed?

For small changes (typo fixes, one-line bug fixes), skip this step.

For anything larger — a new fetcher, a schema change, a breaking change
to a wrapper API — open an issue first. The maintainer will confirm the
approach before you spend hours on it. A rejected PR after significant
work is worse for everyone than a rejected issue.

### 2.3 Does it break existing users?

Any change that alters:

- The `actions.json` schema in a way that invalidates existing entries
- A wrapper's public API in a way that breaks existing code
- A tool's CLI in a way that removes or renames a flag

is a **breaking change**. Breaking changes require a major version bump.
They are accepted only with a clear rationale and a migration path. Open
an issue first; do not surprise maintainers with a breaking-change PR.

---

## 3. Development setup

### 3.1 Prerequisites

| Tool | Minimum version | Purpose |
|------|-----------------|---------|
| Git | any | Version control |
| Python | 3.8 | Validator, fetchers, tests |
| Node.js | 14 | JavaScript wrapper |
| Go | 1.21 | Go wrapper |
| Rust | stable | Rust wrapper |
| Make | any | Build tooling |

You do not need all four languages to contribute. If you are only fixing
a Python test, you only need Python. Install what your change requires.

### 3.2 Clone and virtual environment

```bash
git clone https://github.com/slimissa/corporate-actions.git
cd corporate-actions

# Create a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install pytest jsonschema yfinance requests
```

The `.venv/` directory is in `.gitignore`. Never commit it.

### 3.3 Verify the setup

Run the validator and the test suite:

```bash
# Validator
python3 tools/validate.py \
  --actions actions.json \
  --schema schema.json \
  --identifiers tests/fixtures/identifiers.json \
  --iso4217 tests/fixtures/iso4217.json \
  --exchange-calendar tests/fixtures/exchange_calendar.json

# Root tests
pytest tests/ -v
```

Expected:

- Validator: `OK: 242 actions validated successfully.`
- Tests: `143 passed`

If either fails on a clean checkout, open an issue. The `main` branch is
expected to be green at all times.

### 3.4 Per-language setup

Only needed if you are working on that wrapper.

**JavaScript wrapper**:

```bash
cd wrappers/javascript
npm install
npm test
```

**Go wrapper**:

```bash
cd wrappers/go
go test ./registry -v
```

**Rust wrapper**:

```bash
cd wrappers/rust
cargo test
```

### 3.5 Editor configuration

No `.editorconfig` is enforced, but every file in this repository uses:

- UTF-8 encoding
- LF line endings (not CRLF)
- 4-space indentation for Python, JavaScript, Go
- 4-space indentation for Rust (rustfmt default)
- 2-space indentation for YAML and JSON

Configure your editor to match. A future `.editorconfig` may be added.

---

## 4. Repository layout

```
corporate-actions/
├── actions.json                 # The registry (242 actions)
├── schema.json                  # JSON Schema for actions.json
├── README.md                    # Overview
├── CONTRIBUTING.md              # This file
├── LICENSE                      # Apache 2.0
├── CHANGELOG.md                 # Version history
│
├── docs/                        # Long-form documentation
│   ├── action_types.md
│   ├── contributing.md
│   ├── data_sources.md
│   ├── roadmap.md
│   └── validation_layers.md
│
├── tools/                       # Python utilities
│   ├── validate.py              # 7-layer validator
│   ├── derive_impacts.py        # Compute multipliers
│   ├── build.py                 # Distribution artifacts
│   ├── fetch_yahoo_actions.py   # Working fetcher
│   ├── fetch_sec_edgar_actions.py   # Broken fetcher
│   └── fetch_dividends_nasdaq.py    # Redundant fetcher
│
├── scripts/                     # Operational scripts
│   ├── run_update.sh            # Full pipeline
│   ├── notify_on_change.py      # SHA-256 change detection
│   └── README.md
│
├── wrappers/                    # Language bindings
│   ├── python/
│   ├── javascript/
│   ├── go/
│   └── rust/
│
├── examples/                    # Usage examples
│   ├── python_lookup.py
│   ├── javascript_lookup.js
│   ├── go_lookup.go
│   ├── rust_lookup.rs
│   └── backtest_adjustment.py
│
├── tests/                       # Root test suite
│   ├── test_*.py
│   └── fixtures/
│       ├── identifiers.json
│       ├── iso4217.json
│       └── exchange_calendar.json
│
└── .github/
    ├── workflows/               # CI
    ├── ISSUE_TEMPLATE/
    └── PULL_REQUEST_TEMPLATE.md
```

### What goes where

- **New fetcher**: `tools/fetch_<source>.py`
- **New validator layer**: `tools/validate.py` + `tests/test_<layer>.py`
- **New wrapper**: `wrappers/<language>/` + `tests/` inside
- **New example**: `examples/<language>_<purpose>.<ext>`
- **New doc**: `docs/<topic>.md`

---

## 5. Commit message convention

Every commit message follows this format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type

Exactly one of:

| Type | When to use |
|------|-------------|
| `feat` | A new feature |
| `fix` | A bug fix |
| `data` | A change to `actions.json` |
| `docs` | Documentation only |
| `test` | Test additions or changes |
| `refactor` | Code change that does not fix a bug or add a feature |
| `chore` | Build, CI, tooling, dependency changes |
| `perf` | Performance improvement |
| `style` | Formatting, whitespace (no code change) |

### Scope

Optional. The area of change:

- `validator`, `fetcher`, `wrappers/python`, `wrappers/rust`, `ci`, `docs`, `schema`

Omit for changes that affect the whole repo.

### Subject

- Imperative present tense: "add" not "added" or "adds"
- Lowercase
- No period at the end
- Under 72 characters

### Body

Optional but recommended for non-trivial changes. Explain the *why*, not
the *what*. The diff shows the *what*; the body explains the motivation.

Wrap at 72 columns. Blank line between subject and body.

### Footer

Optional. Use for:

- `Closes #123` — closes an issue
- `Refs #456` — references an issue without closing
- `BREAKING CHANGE:` — flags a breaking change

### Examples

Good:

```
fix(validator): treat missing isin_warnings as error, not warning

When validate_cross_reference() is called without an isin_warnings list
(as the test suite does), missing ISINs were silently ignored. They are
now treated as errors in that case, preserving the previous test contract
while keeping the default warning behavior for main().

Closes #47
```

Good:

```
data: add NVDA 2000-06-27 2:1 split

Discovered while running the update pipeline against a wider ticker list.
Not previously in the registry because the initial extract was limited to
5 tickers.
```

Bad:

```
fixed stuff
```

Bad:

```
Updated validator.py to fix the bug that was causing issues.
```

The bad examples do not say what was fixed or why.

---

## 6. Branch strategy

The repository uses a simple trunk-based model:

- `main` is the only long-lived branch.
- All work happens on short-lived feature branches.
- Branches are merged via pull request and deleted after merge.

### Branch naming

```
<type>/<short-description>
```

Examples:

- `feat/merger-support`
- `fix/rust-clippy-warnings`
- `data/add-nvda-splits`
- `docs/validation-layers`
- `chore/update-dependencies`

Do not use your username in branch names. Do not use long descriptions.

### `main` is protected

- All changes to `main` go through a PR.
- CI must pass before merge.
- At least one maintainer review is required.

Force-pushing to `main` is disabled.

---

## 7. Pull request workflow

### 7.1 Before opening

1. Sync with `main`:

   ```bash
   git checkout main
   git pull origin main
   ```

2. Create a branch:

   ```bash
   git checkout -b feat/my-change
   ```

3. Make your changes.

4. Run the relevant tests locally (see [Testing requirements](#9-testing-requirements)).

5. Rebase or merge `main` if it has moved:

   ```bash
   git fetch origin
   git rebase origin/main
   ```

   Rebase is preferred over merge for a clean history.

### 7.2 Opening the PR

Open a PR against `main`. The
[PR template](./.github/PULL_REQUEST_TEMPLATE.md) will guide you. Fill in
every section that applies to your change. Do not submit the template
unchanged.

### 7.3 PR size

Keep PRs focused. A PR that fixes one bug and reformats three files is
harder to review than two separate PRs. If you notice unrelated cleanup
while working, do it in a separate PR.

Rule of thumb: if you cannot describe the PR in one sentence, it is
probably two PRs.

### 7.4 Draft PRs

Open as a draft if the change is not ready for review. Draft PRs run CI
but do not request review. Mark ready when done.

### 7.5 Review

A maintainer will review your PR. Expect one of:

- **Approved** — ready to merge.
- **Changes requested** — specific concerns to address.
- **Comment** — questions or suggestions, not blocking.

Respond to every comment. If you disagree, say so with reasoning. If you
agree, push a fix and reply with the commit hash.

### 7.6 Merging

All PRs are squash-merged. The squashed commit message uses the PR title
and body. Write them as if they were the commit message.

Do not merge your own PR unless you are a maintainer.

---

## 8. Code style

### 8.1 Python

- PEP 8.
- 4-space indentation.
- Type hints on public functions.
- Docstrings on modules, classes, and public functions.
- Use `pathlib.Path` over `os.path`.
- Use `datetime.now(timezone.utc)` — not `datetime.utcnow()`.
- No mutable default arguments.

Run `python3 -m py_compile <file>` before committing.

### 8.2 JavaScript

- 2-space indentation.
- Semicolons.
- `const` by default, `let` when reassignment is needed.
- Single quotes for strings.
- No `var`.
- CommonJS (`require`) — do not switch to ESM without a coordinated change.

### 8.3 Go

- `gofmt` is authoritative. Run `go fmt ./...` before committing.
- `go vet` must pass.
- Errors are values; return them, do not panic.
- Tests use the standard library `testing` package; no external test frameworks.

### 8.4 Rust

- `rustfmt` is authoritative. Run `cargo fmt` before committing.
- `cargo clippy --all-targets -- -D warnings` must pass.
- Use `Option` and `Result` — do not panic on recoverable errors.
- Public items have doc comments.
- `thiserror` for error types in the library, not `anyhow`.

### 8.5 Bash

- `set -euo pipefail` at the top.
- Quote variables: `"$VAR"`.
- `[[ ... ]]` instead of `[ ... ]`.
- No `eval`.
- Shellcheck-clean (run `shellcheck scripts/*.sh` before committing).

### 8.6 YAML

- 2-space indentation.
- No trailing whitespace.
- Workflows have a header comment with purpose and triggers.

### 8.7 JSON

- 2-space indentation.
- No trailing commas.
- Field order matches the schema where applicable.

---

## 9. Testing requirements

### 9.1 What must pass

Every PR must pass the full test suite on CI. Run locally what is
relevant to your change before pushing.

### 9.2 Commands

```bash
# Root tests (Python)
pytest tests/ -v

# Python wrapper tests
cd wrappers/python && pytest tests/ -v && cd -

# JavaScript wrapper tests
cd wrappers/javascript && npm test && cd -

# Go wrapper tests
cd wrappers/go && go test ./registry -v && cd -

# Rust wrapper tests
cd wrappers/rust && cargo test && cd -

# Validator
python3 tools/validate.py \
  --actions actions.json \
  --schema schema.json \
  --identifiers tests/fixtures/identifiers.json \
  --iso4217 tests/fixtures/iso4217.json \
  --exchange-calendar tests/fixtures/exchange_calendar.json
```

### 9.3 When to add tests

Add a test when:

- Fixing a bug. The test should fail before the fix and pass after.
- Adding a new function.
- Adding a new validation rule.
- Changing a wrapper's behavior.

Do not add a test that restates the implementation without adding a
distinct assertion. "Test that `add(2, 3)` returns `5`" is not a test; it
is a tautology. "Test that `add` rejects non-numeric input" is a test.

### 9.4 Test structure

Tests use `pytest` (Python), `node --test` (JavaScript), `testing` (Go),
and `#[test]` (Rust). No external test frameworks.

Each test file is named `test_<module>.py` or `test_<module>.js`. Test
functions are named `test_<behavior>`.

### 9.5 Coverage

There is no coverage threshold enforced. Contributors should aim for
the tests to exercise the change, not for a coverage number.

---

## 10. Data contribution rules

The `actions.json` file is special. Its contents are the registry. Data
contributions follow stricter rules than code.

### 10.1 Every action needs a source

Every action must have a `provenance.source_url` pointing to a primary
source:

- SEC filing (8-K, S-4)
- Exchange announcement
- Company press release

Secondary sources (Yahoo Finance, Nasdaq summary pages) are acceptable
only when no primary source is linkable.

Wikipedia, blogs, and social media are not accepted as sources.

### 10.2 Verify before submitting

Before submitting a data PR:

1. Fetch the source URL and confirm it exists.
2. Confirm the source describes the action you are adding.
3. Cross-check the date and ratio (or amount) against at least one
   other source.
4. Check that the action is not already in `actions.json` under a
   different `action_id`.

### 10.3 Use the validator

Run the validator before opening the PR:

```bash
python3 tools/validate.py \
  --actions actions.json \
  --schema schema.json \
  --identifiers tests/fixtures/identifiers.json \
  --iso4217 tests/fixtures/iso4217.json \
  --exchange-calendar tests/fixtures/exchange_calendar.json
```

The PR is not ready if the validator fails.

### 10.4 Do not hand-edit derived fields

The `impact` field is derived by `tools/derive_impacts.py`. Do not
hand-edit it. If the derived value is wrong, the bug is in the
derivation, not in the entry.

If you add an action without an `impact` block, run:

```bash
python3 tools/derive_impacts.py --actions actions.json
```

before committing.

### 10.5 Do not silently modify existing actions

If you are correcting an existing action, keep both:

- The original action (with `status: "CANCELLED"` if applicable)
- The corrected action

Or, if the original is simply wrong, remove it and note in the PR body
why it was incorrect.

Do not silently change dates, ratios, or amounts. Reviewers cannot
verify a silent change.

### 10.6 Data PR must include a validator output

The PR template requires validator output. Paste the full output,
including the summary line.

---

## 11. Reporting bugs

Use the bug report issue template (if present) or open a blank issue
with this information:

### 11.1 Required

- **What you expected to happen**
- **What actually happened**
- **Steps to reproduce**
- **Your environment** (Python version, OS, wrapper language and version)
- **The exact command you ran**

### 11.2 For validator bugs

Include the action that failed validation and the error message. If the
action is valid but the validator rejects it, that is a validator bug.
If the action is invalid but the validator accepts it, that is also a
validator bug.

### 11.3 For wrapper bugs

Include a minimal code snippet that reproduces the issue:

```python
from corporate_actions_registry import CorporateActionsRegistry

registry = CorporateActionsRegistry("actions.json")
# ... the code that fails ...
```

The snippet should be runnable by a maintainer.

### 11.4 For CI bugs

Include the workflow name, run ID, and a link to the failed job. The log
is visible to maintainers; you do not need to paste it.

### 11.5 Not a bug

The following are not bugs:

- Missing data (use the Action update template instead)
- Missing coverage for a source we do not support (use the Data source
  template instead)
- A wrapper API that returns a different type than you expected (read
  the wrapper's README)
- CI warnings about Node.js 20 deprecation (these come from the actions
  themselves and are fixed upstream)

---

## 12. Security disclosure

If you discover a security vulnerability, do not open a public issue.
Report it privately:

1. Go to the repository on GitHub.
2. Click **Security** → **Report a vulnerability**.

Include:

- The affected component (validator, fetcher, wrapper, workflow)
- A description of the vulnerability
- Reproduction steps
- The impact you believe it has

Expected response time: within 7 days. Coordinated disclosure: 90 days
from initial report, unless we agree on a different timeline.

Do not include details of the vulnerability in public issues, discussions,
or social media until coordinated disclosure is complete.

---

## 13. Licensing of contributions

The repository is licensed under **Apache 2.0**. See [`LICENSE`](./LICENSE).

By submitting a contribution, you agree that:

1. Your contribution is licensed under Apache 2.0.
2. You have the right to submit it under that license.
3. You are not violating any third party's rights by submitting it.

You do not need to sign a CLA. The Apache 2.0 license includes a
contribution grant (Section 5) that covers the common case.

### Data contributions

Data in `actions.json` is factual and, where applicable, sourced from
public filings and announcements. Contributions of data must come from
sources that permit redistribution, as documented in
[`docs/data_sources.md`](./docs/data_sources.md).

Do not submit data extracted from sources that prohibit redistribution
(Bloomberg, Refinitiv, CUSIP Global Services). If you are unsure about a
source's licensing, ask before submitting.

---

## 14. Release process

Releases are made by maintainers.

### 14.1 Pre-release checklist

- [ ] All CI checks pass on `main`.
- [ ] `actions.json` validates.
- [ ] `--min-actions` floor is met.
- [ ] `CHANGELOG.md` has an entry for the version.
- [ ] Wrapper versions are consistent (all four at the same version).
- [ ] No uncommitted work in progress.

### 14.2 Versioning

Follow semantic versioning:

- **Major** — breaking changes to schema, wrappers, or tool CLIs.
- **Minor** — new actions, new instruments, new action types populated.
- **Patch** — data corrections, documentation fixes, non-breaking tool
  changes.

### 14.3 Steps

```bash
# Update CHANGELOG.md
# Update version strings in:
#   - schema.json         (meta.version)
#   - actions.json        (meta.version)
#   - wrappers/*/         (package versions)

git add -A
git commit -m "chore: prepare release vX.Y.Z"
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin main --tags
```

### 14.4 Post-release

- Create the GitHub release page (`gh release create vX.Y.Z`).
- Publish updated wrappers to their registries.
- Update `docs/roadmap.md` with the shipped version.

---

## 15. Getting help

Three places to ask questions:

| Question type | Where |
|---------------|-------|
| Bug reports and feature requests | GitHub Issues |
| General questions and discussions | GitHub Discussions |
| Security vulnerabilities | Private security advisory |

### 15.1 Response times

This project is maintained by a small team. Response times are best-effort:

| Type | Expected response |
|------|-------------------|
| Security vulnerabilities | Within 7 days |
| Bug reports | Within 14 days |
| Feature requests | Within 30 days |
| PRs | Within 14 days |
| Discussions | Best-effort |

If a PR or issue has not received a response within the expected window,
a polite bump is welcome.

### 15.2 What to include in a question

Questions that are likely to get a good answer include:

- What you are trying to accomplish
- What you have tried
- What happened
- What you expected

Questions that are unlikely to get an answer:

- "Why doesn't this work?"
- "Fix this"
- Screenshots without text or code
- Questions answered in the docs

Before asking, search:

- The existing issues
- The `docs/` folder
- The wrapper README for your language

### 15.3 What you will not get

The maintainers do not provide:

- Free financial advice
- Free consulting on your trading strategy
- Guarantees about data accuracy for any specific use case
- Support for outdated versions (only the latest release is supported)

---

## See also

- [`docs/contributing.md`](./docs/contributing.md) — documentation contributions
- [`docs/action_types.md`](./docs/action_types.md) — action type semantics
- [`docs/validation_layers.md`](./docs/validation_layers.md) — the seven validation layers
- [`docs/data_sources.md`](./docs/data_sources.md) — data sources and licensing
- [`docs/roadmap.md`](./docs/roadmap.md) — planned versions
- [`.github/PULL_REQUEST_TEMPLATE.md`](./.github/PULL_REQUEST_TEMPLATE.md) — PR checklist
- [`.github/ISSUE_TEMPLATE/`](./.github/ISSUE_TEMPLATE/) — issue templates
- [`LICENSE`](./LICENSE) — Apache 2.0
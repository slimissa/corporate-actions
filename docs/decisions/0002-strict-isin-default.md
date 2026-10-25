# ADR 0002 — `--strict-isin` default and CI waiver

**Status**: Accepted 2026-10-24

## Context

`tools/validate.py` currently emits "unknown ISIN" as a warning for every
ISIN in `actions.json` not present in the fixture (`tests/fixtures/identifiers.json`).
As of v1.3.0 expansion this is 26 warnings per run.

The warning exists because:
- The fixture is synthetic (10 test ISINs) by design
- `actions.json` uses real ISINs (26 real ISINs)
- Any production deployment with a real registry is fully consistent
- Any CI test using the fixture will always disagree with real data

## Decision

Add a distinct flag from `--strict-isin`:

- `--strict-isin` (default on): unknown ISINs error
- `--no-strict-isin`: unknown ISINs warn

CI passes `--no-strict-isin` when running against the fixture. Production
deployments run with the default and therefore error on any unknown ISIN.

## Consequences

- CI's fixture-based tests continue to pass without fixture expansion
- Production deployments get the strict enforcement they need
- The flag distinction is explicit and cannot be forgotten: `--no-strict-isin`
  must be passed to every fixture-based validation, so it appears in every
  CI workflow step
- The fixture stays small and hand-maintainable

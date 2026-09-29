# Exit Codes

Every tool in this repository uses the same four exit codes.

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Data error — malformed input, validation failure, drift |
| 2 | Usage error — bad flag, missing argument |
| 3 | External failure — file not found, network, sibling registry |

## Per-tool notes

| Tool | Exit 2 | Exit 3 |
|------|--------|--------|
| `tools/validate.py` | usage error | actions, schema, or sibling registry missing |
| `tools/build.py` | usage error | actions or schema missing |
| `tools/derive_impacts.py` | usage error | actions missing |
| `tools/merge_fetched.py` | usage error | actions or fetched missing |
| `tools/fetch_yahoo_actions.py` | usage error | identifiers missing |
| `tools/fetch_sec_edgar_actions.py` | usage error | identifiers missing |
| `scripts/notify_on_change.py` | usage error | actions missing |

Scripts that branch on `$?` can assume:
- `0` → success
- `1` → the data is wrong
- `2` → the invocation is wrong
- `3` → the environment is wrong
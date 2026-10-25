"""Tools package.

Inserts the repository root on `sys.path` so that running any tool as
`python3 tools/X.py` can correctly `from tools.Y import ...`. Without
this, Python puts `tools/` on sys.path[0] and the import looks for
`tools/tools/Y.py`.

This class of bug bit twice before (fetch_yahoo_actions.py, then
fetch_sec_edgar_actions.py) — both times fixed by adding a per-file
sys.path.insert. Doing it once, at package level, fixes it for every
future tool.
"""
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

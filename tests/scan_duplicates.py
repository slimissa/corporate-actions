#!/usr/bin/env python3
"""Report suspected semantic duplicates in actions.json.

Groups by (isin, family) where family collapses DIVIDEND+SPECIAL_DIVIDEND
and SPLIT+REVERSE_SPLIT. Flags pairs whose ex_dates are within
WINDOW_DAYS and whose amounts match (or differ by a small constant,
indicating a bundled regular+special entry).
"""
import json
import sys
from collections import defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path

WINDOW_DAYS = 10
BUNDLE_DELTA = 0.08  # regular dividend amount that Yahoo bundles with special

REPO_ROOT = Path(__file__).resolve().parents[1]
doc = json.loads((REPO_ROOT / "actions.json").read_text(encoding="utf-8"))


def family(t):
    if t in ("DIVIDEND", "SPECIAL_DIVIDEND"):
        return "DIVIDEND"
    if t in ("SPLIT", "REVERSE_SPLIT"):
        return "SPLIT"
    return t


def amount_of(a):
    return round(a.get("amount") or 0, 4)


def ex_of(a):
    return (a.get("dates") or {}).get("ex_date") or ""


def to_d(s):
    try:
        y, m, d = map(int, s.split("-"))
        return date(y, m, d)
    except Exception:
        return None


by_key = defaultdict(list)
for a in doc["actions"]:
    by_key[(a["isin"], family(a["action_type"]))].append(a)

suspected = []
for key, group in by_key.items():
    for a, b in combinations(group, 2):
        da, db = to_d(ex_of(a)), to_d(ex_of(b))
        if not (da and db):
            continue
        delta = abs((da - db).days)
        if delta > WINDOW_DAYS:
            continue
        amt_a, amt_b = amount_of(a), amount_of(b)
        if abs(amt_a - amt_b) < 0.01:
            suspected.append((key, "same_amount", a["action_id"], b["action_id"]))
        elif abs(amt_a - (amt_b + BUNDLE_DELTA)) < 0.02:
            suspected.append((key, "bundled", a["action_id"], b["action_id"]))
        elif abs(amt_b - (amt_a + BUNDLE_DELTA)) < 0.02:
            suspected.append((key, "bundled", a["action_id"], b["action_id"]))

for s in suspected:
    print(s)
print(f"\n{len(suspected)} suspected duplicate pair(s)")
sys.exit(1 if suspected else 0)
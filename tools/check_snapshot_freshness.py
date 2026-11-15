#!/usr/bin/env python3
import json, sys, datetime
from pathlib import Path

SIBLINGS = Path(__file__).parent / "sibling_versions.json"

def main():
    if not SIBLINGS.exists():
        print(f"Error: {SIBLINGS} not found", file=sys.stderr)
        return 2
    data = json.loads(SIBLINGS.read_text())
    today = datetime.date.today()
    failed = False
    
    for name, info in data.items():
        if not isinstance(info, dict) or "review_by" not in info:
            continue
        review_by = datetime.date.fromisoformat(info["review_by"])
        if review_by < today:
            print(f"FAIL: {name} snapshot is past review_by ({review_by})", file=sys.stderr)
            failed = True
        else:
            print(f"OK: {name} snapshot is current (review_by {review_by})")
            
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Corporate Actions Registry – Change Notification Script

This script monitors the Corporate Actions Registry (actions.json) and
notifies when the file has changed since the last run. It is designed to
be used in cron jobs, CI pipelines, or as a standalone tool.

The script works by:
  1. Computing the SHA‑256 hash of the actions.json file.
  2. Comparing the hash with the hash stored in a state file
     (default: .notify_state.json).
  3. If the hash differs (or no state exists), it prints a change
     notification and optionally POSTs a JSON payload to a webhook URL.
  4. Updating the state file with the new hash.

Usage:
    python scripts/notify_on_change.py --actions actions.json
    python scripts/notify_on_change.py --actions actions.json --webhook-url https://example.com/hook
    python scripts/notify_on_change.py --actions actions.json --state .state --verbose

Exit codes:
  0 – success (either no change or notification sent)
  1 – error (missing file, invalid arguments, webhook failure)
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# Default paths
DEFAULT_ACTIONS_PATH = "actions.json"
DEFAULT_STATE_PATH = ".notify_state.json"


def compute_sha256(file_path: str) -> str:
    """
    Compute the SHA‑256 hash of a file.

    Args:
        file_path: Path to the file.

    Returns:
        Hex digest string.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    with open(file_path, "rb") as f:
        digest = hashlib.sha256()
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_state(state_path: str) -> Dict[str, Any]:
    """
    Load the state file containing the last known hash.

    Args:
        state_path: Path to the state file.

    Returns:
        Dictionary with at least "hash" key. Returns empty dict if file
        does not exist or is invalid.
    """
    if not os.path.exists(state_path):
        return {}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state_path: str, new_hash: str) -> None:
    """
    Save the new hash to the state file.

    Args:
        state_path: Path to the state file.
        new_hash: Hex digest of the current actions.json.
    """
    state = {
        "hash": new_hash,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def send_webhook_notification(
    webhook_url: str,
    old_hash: Optional[str],
    new_hash: str,
    actions_path: str,
) -> bool:
    """
    Send a JSON POST request to a webhook URL with change details.

    Args:
        webhook_url: The webhook endpoint.
        old_hash: Previous hash (or None if first run).
        new_hash: New hash.
        actions_path: Path to the actions file.

    Returns:
        True if the request succeeded, False otherwise.
    """
    payload = {
        "event": "corporate_actions_changed",
        "actions_path": actions_path,
        "old_hash": old_hash,
        "new_hash": new_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        # Use urllib to avoid external dependencies
        import urllib.request
        import urllib.error

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status < 400
    except Exception as e:
        print(f"Webhook delivery failed: {e}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Notify when the Corporate Actions Registry changes."
    )
    parser.add_argument(
        "--actions",
        default=DEFAULT_ACTIONS_PATH,
        help=f"Path to actions.json (default: {DEFAULT_ACTIONS_PATH})",
    )
    parser.add_argument(
        "--state",
        default=DEFAULT_STATE_PATH,
        help=f"Path to state file (default: {DEFAULT_STATE_PATH})",
    )
    parser.add_argument(
        "--webhook-url",
        default=None,
        help="Optional webhook URL to POST a change notification.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed information about the process.",
    )
    args = parser.parse_args()

    # Validate actions file exists
    if not os.path.isfile(args.actions):
        print(f"Error: actions file not found: {args.actions}", file=sys.stderr)
        sys.exit(1)

    # Compute current hash
    try:
        new_hash = compute_sha256(args.actions)
    except OSError as e:
        print(f"Error reading actions file: {e}", file=sys.stderr)
        sys.exit(1)

    # Load previous hash from state
    old_state = load_state(args.state)
    old_hash = old_state.get("hash")

    if args.verbose:
        print(f"Actions path: {args.actions}")
        print(f"State path:   {args.state}")
        print(f"Old hash:     {old_hash if old_hash else 'None (first run)'}")
        print(f"New hash:     {new_hash}")

    # Determine if changed
    changed = old_hash is None or old_hash != new_hash

    if not changed:
        if args.verbose:
            print("No change detected.")
        sys.exit(0)

    # Print notification
    if old_hash is None:
        print(
            f"[{datetime.now(timezone.utc).isoformat()}] First run detected. "
            f"Recording hash for {args.actions}."
        )
    else:
        print(
            f"[{datetime.now(timezone.utc).isoformat()}] Change detected in {args.actions}:\n"
            f"  old hash: {old_hash}\n"
            f"  new hash: {new_hash}"
        )

    # Send webhook if provided
    if args.webhook_url:
        if args.verbose:
            print(f"Sending webhook notification to {args.webhook_url}...")
        success = send_webhook_notification(
            args.webhook_url, old_hash, new_hash, args.actions
        )
        if not success:
            # Do not exit with failure; webhook is optional. Print warning.
            print("Warning: webhook notification failed.", file=sys.stderr)

    # Update state file
    try:
        save_state(args.state, new_hash)
        if args.verbose:
            print(f"State file updated: {args.state}")
    except OSError as e:
        print(f"Error writing state file: {e}", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
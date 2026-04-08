#!/usr/bin/env python3
"""
Application Status Updater — CLI tool to manually update application statuses.

Usage:
  python update_status.py <app_id> <new_status> [note]

Statuses: submitted, accepted, rejected, withdrawn

This is the human-in-the-loop component: after the system generates drafts,
the speaker submits applications manually, then uses this script to track outcomes.

Can also be triggered via GitHub Actions workflow_dispatch for remote updates.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
APPS_FILE = DATA_DIR / "applications.json"

VALID_STATUSES = {"submitted", "accepted", "rejected", "withdrawn", "draft"}


def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def update_metadata(apps_data):
    """Recalculate metadata from application list."""
    apps = apps_data.get("applications", [])
    status_counts = {}
    for app in apps:
        s = app["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    total = len(apps)
    accepted = status_counts.get("accepted", 0)
    rejected = status_counts.get("rejected", 0)
    submitted = status_counts.get("submitted", 0) + accepted + rejected
    acceptance_rate = round(accepted / submitted * 100, 1) if submitted > 0 else 0.0

    apps_data["metadata"] = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_applications": total,
        "total_accepted": accepted,
        "total_rejected": rejected,
        "total_pending": status_counts.get("submitted", 0),
        "total_drafts": status_counts.get("draft", 0),
        "total_expired": status_counts.get("expired", 0),
        "total_withdrawn": status_counts.get("withdrawn", 0),
        "acceptance_rate": acceptance_rate,
        "status_breakdown": status_counts
    }


def list_applications(apps_data):
    """Print all applications with their IDs and statuses."""
    apps = apps_data.get("applications", [])
    if not apps:
        print("No applications found.")
        return

    print(f"\n{'ID':<18} {'Status':<12} {'Score':<7} {'CFP Title':<40} {'Talk'}")
    print("-" * 120)
    for app in apps:
        score = app.get("match_scores", {}).get("composite_score", 0)
        print(f"{app['id']:<18} {app['status']:<12} {score:<7.2f} {app.get('cfp_title', '')[:38]:<40} {app.get('talk_title', '')[:30]}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python update_status.py list                    — List all applications")
        print("  python update_status.py <app_id> <status> [note] — Update application status")
        print(f"  Valid statuses: {', '.join(sorted(VALID_STATUSES))}")
        sys.exit(0)

    apps_data = load_json(APPS_FILE)

    if sys.argv[1] == "list":
        list_applications(apps_data)
        sys.exit(0)

    if len(sys.argv) < 3:
        print("Error: Both app_id and status are required")
        sys.exit(1)

    app_id = sys.argv[1]
    new_status = sys.argv[2].lower()
    note = sys.argv[3] if len(sys.argv) > 3 else ""

    if new_status not in VALID_STATUSES:
        print(f"Error: Invalid status '{new_status}'. Valid: {', '.join(sorted(VALID_STATUSES))}")
        sys.exit(1)

    # Find application
    app = None
    for a in apps_data.get("applications", []):
        if a["id"] == app_id or a["id"].startswith(app_id):
            app = a
            break

    if not app:
        print(f"Error: Application '{app_id}' not found")
        list_applications(apps_data)
        sys.exit(1)

    old_status = app["status"]
    app["status"] = new_status
    app["updated_at"] = datetime.now(timezone.utc).isoformat()
    app["status_history"].append({
        "status": new_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": note or f"Status changed from {old_status} to {new_status}"
    })

    if new_status == "submitted":
        app["submitted_at"] = datetime.now(timezone.utc).isoformat()
    elif new_status in ("accepted", "rejected"):
        app["response_at"] = datetime.now(timezone.utc).isoformat()

    update_metadata(apps_data)
    save_json(APPS_FILE, apps_data)

    print(f"Updated: {app['cfp_title']}")
    print(f"  {old_status} -> {new_status}")
    print(f"  Acceptance rate: {apps_data['metadata']['acceptance_rate']}%")


if __name__ == "__main__":
    main()

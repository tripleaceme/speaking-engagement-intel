#!/usr/bin/env python3
"""
Application Generator — Generates draft speaking engagement applications
for high-scoring CFPs and tracks submission status.

For each qualifying CFP, it:
  1. Selects the best matching talk from the speaker's repertoire
  2. Generates a tailored abstract/proposal
  3. Creates an application entry with status tracking
  4. Updates the applications.json database

Application statuses:
  - draft: Generated but not submitted
  - submitted: Manually submitted by the speaker
  - accepted: Speaker was accepted
  - rejected: Application was rejected
  - withdrawn: Speaker withdrew
  - expired: CFP deadline passed without submission
"""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CFPS_FILE = DATA_DIR / "cfps.json"
PROFILE_FILE = DATA_DIR / "profile.json"
APPS_FILE = DATA_DIR / "applications.json"


def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def generate_app_id(cfp_id, talk_title):
    raw = f"app|{cfp_id}|{talk_title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def tailor_abstract(talk, cfp):
    """
    Generate a tailored abstract based on the talk template and CFP context.
    In production, this could use an LLM API for better personalization.
    """
    abstract = talk.get("abstract", "")

    # Add a contextual opener based on CFP source/topic
    cfp_tags = set(t.lower() for t in cfp.get("tags", []))
    talk_tags = set(t.lower() for t in talk.get("tags", []))
    shared_tags = cfp_tags & talk_tags

    if shared_tags:
        context_note = f"[Tailored for {cfp['title']} — aligned topics: {', '.join(shared_tags)}]"
    else:
        context_note = f"[Tailored for {cfp['title']}]"

    return f"{context_note}\n\n{abstract}"


def generate_proposal(cfp, talk, profile):
    """Generate a complete proposal/application draft."""
    speaker = profile.get("speaker", {})
    bio = profile.get("bio", {})

    proposal = {
        "talk_title": talk.get("title", ""),
        "abstract": tailor_abstract(talk, cfp),
        "speaker_name": speaker.get("name", ""),
        "speaker_bio": bio.get("short", ""),
        "speaker_email": speaker.get("email", ""),
        "speaker_website": speaker.get("website", ""),
        "speaker_github": speaker.get("github", ""),
        "talk_level": talk.get("level", "intermediate"),
        "talk_duration": talk.get("duration_minutes", [30])[0],
        "tags": talk.get("tags", []),
        "outline": [
            "Introduction & Problem Statement",
            "Background & Context",
            "Core Concepts & Demo",
            "Practical Application",
            "Key Takeaways & Q&A"
        ],
        "target_audience": f"Developers and engineers interested in {', '.join(talk.get('tags', ['technology'])[:3])}",
        "prerequisites": "Basic familiarity with the topic area" if talk.get("level") != "beginner" else "None — suitable for all levels",
        "additional_notes": f"I am an open-source contributor (dbt-doc-tracker) and actively building tools in this space. Happy to adapt the talk format or duration as needed."
    }

    return proposal


def main():
    print("=" * 60)
    print("Speaking Engagement Intel - Application Generator")
    print(f"Run time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    profile = load_json(PROFILE_FILE)
    cfps_data = load_json(CFPS_FILE)
    apps_data = load_json(APPS_FILE)

    cfps = cfps_data.get("cfps", [])
    existing_apps = {a["id"]: a for a in apps_data.get("applications", [])}
    talks = profile.get("talk_topics", [])
    min_score = profile.get("matching_preferences", {}).get("min_relevance_score", 0.4)

    # Filter to open CFPs above threshold that don't already have applications
    qualifying = [
        c for c in cfps
        if c.get("status") == "open"
        and c.get("match_scores")
        and c["match_scores"]["composite_score"] >= min_score
    ]

    print(f"\nQualifying CFPs (score >= {min_score}): {len(qualifying)}")

    new_apps = 0
    updated_apps = 0

    for cfp in qualifying:
        scores = cfp["match_scores"]
        suggested_talk_title = scores.get("suggested_talk")

        if not suggested_talk_title:
            continue

        # Find the actual talk object
        talk = next((t for t in talks if t["title"] == suggested_talk_title), None)
        if not talk:
            continue

        app_id = generate_app_id(cfp["id"], suggested_talk_title)

        if app_id in existing_apps:
            # Update scores but don't overwrite status
            existing_apps[app_id]["match_scores"] = scores
            existing_apps[app_id]["cfp_deadline"] = cfp.get("deadline", "")
            updated_apps += 1
            continue

        # Generate new application
        proposal = generate_proposal(cfp, talk, profile)

        app = {
            "id": app_id,
            "cfp_id": cfp["id"],
            "cfp_title": cfp["title"],
            "cfp_url": cfp.get("cfp_url") or cfp.get("url", ""),
            "cfp_source": cfp["source"],
            "cfp_deadline": cfp.get("deadline", ""),
            "event_date": cfp.get("event_date", ""),
            "event_location": cfp.get("location", ""),
            "is_online": cfp.get("is_online", False),
            "talk_title": suggested_talk_title,
            "proposal": proposal,
            "match_scores": scores,
            "status": "draft",
            "status_history": [
                {
                    "status": "draft",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "note": "Auto-generated by Speaking Engagement Intel"
                }
            ],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "submitted_at": None,
            "response_at": None,
            "notes": ""
        }

        existing_apps[app_id] = app
        new_apps += 1

    # Check for expired applications
    expired = 0
    for app in existing_apps.values():
        if app["status"] == "draft" and app.get("cfp_deadline"):
            try:
                deadline = datetime.strptime(app["cfp_deadline"][:10], "%Y-%m-%d")
                if deadline.date() < datetime.now().date():
                    app["status"] = "expired"
                    app["status_history"].append({
                        "status": "expired",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "note": "CFP deadline passed without submission"
                    })
                    app["updated_at"] = datetime.now(timezone.utc).isoformat()
                    expired += 1
            except ValueError:
                pass

    # Compile stats
    all_apps = list(existing_apps.values())
    status_counts = {}
    for app in all_apps:
        s = app["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    total = len(all_apps)
    accepted = status_counts.get("accepted", 0)
    rejected = status_counts.get("rejected", 0)
    submitted = status_counts.get("submitted", 0) + accepted + rejected
    acceptance_rate = round(accepted / submitted * 100, 1) if submitted > 0 else 0.0

    # Save
    output = {
        "metadata": {
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
        },
        "applications": sorted(all_apps, key=lambda a: a.get("match_scores", {}).get("composite_score", 0), reverse=True)
    }

    save_json(APPS_FILE, output)

    print(f"\nResults:")
    print(f"  New applications generated: {new_apps}")
    print(f"  Existing apps updated:      {updated_apps}")
    print(f"  Applications expired:        {expired}")
    print(f"  Total applications:          {total}")
    print(f"  Acceptance rate:             {acceptance_rate}%")
    print(f"\nStatus breakdown:")
    for status, count in sorted(status_counts.items()):
        print(f"    {status}: {count}")

    print(f"\nSaved to {APPS_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()

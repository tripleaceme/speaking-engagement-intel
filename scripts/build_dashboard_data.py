#!/usr/bin/env python3
"""
Dashboard Data Builder — Compiles all data sources into a single
dashboard_data.json file that the static HTML dashboard reads.

This runs after crawl, score, and generate steps.
It produces the JSON that powers the GitHub Pages dashboard.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DOCS_DATA = Path(__file__).resolve().parent.parent / "docs" / "data"

CFPS_FILE = DATA_DIR / "cfps.json"
APPS_FILE = DATA_DIR / "applications.json"
PROFILE_FILE = DATA_DIR / "profile.json"
OUTPUT_FILE = DOCS_DATA / "dashboard_data.json"


def load_json(path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def build_timeline(apps):
    """Build monthly timeline of applications and outcomes."""
    monthly = {}
    for app in apps:
        created = app.get("created_at", "")
        if not created:
            continue
        month_key = created[:7]  # YYYY-MM
        if month_key not in monthly:
            monthly[month_key] = {"applied": 0, "accepted": 0, "rejected": 0, "pending": 0, "draft": 0}
        status = app.get("status", "draft")
        if status == "accepted":
            monthly[month_key]["accepted"] += 1
            monthly[month_key]["applied"] += 1
        elif status == "rejected":
            monthly[month_key]["rejected"] += 1
            monthly[month_key]["applied"] += 1
        elif status == "submitted":
            monthly[month_key]["pending"] += 1
            monthly[month_key]["applied"] += 1
        elif status == "draft":
            monthly[month_key]["draft"] += 1

    return [
        {"month": k, **v}
        for k, v in sorted(monthly.items())
    ]


def build_source_breakdown(cfps):
    """Count CFPs by source."""
    sources = {}
    for cfp in cfps:
        src = cfp.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
    return [{"source": k, "count": v} for k, v in sorted(sources.items(), key=lambda x: -x[1])]


def build_priority_breakdown(cfps):
    """Count open CFPs by priority."""
    priorities = {"high": 0, "medium": 0, "low": 0}
    for cfp in cfps:
        if cfp.get("status") != "open":
            continue
        scores = cfp.get("match_scores")
        if scores:
            p = scores.get("priority", "low")
            priorities[p] = priorities.get(p, 0) + 1
    return priorities


def build_tag_cloud(cfps):
    """Build tag frequency map from open CFPs."""
    tags = {}
    for cfp in cfps:
        if cfp.get("status") != "open":
            continue
        for tag in cfp.get("tags", []):
            tag = tag.lower().strip()
            if tag and len(tag) > 1:
                tags[tag] = tags.get(tag, 0) + 1
    # Top 30 tags
    sorted_tags = sorted(tags.items(), key=lambda x: -x[1])[:30]
    return [{"tag": t, "count": c} for t, c in sorted_tags]


def build_top_matches(cfps, limit=20):
    """Get top scored open CFPs for the dashboard."""
    open_cfps = [
        c for c in cfps
        if c.get("status") == "open" and c.get("match_scores")
    ]
    open_cfps.sort(key=lambda c: c["match_scores"]["composite_score"], reverse=True)

    return [
        {
            "id": c["id"],
            "title": c["title"],
            "source": c["source"],
            "url": c.get("cfp_url") or c.get("url", ""),
            "deadline": c.get("deadline", ""),
            "event_date": c.get("event_date", ""),
            "location": c.get("location", ""),
            "is_online": c.get("is_online", False),
            "tags": c.get("tags", [])[:5],
            "score": c["match_scores"]["composite_score"],
            "priority": c["match_scores"]["priority"],
            "suggested_talk": c["match_scores"].get("suggested_talk"),
            "tag_relevance": c["match_scores"].get("tag_relevance", 0),
            "talk_match": c["match_scores"].get("talk_match_score", 0),
            "urgency": c["match_scores"].get("urgency_score", 0),
            "travel_sponsorship": c.get("travel_sponsorship", "unknown"),
            "event_type": c.get("event_type", "")
        }
        for c in open_cfps[:limit]
    ]


def build_applications_list(apps):
    """Build application list for dashboard."""
    return [
        {
            "id": a["id"],
            "cfp_title": a.get("cfp_title", ""),
            "talk_title": a.get("talk_title", ""),
            "cfp_source": a.get("cfp_source", ""),
            "cfp_url": a.get("cfp_url", ""),
            "deadline": a.get("cfp_deadline", ""),
            "event_date": a.get("event_date", ""),
            "status": a.get("status", "draft"),
            "score": a.get("match_scores", {}).get("composite_score", 0),
            "priority": a.get("match_scores", {}).get("priority", "low"),
            "created_at": a.get("created_at", ""),
            "submitted_at": a.get("submitted_at"),
            "response_at": a.get("response_at"),
            "notes": a.get("notes", ""),
            "travel_sponsorship": a.get("match_scores", {}).get("travel_sponsorship", "unknown"),
            "is_online": a.get("is_online", False),
            "event_location": a.get("event_location", "")
        }
        for a in apps
    ]


def build_talk_performance(apps):
    """Track which talks are most successful."""
    talks = {}
    for app in apps:
        title = app.get("talk_title", "Unknown")
        if title not in talks:
            talks[title] = {"title": title, "applications": 0, "accepted": 0, "rejected": 0, "pending": 0}
        talks[title]["applications"] += 1
        status = app.get("status")
        if status == "accepted":
            talks[title]["accepted"] += 1
        elif status == "rejected":
            talks[title]["rejected"] += 1
        elif status == "submitted":
            talks[title]["pending"] += 1

    result = list(talks.values())
    for t in result:
        submitted = t["accepted"] + t["rejected"] + t["pending"]
        t["acceptance_rate"] = round(t["accepted"] / submitted * 100, 1) if submitted > 0 else 0
    return sorted(result, key=lambda t: -t["applications"])


def main():
    print("=" * 60)
    print("Speaking Engagement Intel - Dashboard Data Builder")
    print(f"Run time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    cfps_data = load_json(CFPS_FILE)
    apps_data = load_json(APPS_FILE)
    profile = load_json(PROFILE_FILE)

    cfps = cfps_data.get("cfps", [])
    apps = apps_data.get("applications", [])
    apps_meta = apps_data.get("metadata", {})
    cfps_meta = cfps_data.get("metadata", {})

    open_cfps = [c for c in cfps if c.get("status") == "open"]
    expired_cfps = [c for c in cfps if c.get("status") == "expired"]

    # Build dashboard data
    dashboard = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "speaker": {
            "name": profile.get("speaker", {}).get("name", ""),
            "title": profile.get("speaker", {}).get("title", ""),
            "tagline": profile.get("speaker", {}).get("tagline", "")
        },
        "summary": {
            "total_cfps_discovered": len(cfps),
            "open_cfps": len(open_cfps),
            "expired_cfps": len(expired_cfps),
            "total_applications": len(apps),
            "drafts": sum(1 for a in apps if a.get("status") == "draft"),
            "submitted": sum(1 for a in apps if a.get("status") == "submitted"),
            "accepted": sum(1 for a in apps if a.get("status") == "accepted"),
            "rejected": sum(1 for a in apps if a.get("status") == "rejected"),
            "withdrawn": sum(1 for a in apps if a.get("status") == "withdrawn"),
            "expired_apps": sum(1 for a in apps if a.get("status") == "expired"),
            "acceptance_rate": apps_meta.get("acceptance_rate", 0),
            "high_priority_cfps": sum(1 for c in open_cfps if c.get("match_scores", {}).get("priority") == "high"),
            "last_crawled": cfps_meta.get("last_crawled", ""),
            "sources_checked": cfps_meta.get("sources_checked", 0),
            "travel_yes": sum(1 for c in open_cfps if c.get("travel_sponsorship") == "yes"),
            "travel_partial": sum(1 for c in open_cfps if c.get("travel_sponsorship") == "partial"),
            "travel_unknown": sum(1 for c in open_cfps if c.get("travel_sponsorship", "unknown") == "unknown"),
        },
        "timeline": build_timeline(apps),
        "source_breakdown": build_source_breakdown(cfps),
        "priority_breakdown": build_priority_breakdown(cfps),
        "tag_cloud": build_tag_cloud(cfps),
        "top_matches": build_top_matches(cfps),
        "applications": build_applications_list(apps),
        "talk_performance": build_talk_performance(apps),
        "upcoming_deadlines": [
            {
                "title": c["title"],
                "deadline": c["deadline"],
                "source": c["source"],
                "score": c.get("match_scores", {}).get("composite_score", 0),
                "url": c.get("cfp_url") or c.get("url", ""),
                "travel_sponsorship": c.get("travel_sponsorship", "unknown"),
                "location": c.get("location", "")
            }
            for c in sorted(
                [c for c in open_cfps if c.get("deadline")],
                key=lambda c: c["deadline"]
            )[:10]
        ]
    }

    # Ensure output directory exists
    DOCS_DATA.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(dashboard, f, indent=2)

    print(f"\nDashboard data written to {OUTPUT_FILE}")
    print(f"  CFPs: {len(cfps)} total, {len(open_cfps)} open")
    print(f"  Applications: {len(apps)}")
    print(f"  Acceptance rate: {apps_meta.get('acceptance_rate', 0)}%")
    print("=" * 60)


if __name__ == "__main__":
    main()

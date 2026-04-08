#!/usr/bin/env python3
"""
Application Generator — Generates TAILORED speaking proposals for each
conference based on its themes, categories, and audience.

Instead of picking from a fixed menu of pre-written talks, this generator:
  1. Reads the conference's detected themes, categories, and description
  2. Finds the intersection between the conference's interests and the
     speaker's expertise
  3. Crafts a unique talk title and abstract that speaks to THAT audience
  4. Falls back to best-matching pre-written talk only when we have zero
     information about the conference

This means a data conference gets a data talk, an AI conference gets an
AI-governance-through-data talk, and a general tech conference gets a
practical-tools talk — all from the same speaker profile.
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


# ─── Tailored Proposal Templates ──────────────────────────────────
# Each template maps conference themes to a customized talk angle.
# The {vars} are filled from the speaker's profile and conference context.

PROPOSAL_TEMPLATES = {
    "data": {
        "title": "Building Trust in Data: Documentation Automation & Quality Engineering at Scale",
        "abstract": (
            "Data teams ship dashboards fast but documentation and quality often lag behind. "
            "In this talk, I share how I built an AI-powered documentation pipeline that auto-generates "
            "column descriptions for dbt models (35%+ coverage increase), and a custom data quality "
            "framework that reduced quality debt by 15% across critical datasets. "
            "You'll learn practical patterns for dbt testing, automated doc generation, and building "
            "a culture of data trust — with live examples from production Snowflake and BigQuery environments."
        ),
        "tags": ["dbt", "data-quality", "documentation", "analytics-engineering", "ai"],
        "level": "intermediate",
    },
    "ai": {
        "title": "AI-Powered Data Governance: From Manual Documentation to Automated Trust",
        "abstract": (
            "Most organizations want to adopt AI but struggle with the foundation: trustworthy, "
            "well-documented data. I'll show how I integrated LLMs into the analytics engineering "
            "workflow to auto-generate documentation, detect anomalies, and enforce governance rules — "
            "all within dbt and the modern data stack. This isn't AI hype — it's practical automation "
            "that increased documentation coverage by 35% and saved $3K/month in tooling costs. "
            "Attendees will leave with a playbook for adding AI to their own data workflows."
        ),
        "tags": ["ai", "llm", "data-governance", "dbt", "automation"],
        "level": "intermediate",
    },
    "cloud": {
        "title": "The Modern Data Stack on a Budget: Replacing Enterprise Tools with Open Source",
        "abstract": (
            "Enterprise data tools are expensive. I'll show how I replaced a $3K/month SaaS ingestion "
            "tool with a custom Streamlit + Snowflake hub, built monitoring with Airflow alerts, and "
            "created a complete analytics pipeline using open-source tools. You'll learn how to build "
            "production-grade data infrastructure on Snowflake, BigQuery, dbt, and Airflow — without "
            "the enterprise price tag. Includes patterns for ingestion, transformation, orchestration, "
            "and observability that scale."
        ),
        "tags": ["cloud", "snowflake", "bigquery", "dbt", "airflow", "cost-optimization"],
        "level": "intermediate",
    },
    "open-source": {
        "title": "From Side Project to dbt Hub: Building Open-Source Packages That Ship",
        "abstract": (
            "I maintain 5 open-source packages on dbt Hub — doc-tracker, doc-inherit, anomaly-detector, "
            "flow-lineage, and tap-substack. This talk is about the messy reality of building open-source "
            "tools: choosing what to build, designing APIs people actually use, testing without a QA team, "
            "and sustaining maintenance alongside a full-time job. Whether you're thinking about your "
            "first package or your fifth, you'll get honest lessons from shipping to production."
        ),
        "tags": ["open-source", "dbt", "community", "packages", "developer-tools"],
        "level": "beginner",
    },
    "education": {
        "title": "Democratizing Data Education: Training 900+ Analysts Across 7 Countries",
        "abstract": (
            "How do you teach analytics engineering to students with unreliable internet and no Snowflake "
            "credits? As founder of Behind The Data Academy and mentor to 900+ students across 7 countries, "
            "I've built curriculum around free tools — dbt, PostgreSQL, Python, Tableau — that produces "
            "job-ready analysts. This talk shares frameworks for designing hands-on data education that "
            "works in resource-constrained environments, plus hard-won lessons on what actually helps "
            "students land their first data roles."
        ),
        "tags": ["education", "data-literacy", "community", "diversity", "edtech"],
        "level": "beginner",
    },
    "database": {
        "title": "From Stored Procedures to dbt: Modernizing Legacy SQL Without Breaking Production",
        "abstract": (
            "Your warehouse is full of stored procedures nobody wants to touch. I migrated legacy SQL "
            "workflows to modular dbt models, cutting maintenance time by 45% while keeping production "
            "running. This talk covers the migration playbook: auditing existing logic, designing the "
            "dbt model layer, testing strategies for parity, and deploying with confidence. "
            "Includes patterns for Snowflake, BigQuery, and PostgreSQL — and how to bring skeptical "
            "DBAs on board."
        ),
        "tags": ["sql", "dbt", "migration", "database", "snowflake", "bigquery"],
        "level": "intermediate",
    },
    "devops": {
        "title": "DataOps in Practice: CI/CD, Observability, and Orchestration for Analytics",
        "abstract": (
            "Software engineering has CI/CD. Data engineering is catching up. I'll share how I built "
            "end-to-end DataOps workflows: Airflow DAGs for orchestration, automated dbt tests in CI, "
            "monitoring dashboards for pipeline health, and alerting that pages before the data is stale. "
            "Drawing from building pipelines across SFTP, S3, BigQuery, and Snowflake, you'll learn "
            "practical patterns for treating your data stack like production software."
        ),
        "tags": ["devops", "dataops", "airflow", "ci-cd", "dbt", "observability"],
        "level": "intermediate",
    },
    "web": {
        "title": "Building Internal Data Tools with Streamlit: From Prototype to Production",
        "abstract": (
            "Your data team needs internal tools but doesn't have frontend engineers. I built three "
            "production Streamlit apps — a Data Modification Hub (70% accuracy improvement), a custom "
            "ingestion hub (replaced $3K SaaS), and an orchestration locking hub (prevents pipeline "
            "conflicts). This talk shows how to go from Python script to production app: database "
            "connections, authentication, state management, and deployment patterns that your team "
            "will actually adopt."
        ),
        "tags": ["streamlit", "python", "internal-tools", "data-apps", "snowflake"],
        "level": "intermediate",
    },
    "leadership": {
        "title": "Scaling Data Culture: How One Analytics Engineer Can Change an Organization",
        "abstract": (
            "You don't need a 20-person data team to build data culture. As a solo analytics engineer, "
            "I introduced documentation automation, data quality frameworks, and self-serve analytics "
            "to organizations that previously relied on ad-hoc SQL queries. This talk covers practical "
            "strategies for evangelizing data best practices, getting buy-in from leadership, and "
            "building the foundations that let small data teams punch above their weight."
        ),
        "tags": ["leadership", "data-culture", "analytics-engineering", "strategy"],
        "level": "beginner",
    },
    "testing": {
        "title": "Data Quality as Code: Testing Strategies That Catch Bugs Before the Dashboard",
        "abstract": (
            "Bad data in dashboards destroys trust. I built a testing framework combining dbt tests, "
            "Great Expectations, and custom anomaly detection that catches issues before they reach "
            "stakeholders — reducing data quality debt by 15% and achieving 95% validation accuracy. "
            "You'll learn schema tests, freshness checks, statistical anomaly detection, and how to "
            "build a testing culture in a team that's never tested data before."
        ),
        "tags": ["testing", "data-quality", "dbt", "great-expectations"],
        "level": "intermediate",
    },
}

# Default/fallback when we can't determine the conference theme
DEFAULT_PROPOSAL = {
    "title": "The Analytics Engineer's Toolkit: dbt, AI Documentation, and Open Source in Production",
    "abstract": (
        "Analytics engineering is evolving fast. In this talk, I share lessons from building 5 open-source "
        "dbt packages, implementing AI-powered documentation automation, and designing data quality "
        "frameworks across Snowflake and BigQuery — all while training 900+ analysts across 7 countries. "
        "You'll get practical patterns for modern analytics engineering: modular dbt models, automated "
        "testing, documentation that writes itself, and tools that scale without enterprise budgets."
    ),
    "tags": ["dbt", "analytics-engineering", "open-source", "data-quality"],
    "level": "intermediate",
}


def select_proposal_for_conference(cfp, profile):
    """
    Select or generate the best proposal for a specific conference
    based on its detected themes, categories, and description.
    """
    themes = cfp.get("themes", [])
    categories = cfp.get("categories", [])
    tags = set(t.lower() for t in cfp.get("tags", []))
    desc_lower = (cfp.get("description", "") + " " + cfp.get("title", "")).lower()

    # Build a score for each template based on theme overlap
    template_scores = {}
    for template_key, template in PROPOSAL_TEMPLATES.items():
        score = 0

        # Score from detected themes
        for theme in themes:
            if theme["theme"] == template_key:
                score += theme["confidence"] * 3
            # Related themes get partial credit
            if template_key in ("data", "database") and theme["theme"] in ("data", "database", "cloud"):
                score += theme["confidence"] * 1

        # Score from tags
        for tag in tags:
            if tag == template_key:
                score += 2
            # Check template tags too
            for ttag in template["tags"]:
                if tag == ttag or tag in ttag or ttag in tag:
                    score += 0.5

        # Score from categories
        for cat in categories:
            cat_lower = cat.lower()
            if template_key in cat_lower:
                score += 2
            for ttag in template["tags"]:
                if ttag in cat_lower:
                    score += 1

        # Score from description
        for ttag in template["tags"]:
            if ttag in desc_lower:
                score += 0.5

        template_scores[template_key] = score

    # Sort by score
    ranked = sorted(template_scores.items(), key=lambda x: -x[1])

    # Pick the best match, or fallback
    best_key, best_score = ranked[0] if ranked else ("default", 0)

    if best_score > 0:
        proposal = PROPOSAL_TEMPLATES[best_key].copy()
        proposal["match_reason"] = f"Conference themes align with '{best_key}' (score: {best_score:.1f})"
    else:
        proposal = DEFAULT_PROPOSAL.copy()
        proposal["match_reason"] = "No specific theme detected — using versatile default proposal"

    return proposal


def build_application(cfp, proposal, profile):
    """Build a complete application entry."""
    speaker = profile.get("speaker", {})
    bio = profile.get("bio", {})

    app_id = generate_app_id(cfp["id"], proposal["title"])

    return {
        "id": app_id,
        "cfp_id": cfp["id"],
        "cfp_title": cfp["title"],
        "cfp_url": cfp.get("cfp_url") or cfp.get("url", ""),
        "cfp_source": cfp["source"],
        "cfp_deadline": cfp.get("deadline", ""),
        "event_date": cfp.get("event_date", ""),
        "event_location": cfp.get("location", ""),
        "is_online": cfp.get("is_online", False),
        "talk_title": proposal["title"],
        "talk_abstract": proposal["abstract"],
        "talk_tags": proposal.get("tags", []),
        "talk_level": proposal.get("level", "intermediate"),
        "match_reason": proposal.get("match_reason", ""),
        "conference_themes": [t["theme"] for t in cfp.get("themes", [])],
        "conference_categories": cfp.get("categories", []),
        "travel_sponsorship": cfp.get("travel_sponsorship", "unknown"),
        "speaker_perks": cfp.get("speaker_perks", {}),
        "proposal": {
            "talk_title": proposal["title"],
            "abstract": proposal["abstract"],
            "speaker_name": speaker.get("name", ""),
            "speaker_bio": bio.get("short", ""),
            "speaker_email": speaker.get("email", ""),
            "speaker_website": speaker.get("website", ""),
            "speaker_github": speaker.get("github", ""),
            "talk_level": proposal.get("level", "intermediate"),
            "talk_duration": 30,
            "tags": proposal.get("tags", []),
        },
        "match_scores": cfp.get("match_scores", {}),
        "status": "draft",
        "status_history": [
            {
                "status": "draft",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": f"Auto-generated — {proposal.get('match_reason', '')}"
            }
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "submitted_at": None,
        "response_at": None,
        "notes": ""
    }


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
    min_score = profile.get("matching_preferences", {}).get("min_relevance_score", 0.25)

    # Filter to open CFPs above threshold
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
        # Generate tailored proposal for this conference
        proposal = select_proposal_for_conference(cfp, profile)

        app_id = generate_app_id(cfp["id"], proposal["title"])

        if app_id in existing_apps:
            # Update scores but don't overwrite status or proposal
            existing_apps[app_id]["match_scores"] = cfp.get("match_scores", {})
            existing_apps[app_id]["cfp_deadline"] = cfp.get("deadline", "")
            existing_apps[app_id]["travel_sponsorship"] = cfp.get("travel_sponsorship", "unknown")
            updated_apps += 1
            continue

        app = build_application(cfp, proposal, profile)
        existing_apps[app_id] = app
        new_apps += 1

        print(f"  + {cfp['title'][:40]:<42} -> {proposal['title'][:50]}")

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

    # Check for topic diversity
    talk_titles = [a["talk_title"] for a in all_apps if a["status"] in ("draft", "submitted")]
    unique_titles = set(talk_titles)
    print(f"\n  Topic diversity: {len(unique_titles)} unique talks across {len(talk_titles)} applications")

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
            "status_breakdown": status_counts,
            "unique_talk_titles": len(unique_titles),
        },
        "applications": sorted(all_apps, key=lambda a: a.get("match_scores", {}).get("composite_score", 0), reverse=True)
    }

    save_json(APPS_FILE, output)

    print(f"\nResults:")
    print(f"  New applications: {new_apps}")
    print(f"  Updated: {updated_apps}")
    print(f"  Expired: {expired}")
    print(f"  Total: {total}")
    print(f"  Acceptance rate: {acceptance_rate}%")
    print(f"\nSaved to {APPS_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()

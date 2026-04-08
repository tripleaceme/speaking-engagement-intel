#!/usr/bin/env python3
"""
CFP Matcher & Scorer — Scores each discovered CFP against the speaker's
profile to determine relevance and application priority.

Scoring factors:
  - Tag/keyword overlap with expertise
  - Topic alignment with prepared talks
  - Format preferences
  - Geographic preferences
  - Deadline urgency bonus

Outputs a ranked list with scores and suggested talk pairings.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CFPS_FILE = DATA_DIR / "cfps.json"
PROFILE_FILE = DATA_DIR / "profile.json"


def load_json(path):
    with open(path) as f:
        return json.load(f)


def normalize(text):
    """Normalize text for comparison."""
    return re.sub(r'[^a-z0-9\s]', '', text.lower()).strip()


def tokenize(text):
    """Split text into meaningful tokens."""
    stop_words = {"the", "a", "an", "and", "or", "for", "in", "on", "at", "to", "of", "is", "it", "with", "by", "from"}
    words = normalize(text).split()
    return [w for w in words if w not in stop_words and len(w) > 2]


def compute_tag_score(cfp_tags, cfp_title, cfp_desc, profile):
    """Score based on tag/keyword overlap with speaker expertise."""
    # Build keyword pool from profile
    keywords = set()
    for k in profile.get("expertise", {}).get("primary", []):
        keywords.update(tokenize(k))
    for k in profile.get("expertise", {}).get("secondary", []):
        keywords.update(tokenize(k))
    for k in profile.get("matching_preferences", {}).get("priority_keywords", []):
        keywords.update(tokenize(k))

    # Build token pool from CFP
    cfp_tokens = set()
    for tag in cfp_tags:
        cfp_tokens.update(tokenize(tag))
    cfp_tokens.update(tokenize(cfp_title))
    cfp_tokens.update(tokenize(cfp_desc))

    if not keywords or not cfp_tokens:
        return 0.0

    overlap = keywords & cfp_tokens
    if not overlap:
        return 0.0

    # Use a combination: how much of CFP matches profile + absolute match bonus
    # This avoids penalizing CFPs just because the profile keyword list is large
    cfp_coverage = len(overlap) / max(len(cfp_tokens), 1)  # What % of CFP is relevant
    profile_coverage = len(overlap) / max(len(keywords), 1)  # What % of profile matches
    match_bonus = min(len(overlap) * 0.15, 0.5)  # Bonus per matched keyword

    score = (cfp_coverage * 0.4) + (profile_coverage * 0.3) + match_bonus
    return min(score, 1.0)


def compute_talk_match(cfp_tags, cfp_title, cfp_desc, talks):
    """Find the best matching prepared talk for a CFP."""
    best_score = 0.0
    best_talk = None

    cfp_tokens = set()
    for tag in cfp_tags:
        cfp_tokens.update(tokenize(tag))
    cfp_tokens.update(tokenize(cfp_title))
    cfp_tokens.update(tokenize(cfp_desc))

    for talk in talks:
        talk_tokens = set()
        talk_tokens.update(tokenize(talk.get("title", "")))
        talk_tokens.update(tokenize(talk.get("abstract", "")))
        for tag in talk.get("tags", []):
            talk_tokens.update(tokenize(tag))

        if not talk_tokens:
            continue

        overlap = cfp_tokens & talk_tokens
        score = len(overlap) / max(len(talk_tokens), 1)

        if score > best_score:
            best_score = score
            best_talk = talk

    return best_talk, min(best_score, 1.0)


def compute_deadline_urgency(deadline_str):
    """
    Give a bonus for CFPs with deadlines coming up soon.
    Closer deadlines get higher urgency (need to act fast).
    """
    if not deadline_str:
        return 0.1  # Low urgency if no deadline known

    try:
        deadline = datetime.strptime(deadline_str[:10], "%Y-%m-%d")
    except ValueError:
        return 0.1

    days_left = (deadline.date() - datetime.now().date()).days

    if days_left < 0:
        return 0.0  # Expired
    elif days_left <= 7:
        return 1.0  # Very urgent
    elif days_left <= 14:
        return 0.8
    elif days_left <= 30:
        return 0.6
    elif days_left <= 60:
        return 0.4
    else:
        return 0.2  # Plenty of time


def compute_format_score(cfp, preferences):
    """Score based on format/location preferences."""
    score = 0.5  # Base score

    # Bonus for online events if remote_ok
    if cfp.get("is_online"):
        score += 0.2

    # Bonus for matching preferred formats
    cfp_text = normalize(cfp.get("description", "") + " " + cfp.get("title", ""))
    for fmt in preferences.get("preferred_formats", []):
        if fmt.lower() in cfp_text:
            score += 0.1
            break

    return min(score, 1.0)


def score_cfp(cfp, profile):
    """Compute an overall relevance score for a CFP."""
    tags = cfp.get("tags", [])
    title = cfp.get("title", "")
    desc = cfp.get("description", "")
    preferences = profile.get("matching_preferences", {})
    talks = profile.get("talk_topics", [])

    # Compute individual scores
    tag_score = compute_tag_score(tags, title, desc, profile)
    best_talk, talk_score = compute_talk_match(tags, title, desc, talks)
    urgency = compute_deadline_urgency(cfp.get("deadline", ""))
    format_score = compute_format_score(cfp, preferences)

    # Weighted composite score
    weights = {
        "tag_relevance": 0.35,
        "talk_match": 0.30,
        "urgency": 0.15,
        "format": 0.20
    }

    composite = (
        tag_score * weights["tag_relevance"] +
        talk_score * weights["talk_match"] +
        urgency * weights["urgency"] +
        format_score * weights["format"]
    )

    return {
        "composite_score": round(composite, 3),
        "tag_relevance": round(tag_score, 3),
        "talk_match_score": round(talk_score, 3),
        "urgency_score": round(urgency, 3),
        "format_score": round(format_score, 3),
        "suggested_talk": best_talk.get("title") if best_talk else None,
        "suggested_talk_level": best_talk.get("level") if best_talk else None,
        "priority": "high" if composite >= 0.6 else "medium" if composite >= 0.4 else "low",
        "travel_sponsorship": cfp.get("travel_sponsorship", "unknown")
    }


def main():
    print("=" * 60)
    print("Speaking Engagement Intel - CFP Matcher & Scorer")
    print(f"Run time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    profile = load_json(PROFILE_FILE)
    cfps_data = load_json(CFPS_FILE)
    cfps = cfps_data.get("cfps", [])
    min_score = profile.get("matching_preferences", {}).get("min_relevance_score", 0.3)

    print(f"\nScoring {len(cfps)} CFPs against profile...")
    print(f"Minimum relevance threshold: {min_score}")

    scored = []
    for cfp in cfps:
        if cfp.get("status") != "open":
            cfp["match_scores"] = None
            scored.append(cfp)
            continue

        scores = score_cfp(cfp, profile)
        cfp["match_scores"] = scores
        scored.append(cfp)

    # Sort by composite score (highest first), open only
    open_scored = [c for c in scored if c.get("status") == "open" and c.get("match_scores")]
    open_scored.sort(key=lambda c: c["match_scores"]["composite_score"], reverse=True)

    # Stats
    high = sum(1 for c in open_scored if c["match_scores"]["priority"] == "high")
    medium = sum(1 for c in open_scored if c["match_scores"]["priority"] == "medium")
    low = sum(1 for c in open_scored if c["match_scores"]["priority"] == "low")
    above_threshold = sum(1 for c in open_scored if c["match_scores"]["composite_score"] >= min_score)

    print(f"\nResults:")
    print(f"  High priority:   {high}")
    print(f"  Medium priority: {medium}")
    print(f"  Low priority:    {low}")
    print(f"  Above threshold: {above_threshold}")

    # Update metadata
    cfps_data["cfps"] = scored
    cfps_data["metadata"]["last_scored"] = datetime.now(timezone.utc).isoformat()
    cfps_data["metadata"]["high_priority"] = high
    cfps_data["metadata"]["medium_priority"] = medium
    cfps_data["metadata"]["above_threshold"] = above_threshold

    # Print top 10
    print(f"\nTop 10 Matches:")
    print("-" * 60)
    for i, cfp in enumerate(open_scored[:10], 1):
        s = cfp["match_scores"]
        print(f"  {i}. [{s['composite_score']:.2f}] {cfp['title'][:50]}")
        print(f"     Priority: {s['priority']} | Talk: {s['suggested_talk'] or 'N/A'}")
        print(f"     Deadline: {cfp.get('deadline') or 'Unknown'} | Source: {cfp['source']}")

    # Save
    with open(CFPS_FILE, "w") as f:
        json.dump(cfps_data, f, indent=2)

    print(f"\nScored CFPs saved to {CFPS_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()

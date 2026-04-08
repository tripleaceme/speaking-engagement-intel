#!/usr/bin/env python3
"""
CFP Enricher — Follows CFP URLs to extract detailed information about
each conference: themes, categories, submission requirements, speaker
perks, and audience details.

This turns a bare "Tech conference in Malta" entry into a rich record
with categories like "AI, Cloud, DevOps, Data" and requirements like
"title, abstract, bio, 3 key takeaways".

Runs after crawl_cfps.py and before match_score.py.
"""

import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CFPS_FILE = DATA_DIR / "cfps.json"

HEADERS = {
    "User-Agent": "SpeakingEngagementIntel/1.0 (https://github.com/tripleaceme/speaking-engagement-intel)"
}

# Keywords that indicate specific conference tracks/themes
THEME_KEYWORDS = {
    "ai": ["artificial intelligence", "ai", "machine learning", "ml", "deep learning", "generative ai", "llm", "gpt", "neural"],
    "data": ["data engineering", "data science", "data analytics", "data pipeline", "etl", "elt", "data warehouse", "data lake", "data modeling", "dbt", "analytics engineering"],
    "cloud": ["cloud", "aws", "azure", "gcp", "kubernetes", "docker", "serverless", "terraform", "infrastructure"],
    "devops": ["devops", "ci/cd", "cicd", "deployment", "monitoring", "observability", "sre", "platform engineering"],
    "security": ["security", "cybersecurity", "infosec", "devsecops", "vulnerability", "penetration"],
    "web": ["web", "frontend", "backend", "javascript", "react", "vue", "angular", "api", "rest", "graphql"],
    "python": ["python", "django", "flask", "fastapi", "pandas", "numpy"],
    "database": ["database", "sql", "postgresql", "mysql", "mongodb", "snowflake", "bigquery", "redis"],
    "open-source": ["open source", "open-source", "oss", "foss", "community", "contributor", "maintainer"],
    "leadership": ["leadership", "career", "management", "soft skills", "team", "culture", "mentoring"],
    "education": ["education", "training", "workshop", "bootcamp", "teaching", "learning", "beginner"],
    "mobile": ["mobile", "ios", "android", "flutter", "react native", "swift", "kotlin"],
    "blockchain": ["blockchain", "web3", "crypto", "defi", "smart contract"],
    "iot": ["iot", "embedded", "hardware", "raspberry pi", "arduino"],
    "testing": ["testing", "qa", "quality assurance", "test automation", "tdd"],
}

# Speaker perk keywords
PERK_KEYWORDS = {
    "travel": ["travel covered", "travel reimbursement", "travel stipend", "travel expenses", "flight covered", "airfare", "travel assistance", "travel grant", "travel support", "we cover travel", "travel budget"],
    "hotel": ["hotel covered", "hotel provided", "accommodation provided", "accommodation covered", "complimentary hotel", "free hotel", "hotel nights", "lodging", "hotel accommodation"],
    "ticket": ["free ticket", "complimentary ticket", "conference pass", "free pass", "speaker pass", "free admission", "free entry"],
    "honorarium": ["honorarium", "speaker fee", "stipend", "compensation", "speaker payment"],
    "dinner": ["speaker dinner", "speakers dinner", "networking dinner"],
    "recording": ["talk recorded", "video recording", "recorded and published"],
}

# Submission requirement keywords
SUBMISSION_KEYWORDS = [
    "title", "abstract", "description", "bio", "biography",
    "takeaway", "key takeaways", "learning objectives",
    "session type", "talk length", "duration",
    "experience level", "difficulty", "target audience",
    "outline", "topic", "category", "track",
    "photo", "headshot", "social media", "twitter",
]


class TextExtractor(HTMLParser):
    """Simple HTML to text converter."""
    def __init__(self):
        super().__init__()
        self.text = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self.text.append(data)

    def get_text(self):
        return " ".join(self.text)


def fetch_page_text(url, timeout=15):
    """Fetch a URL and extract readable text from HTML."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, Exception):
        return None

    parser = TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        return None

    return parser.get_text()


def detect_themes(text):
    """Detect conference themes/categories from page text."""
    text_lower = text.lower()
    detected = []
    for theme, keywords in THEME_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text_lower)
        if hits >= 1:
            detected.append({"theme": theme, "confidence": min(hits / 3, 1.0)})

    # Sort by confidence
    detected.sort(key=lambda x: -x["confidence"])
    return detected


def detect_perks(text):
    """Detect speaker perks from page text."""
    text_lower = text.lower()
    perks = {}
    for perk, keywords in PERK_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                perks[perk] = True
                break
    return perks


def detect_submission_fields(text):
    """Detect what fields/info are required in the CFP submission."""
    text_lower = text.lower()
    fields = []
    for field in SUBMISSION_KEYWORDS:
        if field in text_lower:
            fields.append(field)
    return fields


def extract_categories_from_text(text):
    """Try to extract explicit category/track listings from text."""
    categories = []
    # Look for patterns like "Categories:", "Tracks:", "Topics:", followed by items
    patterns = [
        r'(?:categories|tracks|topics|themes|areas)[:\s]+([^\n.]{10,300})',
        r'(?:we are looking for|submit talks about|interested in)[:\s]+([^\n.]{10,300})',
        r'(?:session types?|talk types?)[:\s]+([^\n.]{10,200})',
    ]
    text_lower = text.lower()
    for pattern in patterns:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            # Split on common delimiters
            items = re.split(r'[,;•\-\|/]', match)
            for item in items:
                item = item.strip()
                if 3 < len(item) < 60:
                    categories.append(item)

    return list(set(categories))[:15]


def enrich_cfp(cfp):
    """Enrich a single CFP entry by fetching and analyzing its page."""
    # Only enrich if we don't already have rich data
    if cfp.get("themes") and len(cfp.get("themes", [])) > 0:
        return cfp  # Already enriched

    # Try CFP URL first, then event URL
    urls_to_try = []
    if cfp.get("cfp_url"):
        urls_to_try.append(cfp["cfp_url"])
    if cfp.get("url") and cfp["url"] != cfp.get("cfp_url"):
        urls_to_try.append(cfp["url"])

    page_text = None
    for url in urls_to_try:
        # Skip non-HTTP URLs
        if not url.startswith("http"):
            continue
        # Skip URLs that are unlikely to have useful text (Wix, SPAs)
        text = fetch_page_text(url)
        if text and len(text) > 100:
            page_text = text
            break

    if not page_text:
        return cfp

    # Detect themes
    themes = detect_themes(page_text)
    if themes:
        cfp["themes"] = themes
        # Add theme names to tags for better matching
        new_tags = set(cfp.get("tags", []))
        for t in themes:
            new_tags.add(t["theme"])
        cfp["tags"] = list(new_tags)

    # Detect explicit categories from text
    categories = extract_categories_from_text(page_text)
    if categories:
        cfp["categories"] = categories

    # Detect speaker perks
    perks = detect_perks(page_text)
    if perks:
        cfp["speaker_perks"] = perks
        # Update travel sponsorship based on actual page content
        if perks.get("travel") or perks.get("hotel"):
            cfp["travel_sponsorship"] = "yes"
        elif perks.get("ticket") or perks.get("dinner"):
            if cfp.get("travel_sponsorship") == "unknown":
                cfp["travel_sponsorship"] = "partial"

    # Detect submission requirements
    fields = detect_submission_fields(page_text)
    if fields:
        cfp["submission_fields"] = fields

    # Build a richer description from page content if current one is generic
    if len(cfp.get("description", "")) < 50:
        # Extract first meaningful paragraph
        sentences = page_text.split(".")
        meaningful = [s.strip() for s in sentences if 20 < len(s.strip()) < 300]
        if meaningful:
            cfp["description"] = ". ".join(meaningful[:3]) + "."

    cfp["enriched_at"] = datetime.now(timezone.utc).isoformat()
    return cfp


def main():
    print("=" * 60)
    print("Speaking Engagement Intel - CFP Enricher")
    print(f"Run time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    with open(CFPS_FILE) as f:
        data = json.load(f)

    cfps = data.get("cfps", [])
    open_cfps = [c for c in cfps if c.get("status") == "open"]

    print(f"\nTotal CFPs: {len(cfps)}")
    print(f"Open CFPs to enrich: {len(open_cfps)}")

    enriched = 0
    failed = 0
    for i, cfp in enumerate(open_cfps):
        # Skip already enriched
        if cfp.get("enriched_at"):
            continue

        title = cfp.get("title", "")[:40]
        print(f"  [{i+1}/{len(open_cfps)}] Enriching: {title}...", end=" ", flush=True)

        try:
            enrich_cfp(cfp)
            themes = cfp.get("themes", [])
            if themes:
                theme_names = [t["theme"] for t in themes[:3]]
                print(f"themes: {', '.join(theme_names)}")
                enriched += 1
            else:
                print("no themes detected")
        except Exception as e:
            print(f"ERROR: {e}")
            failed += 1

    # Update travel stats
    travel_yes = sum(1 for c in cfps if c.get("status") == "open" and c.get("travel_sponsorship") == "yes")
    travel_partial = sum(1 for c in cfps if c.get("status") == "open" and c.get("travel_sponsorship") == "partial")

    print(f"\nResults:")
    print(f"  Enriched: {enriched}")
    print(f"  Failed: {failed}")
    print(f"  Travel confirmed: {travel_yes}")
    print(f"  Travel partial: {travel_partial}")

    # Save
    with open(CFPS_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved to {CFPS_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
CFP Crawler — Discovers open Call for Papers / Call for Speakers
from multiple sources and saves them to data/cfps.json.

Sources:
  1. confs.tech (GitHub JSON — tech conference list)
  2. Sessionize open CFPs (public API)
  3. dev.to CFP listings (community posts)
  4. GitHub awesome-cfp lists
  5. Papercall open CFPs
  6. GitHub Topics Search
  7. callfordataspeakers.com (REST API — data-specific CFPs)
  8. Google Custom Search (speaking engagement submissions)
  9. Open source conferences (Linux Foundation, CNCF, Python, etc.)

Runs as a GitHub Action on a daily schedule.
"""

import json
import os
import re
import hashlib
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CFPS_FILE = DATA_DIR / "cfps.json"

HEADERS = {
    "User-Agent": "SpeakingEngagementIntel/1.0 (https://github.com/tripleaceme/speaking-engagement-intel)"
}

# ─── Travel Sponsorship Detection ─────────────────────────────────
# Keywords that indicate speaker travel/accommodation support
TRAVEL_POSITIVE_KEYWORDS = [
    "travel", "hotel", "accommodation", "flight", "reimburse",
    "stipend", "covered", "sponsor speakers", "speaker perks",
    "travel assistance", "travel grant", "travel support",
    "we cover", "we pay", "expenses covered", "expenses paid",
    "complimentary hotel", "free hotel", "speaker package",
    "speaker benefit", "lodging", "airfare", "transportation",
    "travel fund", "travel budget", "speaker dinner",
]
TRAVEL_NEGATIVE_KEYWORDS = [
    "no travel", "not cover travel", "not provide travel",
    "speakers pay", "no reimbursement", "no sponsorship for travel",
    "at your own expense", "own cost",
]


def detect_travel_sponsorship(text):
    """
    Analyze text for travel/accommodation sponsorship signals.
    Returns: "yes", "no", "partial", or "unknown"
    """
    if not text:
        return "unknown"
    text_lower = text.lower()

    # Check negative signals first (more specific)
    for kw in TRAVEL_NEGATIVE_KEYWORDS:
        if kw in text_lower:
            return "no"

    # Check positive signals
    positive_hits = sum(1 for kw in TRAVEL_POSITIVE_KEYWORDS if kw in text_lower)

    if positive_hits >= 2:
        return "yes"
    elif positive_hits == 1:
        return "partial"  # Mentioned but not confirmed
    return "unknown"


def fetch_url(url, timeout=30):
    """Fetch a URL and return the response text."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"  [WARN] Failed to fetch {url}: {e}")
        return None


def generate_cfp_id(source, title, url):
    """Generate a deterministic ID for a CFP entry."""
    raw = f"{source}|{title}|{url}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def make_cfp_entry(source, title, url, cfp_url, description, tags,
                   deadline, event_date, location, is_online,
                   travel_sponsorship="unknown", event_type=""):
    """Build a standardized CFP entry dict."""
    # Auto-detect travel sponsorship from description if not provided
    if travel_sponsorship == "unknown" and description:
        travel_sponsorship = detect_travel_sponsorship(description)

    return {
        "id": generate_cfp_id(source, title, cfp_url or url),
        "source": source,
        "title": title,
        "url": url,
        "cfp_url": cfp_url or url,
        "description": description[:500] if description else "",
        "tags": tags,
        "deadline": deadline,
        "event_date": event_date,
        "location": location,
        "is_online": is_online,
        "travel_sponsorship": travel_sponsorship,
        "event_type": event_type,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "status": "open"
    }


# ─── Source 1: confs.tech ────────────────────────────────────────
def crawl_confs_tech():
    """Fetch conferences from confs.tech GitHub data."""
    cfps = []
    year = datetime.now().year
    topics = ["data", "python", "devops", "general", "javascript", "golang"]

    for topic in topics:
        url = f"https://raw.githubusercontent.com/tech-conferences/conference-data/main/conferences/{year}/{topic}.json"
        text = fetch_url(url)
        if not text:
            continue

        try:
            confs = json.loads(text)
        except json.JSONDecodeError:
            continue

        for conf in confs:
            cfp_url = conf.get("cfpUrl", "")
            cfp_end = conf.get("cfpEndDate", "")
            if not cfp_url and not cfp_end:
                continue

            if cfp_end:
                try:
                    if datetime.strptime(cfp_end, "%Y-%m-%d").date() < datetime.now().date():
                        continue
                except ValueError:
                    pass

            cfps.append(make_cfp_entry(
                source="confs.tech",
                title=conf.get("name", "Unknown Conference"),
                url=conf.get("url", ""),
                cfp_url=cfp_url,
                description=f"Tech conference in {conf.get('city', 'TBD')}, {conf.get('country', 'TBD')}",
                tags=[topic] + (["online"] if conf.get("online", False) else []),
                deadline=cfp_end,
                event_date=conf.get("startDate", ""),
                location=f"{conf.get('city', 'TBD')}, {conf.get('country', 'TBD')}",
                is_online=conf.get("online", False),
                event_type="conference",
            ))

    print(f"  [confs.tech] Found {len(cfps)} open CFPs")
    return cfps


# ─── Source 2: Sessionize ────────────────────────────────────────
def crawl_sessionize():
    """Fetch open CFPs from Sessionize's public API."""
    cfps = []
    url = "https://sessionize.com/api/v2/cfps"
    text = fetch_url(url)
    if not text:
        return cfps

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return cfps

    for item in data:
        cfp_end = item.get("cfpEnd", "")
        if cfp_end:
            try:
                deadline = datetime.fromisoformat(cfp_end.replace("Z", "+00:00"))
                if deadline < datetime.now(timezone.utc):
                    continue
            except (ValueError, TypeError):
                pass

        desc = item.get("description", "") or ""
        cfps.append(make_cfp_entry(
            source="sessionize",
            title=item.get("name", "Unknown Event"),
            url=item.get("eventUrl", ""),
            cfp_url=item.get("cfpUrl", ""),
            description=desc,
            tags=[t.lower() for t in item.get("categories", [])],
            deadline=cfp_end[:10] if cfp_end else "",
            event_date=item.get("eventStart", "")[:10] if item.get("eventStart") else "",
            location=item.get("location", ""),
            is_online=item.get("isOnline", False),
            travel_sponsorship=detect_travel_sponsorship(desc),
        ))

    print(f"  [sessionize] Found {len(cfps)} open CFPs")
    return cfps


# ─── Source 3: dev.to CFP posts ──────────────────────────────────
def crawl_devto():
    """Search dev.to for CFP-related posts."""
    cfps = []
    url = "https://dev.to/api/articles?tag=cfp&per_page=30"
    text = fetch_url(url)
    if not text:
        return cfps

    try:
        articles = json.loads(text)
    except json.JSONDecodeError:
        return cfps

    for article in articles:
        pub_date = article.get("published_at", "")
        if pub_date:
            try:
                pub = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - pub).days > 90:
                    continue
            except (ValueError, TypeError):
                pass

        desc = article.get("description", "") or ""
        cfps.append(make_cfp_entry(
            source="dev.to",
            title=article.get("title", "Unknown"),
            url=article.get("url", ""),
            cfp_url=article.get("url", ""),
            description=desc,
            tags=article.get("tag_list", []),
            deadline="",
            event_date="",
            location="",
            is_online=True,
            travel_sponsorship=detect_travel_sponsorship(desc),
        ))

    # Deduplicate by URL
    seen = set()
    unique = []
    for c in cfps:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique.append(c)

    print(f"  [dev.to] Found {len(unique)} CFP-related posts")
    return unique


# ─── Source 4: awesome-cfp GitHub list ────────────────────────────
def crawl_cfpland():
    """Crawl CFP aggregator sites for open calls."""
    cfps = []
    url = "https://raw.githubusercontent.com/shortjared/awesome-call-for-papers/master/README.md"
    text = fetch_url(url)
    if not text:
        return cfps

    link_pattern = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')
    matches = link_pattern.findall(text)

    for title, link in matches:
        if any(skip in link.lower() for skip in ["github.com", "twitter.com", "shields.io"]):
            continue
        cfps.append(make_cfp_entry(
            source="awesome-cfp",
            title=title.strip(),
            url=link,
            cfp_url=link,
            description="From awesome-call-for-papers list",
            tags=[],
            deadline="",
            event_date="",
            location="",
            is_online=False,
        ))

    print(f"  [awesome-cfp] Found {len(cfps)} entries")
    return cfps


# ─── Source 5: Papercall ─────────────────────────────────────────
def crawl_papercall():
    """Fetch open CFPs from Papercall."""
    cfps = []
    url = "https://www.papercall.io/cfps.json"
    text = fetch_url(url)
    if not text:
        return cfps

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return cfps

    for item in data:
        cfp_end = item.get("cfp_end_date", "") or item.get("end_date", "")
        if cfp_end:
            try:
                if datetime.strptime(cfp_end[:10], "%Y-%m-%d").date() < datetime.now().date():
                    continue
            except ValueError:
                pass

        desc = item.get("description", "") or ""
        cfps.append(make_cfp_entry(
            source="papercall",
            title=item.get("name", "Unknown"),
            url=item.get("website", ""),
            cfp_url=f"https://www.papercall.io/cfps/{item.get('id', '')}",
            description=desc,
            tags=[t.get("name", "").lower() for t in item.get("tags", []) if isinstance(t, dict)],
            deadline=cfp_end[:10] if cfp_end else "",
            event_date=item.get("event_start", "")[:10] if item.get("event_start") else "",
            location=item.get("location", ""),
            is_online=item.get("virtual", False),
            travel_sponsorship=detect_travel_sponsorship(desc),
        ))

    print(f"  [papercall] Found {len(cfps)} open CFPs")
    return cfps


# ─── Source 6: GitHub Topics Search ──────────────────────────────
def crawl_github_topics():
    """Search GitHub for repos/issues tagged with CFP-related topics."""
    cfps = []
    url = "https://api.github.com/search/repositories?q=topic:call-for-papers+topic:conference&sort=updated&per_page=20"
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {**HEADERS}
    if token:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"  [github] Failed: {e}")
        return cfps

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return cfps

    for repo in data.get("items", []):
        desc = repo.get("description") or ""
        cfps.append(make_cfp_entry(
            source="github",
            title=repo.get("full_name", "Unknown"),
            url=repo.get("html_url", ""),
            cfp_url=repo.get("html_url", ""),
            description=desc,
            tags=repo.get("topics", []),
            deadline="",
            event_date="",
            location="",
            is_online=True,
            travel_sponsorship=detect_travel_sponsorship(desc),
        ))

    print(f"  [github] Found {len(cfps)} CFP-related repos")
    return cfps


# ─── Source 7: callfordataspeakers.com ────────────────────────────
def crawl_callfordataspeakers():
    """
    Fetch open CFPs from callfordataspeakers.com REST API.
    This is a curated list of data-specific conferences and meetups.
    API: https://callfordataspeakers.com/api/events
    """
    cfps = []
    url = "https://callfordataspeakers.com/api/events"
    text = fetch_url(url)
    if not text:
        return cfps

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return cfps

    now = datetime.now(timezone.utc)

    for item in data:
        # Parse dates
        event_date_raw = item.get("Date", "")
        end_date_raw = item.get("EndDate", "")
        cfs_closes_raw = item.get("Cfs_Closes", "") or ""
        event_name = item.get("EventName", "")
        event_url = item.get("URL", "")
        info = item.get("Information", "") or ""
        venue = item.get("Venue", "") or ""
        regions = item.get("Regions", "") or ""
        event_type = item.get("EventType", "") or ""

        if not event_name:
            continue

        # Parse CFP deadline
        deadline = ""
        if cfs_closes_raw:
            try:
                cfs_dt = datetime.fromisoformat(cfs_closes_raw.replace("Z", "+00:00"))
                if cfs_dt < now:
                    continue  # CFP already closed
                deadline = cfs_dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        # Parse event date
        event_date = ""
        if event_date_raw:
            try:
                event_date = datetime.fromisoformat(event_date_raw.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        # Skip events that have already passed (if no CFP deadline, check event date)
        if not deadline and event_date:
            try:
                if datetime.strptime(event_date, "%Y-%m-%d").date() < now.date():
                    continue
            except ValueError:
                pass

        # Determine if online
        is_online = "virtual" in regions.lower() or "online" in venue.lower()

        # Build tags from event type and regions
        tags = ["data"]
        if event_type:
            tags.append(event_type.lower())
        for region in regions.split(","):
            region = region.strip().lower()
            if region and region != "virtual":
                tags.append(region)

        # Check travel sponsorship from info field
        travel = detect_travel_sponsorship(info + " " + event_name)

        cfps.append(make_cfp_entry(
            source="callfordataspeakers",
            title=event_name,
            url=event_url,
            cfp_url=event_url,
            description=info if info else f"Data {event_type.lower()} — {venue}",
            tags=tags,
            deadline=deadline,
            event_date=event_date,
            location=venue,
            is_online=is_online,
            travel_sponsorship=travel,
            event_type=event_type.lower(),
        ))

    print(f"  [callfordataspeakers] Found {len(cfps)} open CFPs")
    return cfps


# ─── Source 8: Google Custom Search ──────────────────────────────
def crawl_google_search():
    """
    Use Google Custom Search API to find open CFPs for speaking engagements.
    Requires GOOGLE_CSE_ID and GOOGLE_API_KEY environment variables.
    Free tier: 100 queries/day — we use ~5 queries per run.
    """
    cfps = []
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    cse_id = os.environ.get("GOOGLE_CSE_ID", "")

    if not api_key or not cse_id:
        print("  [google] Skipped — GOOGLE_API_KEY or GOOGLE_CSE_ID not set")
        return cfps

    queries = [
        '"call for speakers" data engineering 2026',
        '"call for papers" analytics dbt open',
        '"call for speakers" open source conference speaker application',
        '"cfp open" data conference speaker travel',
        '"submit a talk" data pipeline analytics engineering',
    ]

    seen_urls = set()
    for query in queries:
        encoded = urllib.parse.urlencode({
            "key": api_key,
            "cx": cse_id,
            "q": query,
            "num": 10,
            "dateRestrict": "m3",  # Last 3 months
        })
        url = f"https://www.googleapis.com/customsearch/v1?{encoded}"
        text = fetch_url(url)
        if not text:
            continue

        try:
            results = json.loads(text)
        except json.JSONDecodeError:
            continue

        for item in results.get("items", []):
            link = item.get("link", "")
            if link in seen_urls:
                continue
            seen_urls.add(link)

            title = item.get("title", "")
            snippet = item.get("snippet", "")
            combined_text = f"{title} {snippet}"

            # Skip non-CFP results
            cfp_signals = ["call for", "cfp", "submit", "speaker", "proposal", "paper"]
            if not any(sig in combined_text.lower() for sig in cfp_signals):
                continue

            travel = detect_travel_sponsorship(combined_text)

            cfps.append(make_cfp_entry(
                source="google",
                title=title,
                url=link,
                cfp_url=link,
                description=snippet,
                tags=["data", "conference"],
                deadline="",
                event_date="",
                location="",
                is_online=False,
                travel_sponsorship=travel,
            ))

    print(f"  [google] Found {len(cfps)} CFP results")
    return cfps


# ─── Source 9: Open Source Conferences ────────────────────────────
def crawl_opensource_conferences():
    """
    Crawl known open-source conference CFP pages.
    These are curated URLs for major open-source events that regularly
    accept speakers and often sponsor travel.
    """
    cfps = []

    # Linux Foundation events calendar (JSON feed)
    lf_url = "https://events.linuxfoundation.org/about/calendar/"
    # Try the confs.tech open-source topic
    for topic in ["ruby", "rust", "elixir"]:
        year = datetime.now().year
        url = f"https://raw.githubusercontent.com/tech-conferences/conference-data/main/conferences/{year}/{topic}.json"
        text = fetch_url(url)
        if not text:
            continue
        try:
            confs = json.loads(text)
        except json.JSONDecodeError:
            continue

        for conf in confs:
            cfp_url = conf.get("cfpUrl", "")
            cfp_end = conf.get("cfpEndDate", "")
            if not cfp_url and not cfp_end:
                continue
            if cfp_end:
                try:
                    if datetime.strptime(cfp_end, "%Y-%m-%d").date() < datetime.now().date():
                        continue
                except ValueError:
                    pass

            name = conf.get("name", "")
            # Tag as open-source if the name or URL suggests it
            tags = [topic, "open-source"]

            cfps.append(make_cfp_entry(
                source="opensource",
                title=name or "Unknown Conference",
                url=conf.get("url", ""),
                cfp_url=cfp_url,
                description=f"Open source conference in {conf.get('city', 'TBD')}, {conf.get('country', 'TBD')}",
                tags=tags,
                deadline=cfp_end,
                event_date=conf.get("startDate", ""),
                location=f"{conf.get('city', 'TBD')}, {conf.get('country', 'TBD')}",
                is_online=conf.get("online", False),
                event_type="conference",
            ))

    # Known open-source CFP aggregators on GitHub
    oss_url = "https://api.github.com/search/repositories?q=topic:open-source+topic:cfp+topic:conference&sort=updated&per_page=15"
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {**HEADERS}
    if token:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(oss_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
        data = json.loads(text)
        for repo in data.get("items", []):
            desc = repo.get("description") or ""
            cfps.append(make_cfp_entry(
                source="opensource",
                title=repo.get("full_name", "Unknown"),
                url=repo.get("html_url", ""),
                cfp_url=repo.get("html_url", ""),
                description=desc,
                tags=["open-source"] + repo.get("topics", []),
                deadline="",
                event_date="",
                location="",
                is_online=True,
                travel_sponsorship=detect_travel_sponsorship(desc),
            ))
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"  [opensource/github] Failed: {e}")

    print(f"  [opensource] Found {len(cfps)} open source CFPs")
    return cfps


# ─── Main Orchestrator ───────────────────────────────────────────
def load_existing_cfps():
    """Load existing CFPs to merge with new discoveries."""
    if CFPS_FILE.exists():
        with open(CFPS_FILE) as f:
            return json.load(f)
    return {"metadata": {}, "cfps": []}


def merge_cfps(existing_cfps, new_cfps):
    """Merge new CFPs with existing, avoiding duplicates."""
    existing_ids = {c["id"] for c in existing_cfps}
    added = 0
    for cfp in new_cfps:
        if cfp["id"] not in existing_ids:
            existing_cfps.append(cfp)
            existing_ids.add(cfp["id"])
            added += 1
    return existing_cfps, added


def backfill_travel_field(cfps):
    """Add travel_sponsorship field to old CFP entries that lack it."""
    for cfp in cfps:
        if "travel_sponsorship" not in cfp:
            cfp["travel_sponsorship"] = detect_travel_sponsorship(
                cfp.get("description", "") + " " + cfp.get("title", "")
            )
        if "event_type" not in cfp:
            cfp["event_type"] = ""


def mark_expired(cfps):
    """Mark CFPs with passed deadlines as expired."""
    today = datetime.now().date()
    expired_count = 0
    for cfp in cfps:
        if cfp.get("status") == "open" and cfp.get("deadline"):
            try:
                deadline = datetime.strptime(cfp["deadline"][:10], "%Y-%m-%d").date()
                if deadline < today:
                    cfp["status"] = "expired"
                    expired_count += 1
            except ValueError:
                pass
    return expired_count


def main():
    print("=" * 60)
    print("Speaking Engagement Intel - CFP Crawler")
    print(f"Run time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # Load existing data
    data = load_existing_cfps()
    existing_cfps = data.get("cfps", [])
    print(f"\nExisting CFPs in database: {len(existing_cfps)}")

    # Backfill travel_sponsorship for old entries
    backfill_travel_field(existing_cfps)

    # Crawl all sources
    print("\nCrawling sources...")
    all_new = []

    crawlers = [
        ("confs.tech", crawl_confs_tech),
        ("Sessionize", crawl_sessionize),
        ("dev.to", crawl_devto),
        ("awesome-cfp", crawl_cfpland),
        ("Papercall", crawl_papercall),
        ("GitHub", crawl_github_topics),
        ("callfordataspeakers.com", crawl_callfordataspeakers),
        ("Google Search", crawl_google_search),
        ("Open Source Conferences", crawl_opensource_conferences),
    ]

    sources_checked = 0
    for name, crawler in crawlers:
        print(f"\n  Crawling {name}...")
        try:
            results = crawler()
            all_new.extend(results)
            sources_checked += 1
        except Exception as e:
            print(f"  [ERROR] {name} crawler failed: {e}")

    # Merge with existing
    print(f"\nTotal new CFPs discovered: {len(all_new)}")
    merged, added = merge_cfps(existing_cfps, all_new)
    print(f"New unique CFPs added: {added}")

    # Mark expired CFPs
    expired = mark_expired(merged)
    print(f"CFPs marked as expired: {expired}")

    # Count stats
    open_count = sum(1 for c in merged if c.get("status") == "open")
    travel_yes = sum(1 for c in merged if c.get("status") == "open" and c.get("travel_sponsorship") == "yes")
    travel_partial = sum(1 for c in merged if c.get("status") == "open" and c.get("travel_sponsorship") == "partial")
    print(f"Open CFPs: {open_count}")
    print(f"  with confirmed travel support: {travel_yes}")
    print(f"  with possible travel support: {travel_partial}")

    # Save
    output = {
        "metadata": {
            "last_crawled": datetime.now(timezone.utc).isoformat(),
            "total_cfps": len(merged),
            "open_cfps": open_count,
            "sources_checked": sources_checked,
            "new_this_run": added,
            "expired_this_run": expired,
            "travel_sponsorship_yes": travel_yes,
            "travel_sponsorship_partial": travel_partial,
        },
        "cfps": merged
    }

    with open(CFPS_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved {len(merged)} CFPs to {CFPS_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()

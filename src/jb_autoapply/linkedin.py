"""
LinkedIn job search via the public guest API.

Uses LinkedIn's unauthenticated /jobs-guest endpoints to search for jobs
and fetch details. No API key, no login, no browser automation needed.

Usage:
    from jb_autoapply.linkedin import search_jobs
    jobs = search_jobs("software engineer intern", "Austin, TX", limit=10)

Output dicts match the queue format from selector.py for downstream use.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime
from typing import Any
from urllib.parse import quote, urlencode

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
JOB_DETAILS_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

REQUEST_TIMEOUT = 15  # seconds
REQUEST_DELAY = 0.5  # seconds between pagination requests


# ── Helpers ────────────────────────────────────────────────────────────


def _extract_job_id(entity_urn: str) -> str:
    """Extract numeric job ID from a LinkedIn entity URN like
    'urn:li:jobPosting:4416593239'."""
    match = re.search(r"jobPosting:(\d+)", entity_urn)
    return match.group(1) if match else ""


def _parse_relative_date(text: str) -> str | None:
    """Parse relative date strings like '1 day ago', '3 weeks ago' into ISO date."""
    text = text.strip().lower()
    now = date.today()

    match = re.match(r"(\d+)\s+(day|days|week|weeks|month|months|year|years|hour|hours|minute|minutes)\s+ago", text)
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)

    if unit in ("hour", "hours", "minute", "minutes"):
        return now.isoformat()  # posted today
    elif unit in ("day", "days"):
        d = now
        for _ in range(amount):
            d = date.fromordinal(d.toordinal() - 1)
        return d.isoformat()
    elif unit in ("week", "weeks"):
        d = now
        for _ in range(amount * 7):
            d = date.fromordinal(d.toordinal() - 1)
        return d.isoformat()
    elif unit in ("month", "months"):
        # Approximate: subtract N*30 days
        d = now
        for _ in range(amount * 30):
            d = date.fromordinal(d.toordinal() - 1)
        return d.isoformat()
    elif unit in ("year", "years"):
        d = now
        for _ in range(amount * 365):
            d = date.fromordinal(d.toordinal() - 1)
        return d.isoformat()

    return None


def _classify_role(title: str) -> str:
    """Classify a job title into a discipline category."""
    t = title.lower()
    if any(kw in t for kw in ("intern", "internship", "co-op", "coop")):
        return "internship"
    if any(kw in t for kw in ("new grad", "newgrad", "entry level", "graduate", "junior")):
        return "new-grad"
    return "new-grad"  # default for most early-career roles


def _classify_discipline(title: str) -> str:
    """Classify a job title into a discipline."""
    t = title.lower()
    if any(kw in t for kw in ("ml", "machine learning", "ai ", "artificial intelligence", "deep learning", "data science")):
        return "ml"
    if any(kw in t for kw in ("backend", "back-end", "back end")):
        return "backend"
    if any(kw in t for kw in ("frontend", "front-end", "front end", "ui", "react")):
        return "frontend"
    if any(kw in t for kw in ("data engineer", "data analyst", "data")):
        return "data"
    if any(kw in t for kw in ("devops", "sre", "infrastructure", "platform engineer")):
        return "devops"
    if any(kw in t for kw in ("security", "cyber")):
        return "security"
    if any(kw in t for kw in ("mobile", "ios", "android")):
        return "mobile"
    if any(kw in t for kw in ("hardware", "embedded", "firmware", "fpga")):
        return "hardware"
    if any(kw in t for kw in ("swe", "software engineer", "software developer", "full stack", "full-stack")):
        return "swe"
    return "swe"


# ── Search (list) API ────────────────────────────────────────────────


def search_jobs(
    keyword: str,
    location: str = "",
    limit: int = 10,
    max_pages: int = 5,
) -> list[dict[str, Any]]:
    """Search LinkedIn jobs via the public guest API.

    Args:
        keyword: Job title or keyword (e.g. 'software engineer intern')
        location: Location string (e.g. 'Austin, TX') — use '' for remote/anywhere
        limit: Maximum number of jobs to return
        max_pages: Maximum API pages to fetch (each page is ~25 results)

    Returns:
        List of job dicts with keys matching the queue format:
            - file (str): placeholder filename
            - path (str): placeholder path
            - company (str)
            - role (str)
            - category (str): 'internship' or 'new-grad'
            - discipline (str): 'swe', 'ml', 'backend', etc.
            - locations (list[str])
            - url (str): LinkedIn job URL
            - date_posted (str): ISO date string
            - linkedin_job_id (str): numeric job ID
            - source (str): 'linkedin'
            - priority (int): placeholder (0)
            - score_breakdown (dict): empty
    """
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    params: dict[str, str] = {
        "keywords": keyword,
        "start": "0",
    }
    if location:
        params["location"] = location

    for page in range(max_pages):
        if len(results) >= limit:
            break

        params["start"] = str(page * 25)
        url = f"{BASE_URL}?{urlencode(params, quote_via=quote)}"

        logger.debug("Fetching LinkedIn page %d: %s", page + 1, url)

        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Failed to fetch page %d: %s", page + 1, exc)
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.base-search-card")

        if not cards:
            logger.debug("No more job cards found on page %d", page + 1)
            break

        for card in cards:
            if len(results) >= limit:
                break

            entity_urn = str(card.get("data-entity-urn", "") or "")
            job_id = _extract_job_id(entity_urn)
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            # Job title
            title_el = card.select_one(".base-search-card__title")
            role = title_el.text.strip() if title_el else "Unknown Role"

            # Company name
            company_el = card.select_one(".base-search-card__subtitle")
            company = company_el.text.strip() if company_el else "Unknown Company"

            # Location
            location_el = card.select_one(".job-search-card__location")
            loc = location_el.text.strip() if location_el else ""

            # Job URL
            link_el = card.select_one(".base-card__full-link")
            job_url = link_el.get("href", "") if link_el else ""

            # Posted date
            date_el = card.select_one("time.job-search-card__listdate")
            date_posted = ""
            if date_el:
                dt = date_el.get("datetime", "")
                date_posted = dt if dt else _parse_relative_date(date_el.text.strip()) or ""

            results.append({
                "file": f"LinkedIn - {company} - {role}.md",
                "path": "",
                "company": company,
                "role": role,
                "category": _classify_role(role),
                "discipline": _classify_discipline(role),
                "locations": [loc] if loc else [],
                "url": job_url,
                "date_posted": date_posted,
                "linkedin_job_id": job_id,
                "source": "linkedin",
                "priority": 0,
                "score_breakdown": {},
            })

        # Small delay to be polite
        time.sleep(REQUEST_DELAY)

    return results[:limit]


# ── Job Details API ───────────────────────────────────────────────────


def get_job_details(job_id: str) -> dict[str, Any]:
    """Fetch detailed info for a single LinkedIn job posting.

    Args:
        job_id: Numeric LinkedIn job ID (e.g. '4416593239')

    Returns:
        Dict with detailed fields: title, company, location, description,
        seniority, employment_type, industries, etc.
    """
    url = JOB_DETAILS_URL.format(job_id=job_id)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Failed to fetch job details for %s: %s", job_id, exc)
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    details: dict[str, Any] = {}

    title_el = soup.select_one(".top-card-layout__title")
    details["title"] = title_el.text.strip() if title_el else ""

    company_el = soup.select_one(".topcard__org-name-link")
    details["company"] = company_el.text.strip() if company_el else ""

    # Location (first bullet)
    flavor_row = soup.select_one(".topcard__flavor-row")
    if flavor_row:
        bullets = flavor_row.select(".topcard__flavor--bullet")
        if bullets:
            details["location"] = bullets[0].text.strip()

    # Relative posted time
    posted_el = soup.select_one(".posted-time-ago__text")
    if posted_el:
        details["posted_relative"] = posted_el.text.strip()

    # Applicant count
    applicants_el = soup.select_one(".num-applicants__caption")
    if applicants_el:
        details["applicants"] = applicants_el.text.strip()

    # Description (show-more-less-html or standard description div)
    desc_el = soup.select_one(".show-more-less-html__markup, .description__text")
    if desc_el:
        details["description"] = desc_el.get_text(strip=True)

    # Criteria (seniority level, employment type, job function, industries)
    criteria_items = soup.select(".description__job-criteria-item")
    for item in criteria_items:
        label_el = item.select_one(".description__job-criteria-header")
        val_el = item.select_one(".description__job-criteria-text")
        if label_el and val_el:
            key = label_el.text.strip().lower().replace(" ", "_")
            details[key] = val_el.text.strip()

    details["linkedin_job_id"] = job_id
    return details


# ── CLI Entry Point ──────────────────────────────────────────────────


def cli_search(
    keyword: str,
    location: str = "",
    limit: int = 10,
    details: bool = False,
    json_output: bool = False,
) -> list[dict[str, Any]]:
    """Run a LinkedIn search from the CLI and print results.

    Returns the job list for programmatic use.
    """
    jobs = search_jobs(keyword=keyword, location=location, limit=limit)

    if not jobs:
        print("No jobs found.")
        return jobs

    if json_output:
        print(json.dumps(jobs, indent=2, ensure_ascii=False))
        return jobs

    print(f"\nLinkedIn Jobs — \"{keyword}\" in \"{location or 'Anywhere'}\"")
    print(f"{'#' :>3} | {'Company':30s} | {'Role':45s} | {'Location':20s} | {'Posted':12s} | Job ID")
    print("-" * 120)
    for i, job in enumerate(jobs, 1):
        loc = (job["locations"] or [""])[0][:20]
        posted = job["date_posted"][:10] if job["date_posted"] else ""
        jid = job.get("linkedin_job_id", "")
        company = job["company"][:30]
        role = job["role"][:45]
        print(f"{i:>3} | {company:30s} | {role:45s} | {loc:20s} | {posted:12s} | {jid}")

    if details:
        print("\n--- Fetching details ---")
        for job in jobs:
            jid = job.get("linkedin_job_id")
            if jid:
                info = get_job_details(jid)
                if info:
                    desc = info.get("description", "")
                    snippet = desc[:200] if desc else "(no description)"
                    print(f"\n{job['company']} — {job['role']}")
                    print(f"  {snippet}...")

    return jobs

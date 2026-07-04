"""
Greenhouse ATS adapter.
Fetches jobs from a company's public Greenhouse board via their JSON API.
"""

import logging
import requests
from bs4 import BeautifulSoup
from typing import List

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import config
from models import JobRecord

logger = logging.getLogger(__name__)

API_BASE = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"


def _html_to_text(html: str) -> str:
    """Convert HTML job description to clean plain text."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style tags entirely
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Collapse multiple blank lines
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_location(job_data: dict) -> str:
    """Pull a human-readable location string from Greenhouse's nested structure."""
    location = job_data.get("location", {})
    if isinstance(location, dict):
        return location.get("name", "")
    return str(location) if location else ""


def fetch_jobs(board_token: str, company_name: str = "") -> List[JobRecord]:
    """
    Fetch all open jobs from a Greenhouse board.

    Args:
        board_token: The company's Greenhouse board slug (e.g. "google").
        company_name: Friendly company name for the JobRecord. Falls back to board_token.

    Returns:
        List of JobRecord objects.
    """
    url = API_BASE.format(board_token=board_token)
    params = {"content": "true"}
    headers = {"User-Agent": config.USER_AGENT}
    company = company_name or board_token

    try:
        resp = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Greenhouse API error for '%s': %s", board_token, exc)
        return []

    data = resp.json()
    raw_jobs = data.get("jobs", [])
    logger.info("Greenhouse [%s]: fetched %d raw jobs", board_token, len(raw_jobs))

    records: List[JobRecord] = []
    for job in raw_jobs:
        title = job.get("title", "")
        location = _extract_location(job)
        description_html = job.get("content", "")
        apply_url = job.get("absolute_url", "")
        posted = job.get("updated_at", job.get("created_at", ""))

        # Build the plain-text description
        description = _html_to_text(description_html)

        records.append(
            JobRecord(
                title=title,
                company=company,
                apply_link=apply_url,
                location=location,
                description=description,
                posted_date=posted,
                source="greenhouse",
            )
        )

    return records

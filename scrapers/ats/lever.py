"""
Lever ATS adapter.
Fetches jobs from a company's public Lever postings API.
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

API_BASE = "https://api.lever.co/v0/postings/{company_slug}"


def _html_to_text(html: str) -> str:
    """Convert HTML content to clean plain text."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _build_description(posting: dict) -> str:
    """Combine Lever's 'lists' and 'additional' fields into one text block."""
    parts: list[str] = []

    # Main description (plain text already in some cases, HTML in others)
    desc_plain = posting.get("descriptionPlain", "")
    if desc_plain:
        parts.append(desc_plain)
    else:
        desc_html = posting.get("description", "")
        if desc_html:
            parts.append(_html_to_text(desc_html))

    # Lever breaks requirements/qualifications into 'lists'
    for lst in posting.get("lists", []):
        heading = lst.get("text", "")
        if heading:
            parts.append(f"\n{heading}")
        content = lst.get("content", "")
        if content:
            parts.append(_html_to_text(content))

    # Additional / closing section
    additional = posting.get("additional", "") or posting.get("additionalPlain", "")
    if additional:
        parts.append(_html_to_text(additional))

    return "\n".join(parts)


def _extract_location(posting: dict) -> str:
    """Get location from Lever's categories or top-level fields."""
    categories = posting.get("categories", {})
    if isinstance(categories, dict):
        loc = categories.get("location", "")
        if loc:
            return loc

    # Fallback: workplaceType or text field
    return posting.get("workplaceType", "")


def fetch_jobs(company_slug: str, company_name: str = "") -> List[JobRecord]:
    """
    Fetch all open postings from a Lever company page.

    Args:
        company_slug: The company's Lever slug (e.g. "netflix").
        company_name: Friendly company name for the JobRecord.

    Returns:
        List of JobRecord objects.
    """
    url = API_BASE.format(company_slug=company_slug)
    params = {"mode": "json"}
    headers = {"User-Agent": config.USER_AGENT}
    company = company_name or company_slug

    try:
        resp = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Lever API error for '%s': %s", company_slug, exc)
        return []

    postings = resp.json()
    if not isinstance(postings, list):
        logger.warning("Lever [%s]: unexpected response type: %s", company_slug, type(postings))
        return []

    logger.info("Lever [%s]: fetched %d raw postings", company_slug, len(postings))

    records: List[JobRecord] = []
    for posting in postings:
        title = posting.get("text", "")
        location = _extract_location(posting)
        apply_url = posting.get("hostedUrl", posting.get("applyUrl", ""))
        posted = posting.get("createdAt", "")
        # Lever returns createdAt as epoch ms — convert to ISO string
        if isinstance(posted, (int, float)) and posted > 0:
            import datetime
            posted = datetime.datetime.fromtimestamp(
                posted / 1000, tz=datetime.timezone.utc
            ).isoformat()

        description = _build_description(posting)

        records.append(
            JobRecord(
                title=title,
                company=company,
                apply_link=apply_url,
                location=location,
                description=description,
                posted_date=str(posted),
                source="lever",
            )
        )

    return records

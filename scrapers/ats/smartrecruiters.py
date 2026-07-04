"""
SmartRecruiters ATS adapter.
Fetches jobs from a company's public SmartRecruiters postings API.
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

# SmartRecruiters public job search API
API_BASE = "https://api.smartrecruiters.com/v1/companies/{company_id}/postings"
JOB_DETAIL_URL = "https://api.smartrecruiters.com/v1/companies/{company_id}/postings/{posting_id}"


def _html_to_text(html: str) -> str:
    """Convert HTML to clean plain text."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_location(posting: dict) -> str:
    """Build a location string from SmartRecruiters' nested location object."""
    loc = posting.get("location", {})
    if not isinstance(loc, dict):
        return ""

    parts = []
    city = loc.get("city", "")
    region = loc.get("region", "")
    country = loc.get("country", "")

    if city:
        parts.append(city)
    if region and region != city:
        parts.append(region)
    if country:
        parts.append(country)

    return ", ".join(parts)


def _build_description(posting: dict) -> str:
    """
    Combine SmartRecruiters' sectioned job description into one text block.
    The detail endpoint returns jobAd with sections array.
    """
    job_ad = posting.get("jobAd", {})
    sections = job_ad.get("sections", {})

    parts: list[str] = []

    # Main company description
    company_desc = sections.get("companyDescription", {})
    if company_desc.get("text"):
        parts.append(_html_to_text(company_desc["text"]))

    # Job description
    job_desc = sections.get("jobDescription", {})
    if job_desc.get("text"):
        parts.append(_html_to_text(job_desc["text"]))

    # Qualifications
    qualifications = sections.get("qualifications", {})
    if qualifications.get("text"):
        parts.append(_html_to_text(qualifications["text"]))

    # Additional info
    additional = sections.get("additionalInformation", {})
    if additional.get("text"):
        parts.append(_html_to_text(additional["text"]))

    # Fallback if no sections are present
    if not parts:
        name = posting.get("name", "")
        if name:
            parts.append(name)

    return "\n\n".join(parts)


def _fetch_all_pages(company_id: str, headers: dict) -> list[dict]:
    """
    Paginate through SmartRecruiters' listing endpoint.
    Returns a flat list of posting summaries.
    """
    all_postings: list[dict] = []
    offset = 0
    limit = 100  # SR max per page

    while True:
        url = API_BASE.format(company_id=company_id)
        params = {"offset": offset, "limit": limit}

        try:
            resp = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error(
                "SmartRecruiters listing error for '%s' (offset=%d): %s",
                company_id, offset, exc,
            )
            break

        data = resp.json()
        content = data.get("content", [])
        if not content:
            break

        all_postings.extend(content)
        total = data.get("totalFound", 0)

        offset += limit
        if offset >= total:
            break

    return all_postings


def fetch_jobs(company_id: str, company_name: str = "") -> List[JobRecord]:
    """
    Fetch all open jobs from a SmartRecruiters company page.

    Args:
        company_id: The company's SmartRecruiters identifier (e.g. "BOSCH").
        company_name: Friendly company name for the JobRecord.

    Returns:
        List of JobRecord objects.
    """
    headers = {
        "User-Agent": config.USER_AGENT,
        "Accept": "application/json",
    }
    company = company_name or company_id

    postings = _fetch_all_pages(company_id, headers)
    logger.info("SmartRecruiters [%s]: fetched %d raw postings", company_id, len(postings))

    records: List[JobRecord] = []
    for posting in postings:
        title = posting.get("name", "")
        location = _extract_location(posting)

        # Build apply link
        ref = posting.get("ref", "")
        posting_id = posting.get("id", "")
        # Public apply page URL pattern
        apply_url = f"https://jobs.smartrecruiters.com/{company_id}/{posting_id}" if posting_id else ref

        posted = posting.get("releasedDate", "")

        # SmartRecruiters listing endpoint includes a partial description;
        # the detail endpoint has the full jobAd sections.
        description = _build_description(posting)

        records.append(
            JobRecord(
                title=title,
                company=company,
                apply_link=apply_url,
                location=location,
                description=description,
                posted_date=str(posted),
                source="smartrecruiters",
            )
        )

    return records

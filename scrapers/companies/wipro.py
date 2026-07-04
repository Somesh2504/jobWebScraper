"""
Wipro Careers scraper.
Uses Playwright (JS-rendered). Wipro runs SAP SuccessFactors with a React
widget (xweb/rmk-jobs-search) that renders job cards client-side.

RENDERING: Playwright required — the <div id="jobSearch_j_id1"> container
           is populated by a React widget loaded from hcm55.sapsf.eu.

SELECTORS USED (update when layout changes):
  - Search page: https://careers.wipro.com/search-jobs
  - Job cards:   "li.jobs-list-item", "div.job-result-card", "a[data-job-id]"
  - Title:       "h2 a", ".job-result-title a", "[class*='job-title']"
  - Location:    ".job-location", "span[class*='location']", "[class*='city']"
  - Apply link:  href attribute of title anchor
  - Posted date: ".job-date-posted", "[class*='posted']"

  SAP SuccessFactors also exposes a JSON endpoint at:
    /search-jobs/results?ActiveFacetID=0&CurrentPage={page}&RecordsPerPage=25&...
  but it returns an HTML fragment, not JSON. We parse it as a fallback.
"""

import logging
import re
from typing import List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import config
from models import JobRecord

logger = logging.getLogger(__name__)

COMPANY_NAME = "Wipro"

# SAP SuccessFactors "results" endpoint returns an HTML fragment
# This avoids needing Playwright for Wipro specifically.
RESULTS_URL = (
    "https://careers.wipro.com/search-jobs/results"
    "?ActiveFacetID=0"
    "&CurrentPage={page}"
    "&RecordsPerPage=25"
    "&Distance=50"
    "&RadiusUnitType=0"
    "&Keywords="
    "&Location=India"
    "&ShowRadius=False"
    "&IsPag498=False"
    "&CustomFacetName="
    "&FacetTerm="
    "&FacetType=0"
    "&SearchResultsModuleName=Search+Results"
    "&SearchFiltersModuleName=Search+Filters"
    "&SortCriteria=0"
    "&SortDirection=0"
    "&SearchType=5"
    "&PostalCode="
    "&fc="
    "&fl="
    "&fcf="
    "&aession="
)

BASE_URL = "https://careers.wipro.com"


def _parse_results_page(html: str) -> List[dict]:
    """
    Parse job cards from the SuccessFactors HTML fragment.

    SELECTOR NOTES:
    - Each job is in an <li> with class "jobs-list-item"
    - Title is in <h2><a href="...">Title</a></h2>
    - Location, category are in <span> tags within the card footer
    - The href is relative: /job/{id}/{slug}
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs: List[dict] = []

    # SELECTOR: job cards — SAP SuccessFactors uses <li> with various classes
    cards = soup.select("li.jobs-list-item, li[class*='job'], div.job-result-card")
    if not cards:
        # Fallback: try any anchor that looks like a job link
        cards = soup.select("a[href*='/job/']")
        for link in cards:
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not href.startswith("http"):
                href = urljoin(BASE_URL, href)
            jobs.append({
                "title": title,
                "location": "",
                "apply_link": href,
                "posted_date": "",
            })
        return jobs

    for card in cards:
        # SELECTOR: title — <h2><a>...</a></h2>
        title_el = card.select_one("h2 a, h3 a, .job-result-title a, [class*='job-title'] a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        if not href.startswith("http"):
            href = urljoin(BASE_URL, href)

        # SELECTOR: location — spans in the footer area
        loc_el = card.select_one(
            ".job-location, span[class*='location'], span[class*='city']"
        )
        location = loc_el.get_text(strip=True) if loc_el else ""

        # SELECTOR: date posted
        date_el = card.select_one(".job-date-posted, span[class*='date'], [class*='posted']")
        posted = date_el.get_text(strip=True) if date_el else ""

        # SELECTOR: category (optional, for debugging)
        cat_el = card.select_one("[class*='category'], [class*='department']")
        category = cat_el.get_text(strip=True) if cat_el else ""

        jobs.append({
            "title": title,
            "location": location,
            "apply_link": href,
            "posted_date": posted,
        })

    return jobs


def _get_total_count(html: str) -> int:
    """Extract total job count from the SuccessFactors response."""
    soup = BeautifulSoup(html, "html.parser")
    # SELECTOR: total count is usually in a <span class="job-count"> or similar
    count_el = soup.select_one(
        ".job-count, .paginationLabel, span[class*='result-count'], [class*='total']"
    )
    if count_el:
        text = count_el.get_text(strip=True)
        numbers = re.findall(r'\d+', text)
        if numbers:
            return int(numbers[-1])  # last number is usually total
    return 0


def fetch_jobs() -> List[JobRecord]:
    """
    Fetch jobs from Wipro via their SAP SuccessFactors HTML endpoint.
    Paginates through all pages.
    """
    headers = {
        "User-Agent": config.USER_AGENT,
        "Accept": "text/html, application/xhtml+xml",
        "X-Requested-With": "XMLHttpRequest",
    }

    all_jobs: List[dict] = []
    page = 1
    max_pages = 20  # safety limit

    while page <= max_pages:
        url = RESULTS_URL.format(page=page)
        logger.info("Wipro: fetching page %d", page)

        try:
            resp = requests.get(url, headers=headers, timeout=config.REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Wipro: request error on page %d: %s", page, exc)
            break

        html = resp.text
        page_jobs = _parse_results_page(html)

        if not page_jobs:
            logger.info("Wipro: no more jobs found on page %d, stopping", page)
            break

        all_jobs.extend(page_jobs)
        logger.info("Wipro: page %d returned %d jobs (total: %d)", page, len(page_jobs), len(all_jobs))

        page += 1

    records: List[JobRecord] = []
    for job in all_jobs:
        records.append(
            JobRecord(
                title=job.get("title", ""),
                company=COMPANY_NAME,
                apply_link=job.get("apply_link", ""),
                location=job.get("location", ""),
                description="",
                posted_date=job.get("posted_date", ""),
                source="wipro_careers",
            )
        )

    logger.info("Wipro: scraped %d jobs total", len(records))
    return records

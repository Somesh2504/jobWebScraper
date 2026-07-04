"""
Cognizant Careers scraper.
Cognizant uses Oracle Taleo as their ATS.

RENDERING: Mixed — Taleo serves server-rendered HTML, but the job search uses
           JavaScript to paginate. We scrape the initial page with requests+BS4
           and also try the Taleo REST-like search endpoint.

SELECTORS USED (update when layout changes):
  - Search page:  https://careers.cognizant.com/global-en/jobs
  - Taleo portal: https://cognizant.taleo.net/careersection/4/jobsearch.ftl?lang=en
  - Job rows:     "tr.job-row", "div.job-card", "table#jobs tbody tr"
  - Title:        "a[class*='jobTitle']", "td.colTitle a", ".job-title a"
  - Location:     "td.colLocation", "span[class*='location']"
  - Apply link:   href on the title anchor (often relative to Taleo domain)
  - Posted date:  "td.colDate", "span[class*='date']"
  - Req ID:       "td.colReqId", "span[class*='reqId']"

  Cognizant also maintains a newer portal at careers.cognizant.com
  which may return 403 but has a REST search at:
    https://careers.cognizant.com/api/jobs?location=India&page=1
  (probed; may require special headers)
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

COMPANY_NAME = "Cognizant"

# Taleo portal (server-rendered HTML)
TALEO_URL = "https://cognizant.taleo.net/careersection/4/jobsearch.ftl"
TALEO_BASE = "https://cognizant.taleo.net"

# Newer careers portal (JS-rendered, may 403)
CAREERS_URL = "https://careers.cognizant.com/global-en/jobs"


def _scrape_taleo(search_keyword: str = "", location: str = "India") -> List[dict]:
    """
    Scrape the Taleo job search page.
    Taleo renders an HTML table with job listings.
    """
    headers = {
        "User-Agent": config.USER_AGENT,
        "Accept": "text/html",
    }
    params = {
        "lang": "en",
    }

    jobs: List[dict] = []

    try:
        resp = requests.get(
            TALEO_URL,
            params=params,
            headers=headers,
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Cognizant Taleo: request error: %s", exc)
        return jobs

    soup = BeautifulSoup(resp.text, "html.parser")

    # SELECTOR: Taleo job table rows
    # Taleo typically uses a table with class "tablelist" or similar
    rows = soup.select("table.tablelist tbody tr, tr[class*='job'], div.requisition")
    if not rows:
        # Fallback: look for any links that look like job requisitions
        links = soup.select("a[href*='requisition'], a[href*='jobdetail']")
        for link in links:
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = urljoin(TALEO_BASE, href)
            if title:
                jobs.append({
                    "title": title,
                    "location": "",
                    "apply_link": href,
                    "posted_date": "",
                })
        logger.info("Cognizant Taleo: found %d jobs via link fallback", len(jobs))
        return jobs

    logger.info("Cognizant Taleo: found %d table rows", len(rows))

    for row in rows:
        # SELECTOR: title — in <td> with class colTitle or first anchor
        title_el = row.select_one(
            "a[class*='jobTitle'], td.colTitle a, .job-title a, a[href*='requisition']"
        )
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        if href and not href.startswith("http"):
            href = urljoin(TALEO_BASE, href)

        # SELECTOR: location
        loc_el = row.select_one("td.colLocation, span[class*='location'], td:nth-of-type(3)")
        location_text = loc_el.get_text(strip=True) if loc_el else ""

        # SELECTOR: posted date
        date_el = row.select_one("td.colDate, span[class*='date'], td:nth-of-type(4)")
        posted = date_el.get_text(strip=True) if date_el else ""

        # SELECTOR: requisition ID
        req_el = row.select_one("td.colReqId, span[class*='reqId'], td:nth-of-type(2)")
        req_id = req_el.get_text(strip=True) if req_el else ""

        jobs.append({
            "title": title,
            "location": location_text,
            "apply_link": href,
            "posted_date": posted,
            "req_id": req_id,
        })

    return jobs


async def _scrape_careers_portal() -> List[dict]:
    """
    Fallback: scrape the newer careers.cognizant.com portal with Playwright.
    Only used if Taleo yields zero results.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Cognizant: playwright not installed, skipping careers portal")
        return []

    results: List[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=config.USER_AGENT,
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        try:
            await page.goto(CAREERS_URL, wait_until="networkidle", timeout=60000)

            selectors_to_try = [
                "div.job-card",
                "div[class*='JobCard']",
                "a[class*='job-listing']",
                "li[class*='job']",
            ]

            cards_selector = None
            for sel in selectors_to_try:
                try:
                    await page.wait_for_selector(sel, timeout=8000)
                    cards_selector = sel
                    break
                except Exception:
                    continue

            if not cards_selector:
                logger.warning("Cognizant careers portal: no selectors matched")
                await browser.close()
                return results

            cards = await page.query_selector_all(cards_selector)
            for card in cards:
                try:
                    title_el = await card.query_selector("h3, h4, [class*='title']")
                    title = await title_el.inner_text() if title_el else ""
                    title = title.strip().split("\n")[0]

                    loc_el = await card.query_selector("[class*='location']")
                    location = (await loc_el.inner_text()).strip() if loc_el else ""

                    link_el = await card.query_selector("a[href]")
                    href = await link_el.get_attribute("href") if link_el else ""
                    if href and not href.startswith("http"):
                        href = urljoin(CAREERS_URL, href)

                    results.append({
                        "title": title,
                        "location": location,
                        "apply_link": href,
                        "posted_date": "",
                    })
                except Exception:
                    continue

        except Exception as exc:
            logger.error("Cognizant careers portal Playwright error: %s", exc)
        finally:
            await browser.close()

    return results


def fetch_jobs() -> List[JobRecord]:
    """
    Fetch jobs from Cognizant.
    Strategy: Try Taleo first (faster, no browser needed), fall back to Playwright.
    """
    import asyncio

    raw_jobs = _scrape_taleo()

    # If Taleo didn't work, try the newer portal with Playwright
    if not raw_jobs:
        logger.info("Cognizant: Taleo yielded 0 jobs, trying careers portal with Playwright")
        try:
            raw_jobs = asyncio.run(_scrape_careers_portal())
        except Exception as exc:
            logger.error("Cognizant: Playwright fallback failed: %s", exc)

    if not raw_jobs:
        logger.warning("Cognizant: no jobs scraped from any source")
        return []

    records: List[JobRecord] = []
    for job in raw_jobs:
        records.append(
            JobRecord(
                title=job.get("title", ""),
                company=COMPANY_NAME,
                apply_link=job.get("apply_link", ""),
                location=job.get("location", ""),
                description="",
                posted_date=job.get("posted_date", ""),
                source="cognizant_careers",
            )
        )

    logger.info("Cognizant: scraped %d jobs total", len(records))
    return records

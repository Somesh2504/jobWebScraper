"""
TCS iBegin / TCS Careers scraper.
Uses Playwright (JS-rendered SPA). TCS blocks plain requests with 403/WAF.

RENDERING: Playwright required — the careers page is a React SPA behind Akamai WAF.

SELECTORS USED (update when layout changes):
  - Search page: https://www.tcs.com/careers/india/search-jobs
  - Fallback:    https://ibegin.tcs.com/iBegin/jobs
  - Job cards:   CSS selector "div.job-card" or "a[href*='/careers/']" with title text
  - Title:       ".job-card-title", ".job-title", "h3 a", or innerText of link
  - Location:    ".job-card-location", ".job-location", text near pin/map icon
  - Apply link:  href attribute of the job card anchor tag
  - Posted date: ".job-card-date", ".posted-date"
"""

import logging
import re
from typing import List

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import config
from models import JobRecord

logger = logging.getLogger(__name__)

# ── URLs to try in order (TCS reshuffles their careers site frequently) ──
CAREER_URLS = [
    "https://www.tcs.com/careers/india/search-jobs",
    "https://ibegin.tcs.com/iBegin/jobs",
]

COMPANY_NAME = "TCS"


async def _scrape_with_playwright(url: str) -> List[dict]:
    """
    Launch headless Chromium via Playwright, navigate to the TCS careers page,
    wait for job cards to render, and extract structured data.
    """
    from playwright.async_api import async_playwright

    results: List[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=config.USER_AGENT,
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # Wait for any job card container to appear
            # SELECTOR: try multiple common patterns TCS has used
            selectors_to_try = [
                "div.job-card",
                "div.search-result-item",
                "div[class*='JobCard']",
                "li.job-listing",
                "a[href*='job-detail']",
                "div[class*='job']",
            ]

            cards_selector = None
            for sel in selectors_to_try:
                try:
                    await page.wait_for_selector(sel, timeout=10000)
                    cards_selector = sel
                    logger.info("TCS: found job cards with selector '%s'", sel)
                    break
                except Exception:
                    continue

            if not cards_selector:
                logger.warning("TCS: no job card selector matched at %s", url)
                await browser.close()
                return results

            # Extract data from each card
            cards = await page.query_selector_all(cards_selector)
            logger.info("TCS: found %d job cards on page", len(cards))

            for card in cards:
                try:
                    # SELECTOR: title — try nested heading or direct text
                    title_el = (
                        await card.query_selector("h3, h4, .job-title, .job-card-title, [class*='title']")
                    )
                    title = await title_el.inner_text() if title_el else await card.inner_text()
                    title = title.strip().split("\n")[0]  # first line only

                    # SELECTOR: location
                    loc_el = await card.query_selector(
                        ".job-location, .job-card-location, [class*='location'], span[class*='loc']"
                    )
                    location = (await loc_el.inner_text()).strip() if loc_el else ""

                    # SELECTOR: apply link
                    link_el = await card.query_selector("a[href]")
                    href = await link_el.get_attribute("href") if link_el else ""
                    if href and not href.startswith("http"):
                        # Resolve relative URLs
                        from urllib.parse import urljoin
                        href = urljoin(url, href)

                    # SELECTOR: posted date
                    date_el = await card.query_selector(
                        ".posted-date, .job-card-date, [class*='date'], time"
                    )
                    posted = (await date_el.inner_text()).strip() if date_el else ""

                    results.append({
                        "title": title,
                        "location": location,
                        "apply_link": href,
                        "posted_date": posted,
                    })
                except Exception as exc:
                    logger.debug("TCS: failed to parse a card: %s", exc)
                    continue

        except Exception as exc:
            logger.error("TCS: Playwright error at %s: %s", url, exc)
        finally:
            await browser.close()

    return results


def fetch_jobs() -> List[JobRecord]:
    """
    Fetch entry-level / fresher jobs from TCS India careers.
    Tries multiple URLs in case one is down.
    """
    import asyncio

    raw_jobs: List[dict] = []
    for url in CAREER_URLS:
        logger.info("TCS: trying %s", url)
        try:
            raw_jobs = asyncio.run(_scrape_with_playwright(url))
            if raw_jobs:
                break
        except Exception as exc:
            logger.warning("TCS: failed on %s: %s", url, exc)
            continue

    if not raw_jobs:
        logger.warning("TCS: no jobs scraped from any URL")
        return []

    records: List[JobRecord] = []
    for job in raw_jobs:
        records.append(
            JobRecord(
                title=job.get("title", ""),
                company=COMPANY_NAME,
                apply_link=job.get("apply_link", ""),
                location=job.get("location", ""),
                description="",  # detail page scrape not implemented yet
                posted_date=job.get("posted_date", ""),
                source="tcs_careers",
            )
        )

    logger.info("TCS: scraped %d jobs total", len(records))
    return records

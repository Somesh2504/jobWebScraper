"""
Infosys Careers scraper.
Uses Playwright (JS-rendered SPA). Infosys returns 403 to plain requests.

RENDERING: Playwright required — careers portal is a JS SPA behind Akamai/CloudFlare.

SELECTORS USED (update when layout changes):
  - Search page: https://www.infosys.com/careers/apply.html
  - Alt page:    https://career.infosys.com/joblist
  - Job cards:   "div.job-card", "div.joblist-card", "li[class*='job']"
  - Title:       "h3", ".job-title", "a.job-link", "[class*='title']"
  - Location:    ".job-location", "[class*='location']"
  - Apply link:  href attribute of the job card anchor
  - Posted date: ".posted-date", "[class*='date']"
"""

import logging
from typing import List

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import config
from models import JobRecord

logger = logging.getLogger(__name__)

CAREER_URLS = [
    "https://career.infosys.com/joblist",
    "https://www.infosys.com/careers/apply.html",
]

COMPANY_NAME = "Infosys"


async def _scrape_with_playwright(url: str) -> List[dict]:
    """Launch headless browser, scrape Infosys careers."""
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

            # SELECTOR: try multiple patterns Infosys has used
            selectors_to_try = [
                "div.job-card",
                "div.joblist-card",
                "div[class*='JobCard']",
                "li[class*='job']",
                "tr.job-row",
                "div[class*='career']",
                "a[href*='joblist']",
            ]

            cards_selector = None
            for sel in selectors_to_try:
                try:
                    await page.wait_for_selector(sel, timeout=8000)
                    cards_selector = sel
                    logger.info("Infosys: found cards with selector '%s'", sel)
                    break
                except Exception:
                    continue

            if not cards_selector:
                logger.warning("Infosys: no job card selector matched at %s", url)
                await browser.close()
                return results

            cards = await page.query_selector_all(cards_selector)
            logger.info("Infosys: found %d job cards", len(cards))

            for card in cards:
                try:
                    # SELECTOR: title
                    title_el = await card.query_selector(
                        "h3, h4, .job-title, a.job-link, [class*='title']"
                    )
                    title = await title_el.inner_text() if title_el else await card.inner_text()
                    title = title.strip().split("\n")[0]

                    # SELECTOR: location
                    loc_el = await card.query_selector(
                        ".job-location, [class*='location'], span[class*='loc']"
                    )
                    location = (await loc_el.inner_text()).strip() if loc_el else ""

                    # SELECTOR: apply link
                    link_el = await card.query_selector("a[href]")
                    href = await link_el.get_attribute("href") if link_el else ""
                    if href and not href.startswith("http"):
                        from urllib.parse import urljoin
                        href = urljoin(url, href)

                    # SELECTOR: posted date
                    date_el = await card.query_selector(
                        ".posted-date, [class*='date'], time"
                    )
                    posted = (await date_el.inner_text()).strip() if date_el else ""

                    results.append({
                        "title": title,
                        "location": location,
                        "apply_link": href,
                        "posted_date": posted,
                    })
                except Exception as exc:
                    logger.debug("Infosys: failed to parse card: %s", exc)
                    continue

        except Exception as exc:
            logger.error("Infosys: Playwright error at %s: %s", url, exc)
        finally:
            await browser.close()

    return results


def fetch_jobs() -> List[JobRecord]:
    """Fetch jobs from Infosys careers portal."""
    import asyncio

    raw_jobs: List[dict] = []
    for url in CAREER_URLS:
        logger.info("Infosys: trying %s", url)
        try:
            raw_jobs = asyncio.run(_scrape_with_playwright(url))
            if raw_jobs:
                break
        except Exception as exc:
            logger.warning("Infosys: failed on %s: %s", url, exc)
            continue

    if not raw_jobs:
        logger.warning("Infosys: no jobs scraped from any URL")
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
                source="infosys_careers",
            )
        )

    logger.info("Infosys: scraped %d jobs total", len(records))
    return records

"""
Indeed India public job search scraper.
Indeed returns 403 to plain requests and uses aggressive anti-bot
(reCAPTCHA, CloudFlare). Requires Playwright.

RENDERING: Playwright required — 403 on requests, bot detection active.

SELECTORS USED (update when layout changes):
  - URL pattern:  https://in.indeed.com/jobs?q={query}&l={location}
  - Job cards:    "div.job_seen_beacon", "div.jobsearch-ResultsList > div", "li.css-*"
  - Title:        "h2.jobTitle a span", "a[data-jk] span[title]"
  - Company:      "span[data-testid='company-name']", "span.companyName"
  - Location:     "div[data-testid='text-location']", "div.companyLocation"
  - Apply link:   href of the title anchor (relative to indeed.com)
  - Posted date:  "span.date", "span[data-testid='myJobsStateDate']"
  - Salary:       "div.salary-snippet-container", "div.metadata.salary-snippet-container"
"""

import logging
from typing import List
from urllib.parse import quote_plus

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import config
from models import JobRecord

logger = logging.getLogger(__name__)

BASE_URL = "https://in.indeed.com"


def _build_search_url(keywords: List[str], location: str) -> str:
    query = quote_plus(" ".join(keywords))
    loc = quote_plus(location)
    return f"{BASE_URL}/jobs?q={query}&l={loc}&fromage=7"  # last 7 days


async def _scrape_with_playwright(url: str) -> List[dict]:
    from playwright.async_api import async_playwright
    results: List[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=config.USER_AGENT,
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # Indeed may show a CAPTCHA; we try to proceed anyway
            selectors_to_try = [
                "div.job_seen_beacon",
                "div.jobsearch-ResultsList > div",
                "li[class*='css-']",
                "td.resultContent",
                "div[data-jk]",
            ]

            cards_sel = None
            for sel in selectors_to_try:
                try:
                    await page.wait_for_selector(sel, timeout=12000)
                    cards_sel = sel
                    logger.info("Indeed: matched selector '%s'", sel)
                    break
                except Exception:
                    continue

            if not cards_sel:
                logger.warning("Indeed: no job cards found (possibly CAPTCHA)")
                await browser.close()
                return results

            cards = await page.query_selector_all(cards_sel)
            logger.info("Indeed: found %d cards", len(cards))

            for card in cards:
                try:
                    # SELECTOR: title
                    title_el = await card.query_selector(
                        "h2.jobTitle a span, a[data-jk] span[title], h2 a span, [class*='jobTitle'] span"
                    )
                    title = (await title_el.inner_text()).strip() if title_el else ""

                    # SELECTOR: apply link
                    link_el = await card.query_selector(
                        "h2.jobTitle a, a[data-jk], a[class*='jobTitle']"
                    )
                    href = (await link_el.get_attribute("href")) if link_el else ""
                    if href and not href.startswith("http"):
                        href = BASE_URL + href

                    # SELECTOR: company
                    comp_el = await card.query_selector(
                        "span[data-testid='company-name'], span.companyName, [class*='company']"
                    )
                    company = (await comp_el.inner_text()).strip() if comp_el else ""

                    # SELECTOR: location
                    loc_el = await card.query_selector(
                        "div[data-testid='text-location'], div.companyLocation, [class*='location']"
                    )
                    location_text = (await loc_el.inner_text()).strip() if loc_el else ""

                    # SELECTOR: salary
                    sal_el = await card.query_selector(
                        "div.salary-snippet-container, div[class*='salary'], span[class*='salary']"
                    )
                    salary = (await sal_el.inner_text()).strip() if sal_el else ""

                    # SELECTOR: posted date
                    date_el = await card.query_selector(
                        "span.date, span[data-testid='myJobsStateDate'], span[class*='date']"
                    )
                    posted = (await date_el.inner_text()).strip() if date_el else ""

                    results.append({
                        "title": title,
                        "company": company,
                        "location": location_text,
                        "apply_link": href,
                        "description": salary,
                        "posted_date": posted,
                    })
                except Exception as exc:
                    logger.debug("Indeed: card parse error: %s", exc)
                    continue

        except Exception as exc:
            logger.error("Indeed: Playwright error: %s", exc)
        finally:
            await browser.close()

    return results


def fetch_jobs(keywords: List[str], location: str = "Hyderabad") -> List[JobRecord]:
    """Fetch jobs from Indeed India public search."""
    import asyncio

    url = _build_search_url(keywords, location)
    logger.info("Indeed: searching %s", url)

    try:
        raw = asyncio.run(_scrape_with_playwright(url))
    except Exception as exc:
        logger.error("Indeed: scraping failed: %s", exc)
        raw = []

    records = []
    for job in raw:
        records.append(JobRecord(
            title=job.get("title", ""),
            company=job.get("company", ""),
            apply_link=job.get("apply_link", ""),
            location=job.get("location", ""),
            description=job.get("description", ""),
            posted_date=job.get("posted_date", ""),
            source="indeed",
        ))

    logger.info("Indeed: scraped %d jobs", len(records))
    return records

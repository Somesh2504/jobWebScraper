"""
Accenture India Careers scraper.
Uses Playwright (JS-rendered SPA). Accenture's job search is a React/Next.js app.

RENDERING: Playwright required — the page shell loads via AEM (Adobe Experience Manager)
           and job results are rendered client-side via a React component that fetches
           from an internal API.

SELECTORS USED (update when layout changes):
  - Search page:  https://www.accenture.com/in-en/careers/jobsearch?jk=&sb=1&pg=1&is_rj=0
  - Job cards:    "div.cmp-teaser-card", "div[class*='JobCard']", "a[class*='job-card']"
  - Title:        "h3", "a.cmp-teaser-card__title", "[class*='job-title']"
  - Location:     "span[class*='location']", "[class*='city']"
  - Apply link:   href on the card anchor or title anchor
  - Posted date:  "[class*='date']", "span[class*='posted']"
  - Skill/Level:  "[class*='skill']", "[class*='level']"
"""

import logging
from typing import List

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import config
from models import JobRecord

logger = logging.getLogger(__name__)

CAREER_URL = "https://www.accenture.com/in-en/careers/jobsearch?jk=&sb=1&pg=1&is_rj=0"
COMPANY_NAME = "Accenture"


async def _scrape_with_playwright() -> List[dict]:
    """Launch headless browser, scrape Accenture India careers."""
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
            await page.goto(CAREER_URL, wait_until="networkidle", timeout=60000)

            # SELECTOR: job card containers
            selectors_to_try = [
                "div.cmp-teaser-card",
                "div[class*='JobCard']",
                "a[class*='job-card']",
                "div[class*='search-result']",
                "li[class*='job']",
                "article[class*='job']",
            ]

            cards_selector = None
            for sel in selectors_to_try:
                try:
                    await page.wait_for_selector(sel, timeout=10000)
                    cards_selector = sel
                    logger.info("Accenture: found cards with selector '%s'", sel)
                    break
                except Exception:
                    continue

            if not cards_selector:
                logger.warning("Accenture: no job card selector matched")
                await browser.close()
                return results

            # Scroll to load more results (Accenture uses lazy loading)
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(1000)

            cards = await page.query_selector_all(cards_selector)
            logger.info("Accenture: found %d job cards after scrolling", len(cards))

            for card in cards:
                try:
                    # SELECTOR: title
                    title_el = await card.query_selector(
                        "h3, a.cmp-teaser-card__title, [class*='job-title'], [class*='title']"
                    )
                    title = await title_el.inner_text() if title_el else await card.inner_text()
                    title = title.strip().split("\n")[0]

                    # SELECTOR: location
                    loc_el = await card.query_selector(
                        "span[class*='location'], [class*='city'], [class*='loc']"
                    )
                    location = (await loc_el.inner_text()).strip() if loc_el else ""

                    # SELECTOR: apply link
                    link_el = await card.query_selector("a[href]")
                    href = await link_el.get_attribute("href") if link_el else ""
                    if href and not href.startswith("http"):
                        from urllib.parse import urljoin
                        href = urljoin("https://www.accenture.com", href)

                    # SELECTOR: posted date
                    date_el = await card.query_selector(
                        "[class*='date'], span[class*='posted']"
                    )
                    posted = (await date_el.inner_text()).strip() if date_el else ""

                    # SELECTOR: skill / career level
                    level_el = await card.query_selector(
                        "[class*='level'], [class*='skill'], [class*='experience']"
                    )
                    level = (await level_el.inner_text()).strip() if level_el else ""

                    results.append({
                        "title": title,
                        "location": location,
                        "apply_link": href,
                        "posted_date": posted,
                        "level": level,
                    })
                except Exception as exc:
                    logger.debug("Accenture: failed to parse card: %s", exc)
                    continue

        except Exception as exc:
            logger.error("Accenture: Playwright error: %s", exc)
        finally:
            await browser.close()

    return results


def fetch_jobs() -> List[JobRecord]:
    """Fetch jobs from Accenture India careers portal."""
    import asyncio

    try:
        raw_jobs = asyncio.run(_scrape_with_playwright())
    except Exception as exc:
        logger.error("Accenture: scraping failed: %s", exc)
        raw_jobs = []

    if not raw_jobs:
        logger.warning("Accenture: no jobs scraped")
        return []

    records: List[JobRecord] = []
    for job in raw_jobs:
        # Combine level info into description for matching
        desc = f"Career Level: {job.get('level', '')}" if job.get("level") else ""

        records.append(
            JobRecord(
                title=job.get("title", ""),
                company=COMPANY_NAME,
                apply_link=job.get("apply_link", ""),
                location=job.get("location", ""),
                description=desc,
                posted_date=job.get("posted_date", ""),
                source="accenture_careers",
            )
        )

    logger.info("Accenture: scraped %d jobs total", len(records))
    return records

"""
Naukri.com public job search scraper.
Naukri is a Next.js SPA — the HTML shell is empty and all job cards are
rendered client-side. Requires Playwright.

RENDERING: Playwright required — React SPA behind CDN.

SELECTORS USED (update when layout changes):
  - URL pattern:  https://www.naukri.com/{keyword}-jobs-in-{location}
  - Job cards:    "div.srp-jobtuple-wrapper", "article.jobTuple"
  - Title:        "a.title", "h2 a", "[class*='jobTitle']"
  - Company:      "a.comp-name", "span.comp-name", "[class*='companyName']"
  - Location:     "span.loc-wrap span", "span.locWdth", "[class*='location']"
  - Experience:   "span.exp-wrap span", "[class*='experience']"
  - Salary:       "span.sal-wrap span", "[class*='salary']"
  - Apply link:   href of the title anchor (relative to naukri.com)
  - Posted date:  "span.job-post-day", "[class*='posted']"
"""

import logging
import re
from typing import List
from urllib.parse import quote_plus

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import config
from models import JobRecord

logger = logging.getLogger(__name__)

BASE_URL = "https://www.naukri.com"


def _build_search_url(keywords: List[str], location: str) -> str:
    """Build Naukri SEO-friendly search URL."""
    kw_slug = "-".join(w.lower().replace(".", "-") for w in " ".join(keywords).split())
    loc_slug = location.lower().strip().replace(" ", "-")
    return f"{BASE_URL}/{kw_slug}-jobs-in-{loc_slug}"


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

            # SELECTOR: wait for job tuple wrappers
            selectors_to_try = [
                "div.srp-jobtuple-wrapper",
                "article.jobTuple",
                "div[class*='jobTuple']",
                "div[class*='cust-job-tuple']",
                "div[data-job-id]",
            ]

            cards_sel = None
            for sel in selectors_to_try:
                try:
                    await page.wait_for_selector(sel, timeout=12000)
                    cards_sel = sel
                    logger.info("Naukri: matched selector '%s'", sel)
                    break
                except Exception:
                    continue

            if not cards_sel:
                logger.warning("Naukri: no job cards found at %s", url)
                await browser.close()
                return results

            # Scroll down to load more cards (Naukri lazy-loads)
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(1500)

            cards = await page.query_selector_all(cards_sel)
            logger.info("Naukri: found %d cards", len(cards))

            for card in cards:
                try:
                    # SELECTOR: title
                    title_el = await card.query_selector(
                        "a.title, h2 a, a[class*='title'], [class*='jobTitle'] a"
                    )
                    title = (await title_el.inner_text()).strip() if title_el else ""
                    href = (await title_el.get_attribute("href")) if title_el else ""
                    if href and not href.startswith("http"):
                        href = BASE_URL + href

                    # SELECTOR: company
                    comp_el = await card.query_selector(
                        "a.comp-name, span.comp-name, a[class*='companyName'], [class*='comp-name']"
                    )
                    company = (await comp_el.inner_text()).strip() if comp_el else ""

                    # SELECTOR: location
                    loc_el = await card.query_selector(
                        "span.loc-wrap span, span.locWdth, span[class*='location'], [class*='loc']"
                    )
                    location = (await loc_el.inner_text()).strip() if loc_el else ""

                    # SELECTOR: experience
                    exp_el = await card.query_selector(
                        "span.exp-wrap span, span[class*='experience'], [class*='expwdth']"
                    )
                    experience = (await exp_el.inner_text()).strip() if exp_el else ""

                    # SELECTOR: salary
                    sal_el = await card.query_selector(
                        "span.sal-wrap span, span[class*='salary'], [class*='sal']"
                    )
                    salary = (await sal_el.inner_text()).strip() if sal_el else ""

                    # SELECTOR: posted date
                    date_el = await card.query_selector(
                        "span.job-post-day, span[class*='posted'], [class*='freshness']"
                    )
                    posted = (await date_el.inner_text()).strip() if date_el else ""

                    # Build description from experience + salary
                    desc_parts = [p for p in [experience, salary] if p]
                    description = " | ".join(desc_parts)

                    results.append({
                        "title": title,
                        "company": company,
                        "location": location,
                        "apply_link": href,
                        "description": description,
                        "posted_date": posted,
                    })
                except Exception as exc:
                    logger.debug("Naukri: card parse error: %s", exc)
                    continue

        except Exception as exc:
            logger.error("Naukri: Playwright error: %s", exc)
        finally:
            await browser.close()

    return results


def fetch_jobs(keywords: List[str], location: str = "hyderabad") -> List[JobRecord]:
    """Fetch jobs from Naukri.com public search."""
    import asyncio

    url = _build_search_url(keywords, location)
    logger.info("Naukri: searching %s", url)

    try:
        raw = asyncio.run(_scrape_with_playwright(url))
    except Exception as exc:
        logger.error("Naukri: scraping failed: %s", exc)
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
            source="naukri",
        ))

    logger.info("Naukri: scraped %d jobs for '%s' in '%s'", len(records), " ".join(keywords), location)
    return records

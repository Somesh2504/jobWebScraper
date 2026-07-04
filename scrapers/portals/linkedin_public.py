"""
LinkedIn public job search scraper.
Public (logged-out) search results only. Extremely strict rate limits.
HIGHEST RISK / MOST FRAGILE MODULE.

Will use Playwright and standard LinkedIn public jobs route:
https://www.linkedin.com/jobs/search?keywords=X&location=Y
"""
import logging
from typing import List
from urllib.parse import quote_plus
import time

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import config
from models import JobRecord

logger = logging.getLogger(__name__)

BASE_URL = "https://www.linkedin.com"

async def _scrape_with_playwright(url: str) -> List[dict]:
    from playwright.async_api import async_playwright
    results: List[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=config.USER_AGENT,
            viewport={"width": 1280, "height": 900},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9"
            }
        )
        page = await context.new_page()

        try:
            logger.info("LinkedIn: Navigating to %s", url)
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Wait to avoid immediate bot block
            await page.wait_for_timeout(3000)

            cards_sel = "ul.jobs-search__results-list > li"
            try:
                await page.wait_for_selector(cards_sel, timeout=12000)
            except Exception:
                logger.warning("LinkedIn: no job cards found. May be blocked.")
                await browser.close()
                return results

            # Scroll a few times to load more
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)

            cards = await page.query_selector_all(cards_sel)
            logger.info("LinkedIn: found %d cards", len(cards))

            for card in cards:
                try:
                    title_el = await card.query_selector("h3.base-search-card__title")
                    title = (await title_el.inner_text()).strip() if title_el else ""
                    
                    comp_el = await card.query_selector("h4.base-search-card__subtitle")
                    company = (await comp_el.inner_text()).strip() if comp_el else ""
                    
                    loc_el = await card.query_selector("span.job-search-card__location")
                    loc = (await loc_el.inner_text()).strip() if loc_el else ""
                    
                    link_el = await card.query_selector("a.base-card__full-link")
                    href = (await link_el.get_attribute("href")) if link_el else ""
                    
                    date_el = await card.query_selector("time.job-search-card__listdate")
                    posted = (await date_el.inner_text()).strip() if date_el else ""

                    results.append({
                        "title": title,
                        "company": company,
                        "location": loc,
                        "apply_link": href,
                        "posted_date": posted,
                        "description": "",
                    })
                except Exception as exc:
                    logger.debug("LinkedIn: parse error %s", exc)
                    continue

        except Exception as exc:
            logger.error("LinkedIn: Playwright error %s", exc)
        finally:
            await browser.close()

    return results

def fetch_jobs(keywords: List[str], location: str = "") -> List[JobRecord]:
    import asyncio
    
    kw_slug = quote_plus(" ".join(keywords))
    loc_slug = quote_plus(location) if location else "India"
    
    url = f"{BASE_URL}/jobs/search?keywords={kw_slug}&location={loc_slug}"
    
    try:
        raw = asyncio.run(_scrape_with_playwright(url))
    except Exception as exc:
        logger.error("LinkedIn: async run failed %s", exc)
        raw = []
        
    records = []
    for r in raw:
        records.append(JobRecord(
            title=r.get("title", ""),
            company=r.get("company", ""),
            apply_link=r.get("apply_link", ""),
            location=r.get("location", ""),
            posted_date=r.get("posted_date", ""),
            source="linkedin"
        ))
        
    logger.info("LinkedIn: fetched %d jobs", len(records))
    return records

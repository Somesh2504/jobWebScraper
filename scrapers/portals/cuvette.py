"""
Cuvette public job search scraper.
Playwright required.
"""
import logging
from typing import List
from urllib.parse import quote_plus

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import config
from models import JobRecord

logger = logging.getLogger(__name__)

BASE_URL = "https://cuvette.tech"

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

            # Wait for job cards
            cards_sel = "div[class*='jobCard'], div[class*='job-card']"
            try:
                await page.wait_for_selector(cards_sel, timeout=12000)
            except Exception:
                logger.warning("Cuvette: no job cards found")
                await browser.close()
                return results

            cards = await page.query_selector_all(cards_sel)
            
            for card in cards:
                try:
                    title_el = await card.query_selector("h3, h2, [class*='title']")
                    title = (await title_el.inner_text()).strip() if title_el else ""
                    
                    comp_el = await card.query_selector("h4, [class*='company']")
                    company = (await comp_el.inner_text()).strip() if comp_el else ""
                    
                    # Try to find a link
                    link_el = await card.query_selector("a")
                    href = (await link_el.get_attribute("href")) if link_el else ""
                    if href and not href.startswith("http"):
                        href = BASE_URL + href
                        
                    results.append({
                        "title": title,
                        "company": company,
                        "location": "",
                        "apply_link": href,
                        "description": "",
                    })
                except Exception as exc:
                    logger.debug("Cuvette: parse error %s", exc)
                    continue

        except Exception as exc:
            logger.error("Cuvette: Playwright error %s", exc)
        finally:
            await browser.close()

    return results

def fetch_jobs(keywords: List[str], location: str = "") -> List[JobRecord]:
    import asyncio
    
    url = f"{BASE_URL}/app/student/jobs"
    
    try:
        raw = asyncio.run(_scrape_with_playwright(url))
    except Exception as exc:
        logger.error("Cuvette: async run failed %s", exc)
        raw = []
        
    records = []
    for r in raw:
        # Client side filter because cuvette url doesn't take standard search queries simply
        title = r.get("title", "")
        # Very loose filter
        if any(kw.lower() in title.lower() for kw in keywords):
            records.append(JobRecord(
                title=title,
                company=r.get("company", ""),
                apply_link=r.get("apply_link", ""),
                location=r.get("location", ""),
                description=r.get("description", ""),
                source="cuvette"
            ))
            
    return records

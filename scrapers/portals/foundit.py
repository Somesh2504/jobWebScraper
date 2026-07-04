"""
Foundit (formerly Monster) public job search scraper.
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

BASE_URL = "https://www.foundit.in"

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

            cards_sel = "div.card-apply-content, div.srpResultCard"
            try:
                await page.wait_for_selector(cards_sel, timeout=12000)
            except Exception:
                logger.warning("Foundit: no job cards found")
                await browser.close()
                return results

            cards = await page.query_selector_all(cards_sel)
            
            for card in cards:
                try:
                    title_el = await card.query_selector("h3, .jobTitle")
                    title = (await title_el.inner_text()).strip() if title_el else ""
                    
                    link_el = await card.query_selector("h3 a, a.jobTitle")
                    href = (await link_el.get_attribute("href")) if link_el else ""
                    if href and not href.startswith("http"):
                        href = BASE_URL + href
                        
                    comp_el = await card.query_selector("div.companyName, .company-name")
                    company = (await comp_el.inner_text()).strip() if comp_el else ""
                    
                    loc_el = await card.query_selector("div.details-container, .loc")
                    loc = (await loc_el.inner_text()).strip() if loc_el else ""
                    
                    results.append({
                        "title": title,
                        "company": company,
                        "location": loc,
                        "apply_link": href,
                        "description": "",
                    })
                except Exception as exc:
                    logger.debug("Foundit: parse error %s", exc)
                    continue

        except Exception as exc:
            logger.error("Foundit: Playwright error %s", exc)
        finally:
            await browser.close()

    return results

def fetch_jobs(keywords: List[str], location: str = "") -> List[JobRecord]:
    import asyncio
    kw_slug = "-".join(keywords).lower()
    loc_slug = location.lower().replace(" ", "-") if location else "india"
    url = f"{BASE_URL}/srp/results?query={quote_plus(' '.join(keywords))}&locations={quote_plus(location)}"
    
    try:
        raw = asyncio.run(_scrape_with_playwright(url))
    except Exception as exc:
        logger.error("Foundit: async run failed %s", exc)
        raw = []
        
    records = []
    for r in raw:
        records.append(JobRecord(
            title=r.get("title", ""),
            company=r.get("company", ""),
            apply_link=r.get("apply_link", ""),
            location=r.get("location", ""),
            description=r.get("description", ""),
            source="foundit"
        ))
    return records

"""
Internshala public job search scraper.
Server-rendered HTML, uses requests and BeautifulSoup.
"""
import logging
from typing import List
from urllib.parse import quote_plus
import requests
from bs4 import BeautifulSoup

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import config
from models import JobRecord

logger = logging.getLogger(__name__)

BASE_URL = "https://internshala.com"

def fetch_jobs(keywords: List[str], location: str = "") -> List[JobRecord]:
    # Internshala URL structure usually: /jobs/keyword-jobs-in-location
    kw_slug = "-".join(w.lower().replace(".", "-") for w in " ".join(keywords).split())
    loc_slug = location.lower().strip().replace(" ", "-") if location else "india"
    
    url = f"{BASE_URL}/jobs/{kw_slug}-jobs-in-{loc_slug}"
    logger.info("Internshala: searching %s", url)

    headers = {"User-Agent": config.USER_AGENT}
    try:
        r = requests.get(url, headers=headers, timeout=config.REQUEST_TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as exc:
        logger.error("Internshala: request failed: %s", exc)
        return []

    records = []
    cards = soup.find_all("div", class_="container-fluid individual_internship")
    
    for card in cards:
        try:
            title_el = card.find("h3", class_="heading_4_5 profile")
            title = title_el.get_text(strip=True) if title_el else ""
            
            comp_el = card.find("div", class_="heading_6 company_name")
            company = comp_el.get_text(strip=True) if comp_el else ""
            
            loc_el = card.find("a", class_="location_link")
            loc = loc_el.get_text(strip=True) if loc_el else ""
            
            link_el = card.get("data-href")
            link = BASE_URL + link_el if link_el else ""
            
            # Additional details (stipend, duration, etc.)
            details = card.find_all("div", class_="item_body")
            desc = " | ".join(d.get_text(strip=True) for d in details) if details else ""
            
            records.append(JobRecord(
                title=title,
                company=company,
                apply_link=link,
                location=loc,
                description=desc,
                source="internshala"
            ))
        except Exception as exc:
            logger.debug("Internshala: card parse error %s", exc)
            continue
            
    logger.info("Internshala: fetched %d jobs", len(records))
    return records

"""
GeeksForGeeks Jobs scraper.
Uses public JSON API.
"""
import logging
from typing import List
import requests

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import config
from models import JobRecord

logger = logging.getLogger(__name__)

def fetch_jobs(keywords: List[str], location: str = "") -> List[JobRecord]:
    url = "https://practiceapi.geeksforgeeks.org/api/latest/jobs/"
    params = {
        "search": " ".join(keywords)
    }
    
    headers = {"User-Agent": config.USER_AGENT}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=config.REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json().get("results", [])
    except Exception as exc:
        logger.error("GFG Jobs: API request failed: %s", exc)
        return []

    records = []
    for item in data:
        title = item.get("title", item.get("role", ""))
        company = item.get("company_name", item.get("organization", ""))
        slug = item.get("slug", "")
        link = item.get("apply_link", f"https://www.geeksforgeeks.org/jobs/{slug}" if slug else "")
        loc = item.get("location", "")
        desc = item.get("description", "")
        
        records.append(JobRecord(
            title=title,
            company=company,
            apply_link=link,
            location=loc,
            description=desc,
            source="gfg_jobs"
        ))

    logger.info("GFG Jobs: fetched %d jobs", len(records))
    return records

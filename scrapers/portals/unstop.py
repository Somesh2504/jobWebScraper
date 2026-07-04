"""
Unstop public job scraper.
Uses the public JSON API endpoint.
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
    url = "https://unstop.com/api/public/opportunity/search-result"
    params = {
        "opportunity": "jobs",
        "keyword": " ".join(keywords)
    }
    
    headers = {
        "User-Agent": config.USER_AGENT
    }

    try:
        r = requests.get(url, params=params, headers=headers, timeout=config.REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json().get("data", {}).get("data", [])
    except Exception as exc:
        logger.error("Unstop: API request failed: %s", exc)
        return []

    records = []
    for item in data:
        # Check location manually since API might not filter perfectly
        item_loc = item.get("region", "")
        if location and location.lower() not in item_loc.lower():
            # If target location doesn't match and location filter is strict, skip or keep it
            pass
            
        title = item.get("title", "")
        company = item.get("organisation", {}).get("name", "") if isinstance(item.get("organisation"), dict) else item.get("organisation", "")
        if not company:
             company = "Unknown"
        seo_url = item.get("seo_url", "")
        link = f"https://unstop.com/{seo_url}" if seo_url else ""
        
        desc = ", ".join(item.get("required_skills", []))
        
        records.append(JobRecord(
            title=title,
            company=company,
            apply_link=link,
            location=item_loc,
            description=desc,
            source="unstop"
        ))

    logger.info("Unstop: fetched %d jobs", len(records))
    return records

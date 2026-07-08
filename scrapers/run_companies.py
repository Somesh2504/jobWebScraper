"""
Company portal runner — scrapes individual career portals that don't use
standard ATS platforms, filters for India-based entry-level roles,
and inserts into storage.

Usage:
    python -m scrapers.run_companies          # from project root
    python scrapers/run_companies.py          # direct invocation
"""

import logging
import sys
import time
import importlib
from pathlib import Path
from typing import List, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from models import JobRecord
from storage.storage import insert_job_if_new

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run_companies")

# ── Registry: maps company key -> module path ──
# Each module must expose a fetch_jobs() -> List[JobRecord] function.
COMPANY_SCRAPERS: dict[str, str] = {
    "TCS":        "scrapers.companies.tcs",
    "Infosys":    "scrapers.companies.infosys",
    "Wipro":      "scrapers.companies.wipro",
    "Accenture":  "scrapers.companies.accenture",
    "Cognizant":  "scrapers.companies.cognizant",
}

RATE_LIMIT_DELAY = 1.0  # seconds between companies (higher for portal scraping)


def _is_blocked_location(job: JobRecord) -> bool:
    """Return True if the job is from a blocked foreign location."""
    loc = job.location.lower().strip()
    if not loc:
        return False
    blocked = getattr(config, "BLOCKED_LOCATIONS", [])
    for bl in blocked:
        if bl in loc:
            return True
    if "remote" in loc and "india" not in loc:
        has_india = any(t in loc for t in config.TARGET_LOCATIONS)
        if not has_india:
            return True
    return False


def _is_blocked_title(job: JobRecord) -> bool:
    """Return True if the job title indicates a senior/lead role."""
    title = job.title.lower().strip()
    blocked = getattr(config, "BLOCKED_TITLE_KEYWORDS", [])
    for bt in blocked:
        if bt in title:
            return True
    return False


def _matches_india_location(job: JobRecord) -> bool:
    """Return True if the job location matches any target location."""
    loc = job.location.lower().strip()
    if not loc:
        # For company portals that are already India-specific (like TCS iBegin),
        # an empty location still counts as India.
        return True
    for target in config.TARGET_LOCATIONS:
        if target in loc:
            return True
    return False


def _matches_entry_level(job: JobRecord) -> bool:
    """Return True if the job title or description hints at entry-level."""
    text = f"{job.title} {job.description}".lower()
    for kw in config.ENTRY_LEVEL_KEYWORDS:
        if kw in text:
            return True
    return False


def run() -> dict:
    """
    Execute the company-portal scrape-filter-store pipeline.

    Returns:
        Summary dict with counts per company.
    """
    summary: dict[str, dict] = {}

    for name, module_path in COMPANY_SCRAPERS.items():
        logger.info("─── Scraping: %s ───", name)

        try:
            adapter = importlib.import_module(module_path)
            fetch_fn: Callable[[], List[JobRecord]] = getattr(adapter, "fetch_jobs")

            raw_jobs = fetch_fn()
            logger.info("  ↳ Raw jobs fetched: %d", len(raw_jobs))

            # Filter 1: reject blocked foreign locations and senior titles
            safe_jobs = [j for j in raw_jobs if not _is_blocked_location(j) and not _is_blocked_title(j)]
            logger.info("  ↳ After blocklist filter: %d", len(safe_jobs))

            # Filter 2: India locations
            india_jobs = [j for j in safe_jobs if _matches_india_location(j)]
            logger.info("  ↳ After location filter: %d", len(india_jobs))

            # Filter 3: entry-level (strict — no fallback)
            entry_jobs = [j for j in india_jobs if _matches_entry_level(j)]
            logger.info("  ↳ After entry-level filter: %d", len(entry_jobs))

            # Only insert entry-level jobs — no fallback to all-India
            new_count = 0
            dup_count = 0
            for job in entry_jobs:
                if insert_job_if_new(job):
                    new_count += 1
                else:
                    dup_count += 1

            logger.info(
                "  ↳ Inserted: %d new, %d duplicates  [filter: entry-level only]",
                new_count, dup_count,
            )

            summary[name] = {
                "status": "ok",
                "raw": len(raw_jobs),
                "blocked": len(raw_jobs) - len(safe_jobs),
                "india": len(india_jobs),
                "entry_level": len(entry_jobs),
                "new": new_count,
                "duplicates": dup_count,
            }

        except Exception as exc:
            logger.error("  ✗ FAILED for '%s': %s", name, exc, exc_info=True)
            summary[name] = {"status": "error", "error": str(exc)}

        time.sleep(RATE_LIMIT_DELAY)

    # Final summary
    total_new = sum(s.get("new", 0) for s in summary.values())
    total_errors = sum(1 for s in summary.values() if s.get("status") == "error")
    logger.info("═══════════════════════════════════════════")
    logger.info("  DONE — %d new jobs stored, %d company errors", total_new, total_errors)
    logger.info("═══════════════════════════════════════════")

    return summary


if __name__ == "__main__":
    run()

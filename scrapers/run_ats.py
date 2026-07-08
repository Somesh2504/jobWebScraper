"""
ATS runner — loops through companies_config.yaml, calls the right adapter,
filters for India-based / remote roles and entry-level titles, and inserts
matching jobs into storage.

Usage:
    python -m scrapers.run_ats          # from project root
    python scrapers/run_ats.py          # direct invocation
"""

import logging
import sys
import os
import time
import importlib
from pathlib import Path
from typing import List

import yaml

# ── Project root on sys.path ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from models import JobRecord
from storage.storage import insert_job_if_new

# ── Logging setup ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run_ats")

# ── ATS adapter registry ──
# Maps the YAML 'ats' field to (module_path, fetch_function_name)
ATS_ADAPTERS = {
    "greenhouse":      "scrapers.ats.greenhouse",
    "lever":           "scrapers.ats.lever",
    "smartrecruiters": "scrapers.ats.smartrecruiters",
}

RATE_LIMIT_DELAY = 0.5  # seconds between API calls


# ─────────────────────────────────────────────
# Filtering helpers
# ─────────────────────────────────────────────

def _is_blocked_location(job: JobRecord) -> bool:
    """Return True if the job is from a blocked foreign location."""
    loc = job.location.lower().strip()
    if not loc:
        return False
    blocked = getattr(config, "BLOCKED_LOCATIONS", [])
    for bl in blocked:
        if bl in loc:
            return True
    # Catch generic 'remote' without India context
    if "remote" in loc and "india" not in loc:
        has_india = any(t in loc for t in config.TARGET_LOCATIONS)
        if not has_india:
            return True
    return False


def _is_blocked_title(job: JobRecord) -> bool:
    """Return True if the job title indicates a senior/lead role."""
    title = job.title.lower().strip()
    blocked = getattr(config, "GLOBAL_DENYLIST", [])
    for bt in blocked:
        if bt in title:
            return True
    return False


def _matches_india_location(job: JobRecord) -> bool:
    """Return True if the job location matches any target location."""
    loc = job.location.lower().strip()
    if not loc:
        return False  # unknown location — skip rather than spam
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


def _load_companies_config() -> list[dict]:
    """Load and validate companies_config.yaml."""
    yaml_path = Path(__file__).resolve().parent / "companies_config.yaml"
    if not yaml_path.exists():
        logger.error("companies_config.yaml not found at %s", yaml_path)
        return []

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    companies = data.get("companies", [])
    if not companies:
        logger.warning("No companies found in companies_config.yaml")
    return companies


# ─────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────

def run() -> dict:
    """
    Execute the full ATS scrape-filter-store pipeline.

    Returns:
        Summary dict with counts per company.
    """
    companies = _load_companies_config()
    summary: dict[str, dict] = {}

    for entry in companies:
        name = entry.get("name", "unknown")
        ats = entry.get("ats", "").lower()
        token = entry.get("token", "")

        if not token:
            logger.warning("Skipping '%s': no token configured", name)
            summary[name] = {"status": "skipped", "reason": "no token"}
            continue

        adapter_module_path = ATS_ADAPTERS.get(ats)
        if not adapter_module_path:
            logger.warning("Skipping '%s': unknown ATS platform '%s'", name, ats)
            summary[name] = {"status": "skipped", "reason": f"unknown ATS: {ats}"}
            continue

        logger.info("─── Scraping: %s  [%s / %s] ───", name, ats, token)

        try:
            # Dynamically import the adapter
            adapter = importlib.import_module(adapter_module_path)
            fetch_fn = getattr(adapter, "fetch_jobs")

            raw_jobs: List[JobRecord] = fetch_fn(token, company_name=name)
            logger.info("  ↳ Raw jobs fetched: %d", len(raw_jobs))

            # Filter 1: reject blocked foreign locations and senior titles
            safe_jobs = [j for j in raw_jobs if not _is_blocked_location(j) and not _is_blocked_title(j)]
            logger.info("  ↳ After blocklist filter: %d", len(safe_jobs))

            # Filter 2: India-based / remote locations
            india_jobs = [j for j in safe_jobs if _matches_india_location(j)]
            logger.info("  ↳ After location filter (India): %d", len(india_jobs))

            # Filter 3: entry-level titles (strict — no fallback)
            entry_level_jobs = [j for j in india_jobs if _matches_entry_level(j)]
            logger.info("  ↳ After entry-level filter: %d", len(entry_level_jobs))

            # Only insert entry-level jobs — no fallback to all-India
            new_count = 0
            dup_count = 0
            for job in entry_level_jobs:
                is_new = insert_job_if_new(job)
                if is_new:
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
                "entry_level": len(entry_level_jobs),
                "new": new_count,
                "duplicates": dup_count,
            }

        except Exception as exc:
            logger.error("  ✗ FAILED for '%s': %s", name, exc, exc_info=True)
            summary[name] = {"status": "error", "error": str(exc)}

        # Rate-limit between companies
        time.sleep(RATE_LIMIT_DELAY)

    # ── Final summary ──
    total_new = sum(s.get("new", 0) for s in summary.values())
    total_errors = sum(1 for s in summary.values() if s.get("status") == "error")
    logger.info("═══════════════════════════════════════════")
    logger.info("  DONE — %d new jobs stored, %d company errors", total_new, total_errors)
    logger.info("═══════════════════════════════════════════")

    return summary


if __name__ == "__main__":
    run()

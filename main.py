"""
main.py — Full pipeline orchestrator.

Modes (controlled via DIGEST env var or --digest / --urgent-only CLI flag):

  DIGEST=true   (default for scheduled-scrape.yml)
    1. Scrape  →  ATS + Companies + Portals
    2. Dedup / store  (handled inside each runner)
    3. Score all unalerted jobs
    4. Check urgency  →  send_urgent_alert() immediately for each
    5. Build digest of top 8-10 unalerted jobs  →  send_digest()
    6. Mark everything as alerted

  DIGEST=false  /  --urgent-only  (for urgent-check.yml)
    1. Skip scraping (jobs already in DB)
    2. Re-scan ALL stored jobs for urgency
    3. Send urgent alerts for any newly-urgent, un-alerted jobs
    4. Do NOT send a digest
    5. Mark only the alerted urgent jobs

Usage:
    python main.py                      # defaults to DIGEST=true
    python main.py --digest             # explicit digest mode
    python main.py --urgent-only        # urgent re-check only
    DIGEST=false python main.py         # env-var driven

Secrets are read from .env (local) or GitHub Actions secrets (CI).
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

# ── Project root on sys.path ──
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from models import JobRecord
from storage.storage import (
    get_unalerted_jobs,
    get_all_stored_jobs,
    get_job_hash,
    get_stats,
    mark_alerted,
)
from matching.scorer import score_job, rank_jobs
from matching.urgency import is_urgent
from notifier.telegram_bot import send_digest, send_no_new_matches_status, send_urgent_alert

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


# ═══════════════════════════════════════════════
#  PHASE 1 — SCRAPE
# ═══════════════════════════════════════════════
def run_scrapers(include_linkedin: bool = False) -> None:
    """Run all three scraper tracks sequentially.

    Each runner script handles its own error handling per-source,
    so a single portal failing won't crash the pipeline.
    """
    scrapers = [
        ("ATS scrapers", [sys.executable, str(PROJECT_ROOT / "scrapers" / "run_ats.py")]),
        ("Company scrapers", [sys.executable, str(PROJECT_ROOT / "scrapers" / "run_companies.py")]),
    ]

    portal_cmd = [sys.executable, str(PROJECT_ROOT / "scrapers" / "run_portals.py")]
    if include_linkedin:
        portal_cmd.append("--reduced-frequency")
    scrapers.append(("Portal scrapers", portal_cmd))

    for label, cmd in scrapers:
        logger.info("─── Starting %s ───", label)
        try:
            result = subprocess.run(
                cmd,
                cwd=str(PROJECT_ROOT),
                timeout=600,           # 10 min max per track
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.info("%s finished OK.", label)
            else:
                logger.warning(
                    "%s exited with code %d.\nstderr: %s",
                    label, result.returncode, result.stderr[-500:] if result.stderr else "(empty)",
                )
        except subprocess.TimeoutExpired:
            logger.error("%s timed out after 600 s — skipping.", label)
        except Exception as exc:
            logger.error("%s failed to launch: %s", label, exc)


# ═══════════════════════════════════════════════
#  PHASE 2 — SCORE + URGENCY + NOTIFY
# ═══════════════════════════════════════════════
def _determine_slot_label() -> str:
    """Pick a human-readable label based on the current IST hour."""
    ist_hour = (datetime.now(timezone.utc).hour + 5) % 24  # rough IST
    if ist_hour < 10:
        return "Morning Scan ☀️"
    elif ist_hour < 14:
        return "Midday Update 🌤️"
    elif ist_hour < 18:
        return "Afternoon Roundup 🌇"
    else:
        return "Evening Digest 🌙"


def process_digest() -> None:
    """Full digest mode: score → urgent alerts → digest → mark alerted."""
    stats_before = get_stats()
    logger.info("DB stats: %s", stats_before)

    jobs = get_unalerted_jobs()
    if not jobs:
        logger.info("No unalerted jobs in DB. Nothing to process.")
        if not send_no_new_matches_status(
            total_jobs=stats_before["total"],
            alerted_jobs=stats_before["alerted"],
        ):
            logger.error("Could not send no-new-matches Telegram status.")
        return

    logger.info("Scoring %d unalerted jobs…", len(jobs))

    # ── Score every job ──
    for job in jobs:
        job._score = score_job(job)  # type: ignore[attr-defined]

    # ── Separate urgent from normal ──
    urgent: List[JobRecord] = []
    normal: List[JobRecord] = []
    for job in jobs:
        if is_urgent(job):
            urgent.append(job)
        else:
            normal.append(job)

    logger.info("Urgent: %d  |  Normal: %d", len(urgent), len(normal))

    # ── Immediate urgent alerts ──
    alerted_hashes: set = set()
    for job in urgent:
        score = getattr(job, '_score', 0.0)
        if score < 10:
            logger.debug("Skipping low-score urgent job: %.1f '%s'", score, job.title)
            continue
        if send_urgent_alert(job):
            h = get_job_hash(job)
            mark_alerted(h)
            alerted_hashes.add(h)
            time.sleep(1)  # avoid Telegram rate limit (30 msg/s per bot)

    # ── Build digest from top unalerted jobs ──
    # Exclude already-alerted urgent jobs
    digest_candidates = [
        j for j in jobs
        if get_job_hash(j) not in alerted_hashes
        and getattr(j, '_score', 0) >= config.MIN_MATCH_SCORE * 100
    ]
    digest_candidates.sort(key=lambda j: getattr(j, '_score', 0), reverse=True)
    digest_top = digest_candidates[:10]

    digest_success = True
    if digest_top:
        slot_label = _determine_slot_label()
        logger.info("Sending digest '%s' with %d jobs.", slot_label, len(digest_top))
        digest_success = send_digest(digest_top, slot_label=slot_label)
    else:
        logger.info("No jobs above threshold for digest.")

    # ── Mark ALL unalerted jobs as processed ──
    for job in jobs:
        h = get_job_hash(job)
        if h not in alerted_hashes:
            # If sending digest failed, don't mark the top jobs as alerted so we retry next time
            if job in digest_top and not digest_success:
                continue
            mark_alerted(h)

    stats_after = get_stats()
    logger.info("Done. DB stats: %s", stats_after)


def process_urgent_only() -> None:
    """Urgent-only mode: re-scan stored un-alerted jobs for urgency."""
    jobs = get_unalerted_jobs()
    if not jobs:
        logger.info("No unalerted jobs to re-check for urgency.")
        return

    logger.info("Re-checking %d unalerted jobs for urgency…", len(jobs))

    urgent_count = 0
    for job in jobs:
        if is_urgent(job):
            job._score = score_job(job)  # type: ignore[attr-defined]
            score = getattr(job, '_score', 0.0)
            if score < 10:
                continue
            if send_urgent_alert(job):
                mark_alerted(get_job_hash(job))
                urgent_count += 1
                time.sleep(1)

    logger.info("Urgent re-check done. Sent %d alerts.", urgent_count)


# ═══════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════
def main() -> None:
    parser = argparse.ArgumentParser(description="Job Search Automation Pipeline")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--digest", action="store_true", default=None,
        help="Run full pipeline: scrape + score + digest (default)",
    )
    mode.add_argument(
        "--urgent-only", action="store_true", default=False,
        help="Skip scraping; re-check stored jobs for urgency only",
    )
    parser.add_argument(
        "--include-linkedin", action="store_true", default=False,
        help="Include LinkedIn scraper (high-risk, use sparingly)",
    )
    args = parser.parse_args()

    # Env var DIGEST overrides if no CLI flag given
    if args.digest is None and not args.urgent_only:
        env_digest = os.environ.get("DIGEST", "true").strip().lower()
        is_digest = env_digest in ("true", "1", "yes")
    elif args.urgent_only:
        is_digest = False
    else:
        is_digest = True

    start = time.time()
    logger.info(
        "═══ Job Search Pipeline — mode=%s ═══",
        "DIGEST" if is_digest else "URGENT-ONLY",
    )

    if is_digest:
        # Phase 1: Scrape
        run_scrapers(include_linkedin=args.include_linkedin)
        # Phase 2: Score + notify
        process_digest()
    else:
        # Urgent-only mode (no scraping)
        process_urgent_only()

    elapsed = time.time() - start
    logger.info("═══ Pipeline finished in %.1f s ═══", elapsed)


if __name__ == "__main__":
    main()

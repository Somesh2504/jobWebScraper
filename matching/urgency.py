"""
matching/urgency.py — Urgency detector for job postings.

Detects whether a job posting signals urgency using regex patterns.
If a date appears near "last date" / "apply by", it is parsed and
flagged urgent only if the deadline is within 3 days.

Public API:
    is_urgent(job: JobRecord) -> bool
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import JobRecord

logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────
# Instant-urgency patterns  (any match → immediately urgent)
# ───────────────────────────────────────────────────────
_INSTANT_URGENT_PATTERNS = [
    re.compile(r'\bimmediate\s+join(?:er|ing)\b', re.IGNORECASE),
    re.compile(r'\bimmediate\s+requirement\b', re.IGNORECASE),
    re.compile(r'\burgent\s+(?:hiring|requirement|opening|vacancy)\b', re.IGNORECASE),
    re.compile(r'\bwalk[\s-]?in\b', re.IGNORECASE),
    re.compile(r'\bspot\s+offer\b', re.IGNORECASE),
    re.compile(r'\bhiring\s+now\b', re.IGNORECASE),
    re.compile(r'\basap\b', re.IGNORECASE),
]

# ───────────────────────────────────────────────────────
# Date-dependent urgency patterns
# "last date to apply: 5 Jul 2026"
# "apply by July 7, 2026"
# "apply before 07/07/2026"
# ───────────────────────────────────────────────────────
_DATE_TRIGGER_PATTERN = re.compile(
    r'(?:last\s+date(?:\s+to\s+apply)?|apply\s+by|apply\s+before|deadline|closing\s+date)'
    r'\s*[:;\-–—]?\s*'
    r'(\d{1,2}[\s/\-]\w{3,9}[\s/\-]\d{2,4}'  # "5 Jul 2026", "07/Jul/2026"
    r'|'
    r'\w{3,9}\s+\d{1,2},?\s+\d{2,4}'           # "July 5, 2026"
    r'|'
    r'\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}'         # "07/05/2026", "7-5-26"
    r'|'
    r'\d{4}[/\-]\d{1,2}[/\-]\d{1,2}'           # "2026-07-05"
    r')',
    re.IGNORECASE,
)

# Supported date formats for parsing
_DATE_FORMATS = [
    "%d %b %Y",       # 5 Jul 2026
    "%d %B %Y",       # 5 July 2026
    "%d-%b-%Y",       # 05-Jul-2026
    "%d/%b/%Y",       # 05/Jul/2026
    "%B %d, %Y",      # July 5, 2026
    "%B %d %Y",       # July 5 2026
    "%b %d, %Y",      # Jul 5, 2026
    "%b %d %Y",       # Jul 5 2026
    "%d/%m/%Y",       # 05/07/2026
    "%m/%d/%Y",       # 07/05/2026
    "%d-%m-%Y",       # 05-07-2026
    "%Y-%m-%d",       # 2026-07-05
    "%Y/%m/%d",       # 2026/07/05
    "%d %b %y",       # 5 Jul 26
    "%d/%m/%y",       # 05/07/26
]

URGENCY_WINDOW_DAYS = 3


def _try_parse_date(date_str: str) -> Optional[datetime]:
    """Try to parse a date string using multiple formats."""
    date_str = date_str.strip().rstrip(".")
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Handle 2-digit years
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            return dt
        except ValueError:
            continue
    return None


def _check_date_urgency(text: str) -> bool:
    """
    Search for date-dependent urgency triggers.
    Returns True if a deadline date is found and it's within URGENCY_WINDOW_DAYS.
    """
    match = _DATE_TRIGGER_PATTERN.search(text)
    if not match:
        return False

    date_str = match.group(1)
    deadline = _try_parse_date(date_str)

    if deadline is None:
        logger.debug("Urgency: found trigger but couldn't parse date '%s'", date_str)
        # Can't parse → be conservative, don't flag as urgent
        return False

    now = datetime.now()
    delta = deadline - now

    if timedelta(0) <= delta <= timedelta(days=URGENCY_WINDOW_DAYS):
        logger.debug(
            "Urgency: deadline '%s' is %.1f days away → URGENT",
            date_str, delta.total_seconds() / 86400,
        )
        return True

    if delta < timedelta(0):
        # Deadline already passed
        logger.debug("Urgency: deadline '%s' already passed", date_str)
        return False

    logger.debug(
        "Urgency: deadline '%s' is %.1f days away (> %d) → not urgent",
        date_str, delta.total_seconds() / 86400, URGENCY_WINDOW_DAYS,
    )
    return False


def is_urgent(job: JobRecord) -> bool:
    """
    Determine if a job posting signals urgency.

    A job is urgent if:
      1. Any instant-urgency keyword is found in the title or description, OR
      2. A deadline date is found near "last date" / "apply by" and
         the deadline is within 3 days from now.

    Args:
        job: A JobRecord to evaluate.

    Returns:
        True if the job is urgent.
    """
    text = f"{job.title} {job.description} {job.posted_date}".strip()
    if not text:
        return False

    # Check instant-urgency patterns first (fast path)
    for pattern in _INSTANT_URGENT_PATTERNS:
        if pattern.search(text):
            logger.debug(
                "Urgency: instant match '%s' in '%s' @ %s",
                pattern.pattern, job.title, job.company,
            )
            return True

    # Check date-dependent urgency
    if _check_date_urgency(text):
        return True

    return False

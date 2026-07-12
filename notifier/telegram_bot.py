"""
notifier/telegram_bot.py — Telegram Bot API integration.

Sends formatted job alerts via the Telegram Bot API using raw HTTP
requests to api.telegram.org (zero extra dependencies beyond requests).

Public API:
    send_urgent_alert(job: JobRecord)  → send a single urgent-job message
    send_digest(jobs: List[JobRecord], slot_label: str) → send a digest of top jobs

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from environment / config.py.
"""

import logging
import textwrap
from datetime import datetime, timezone
from typing import List, Optional

import requests

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
from models import JobRecord

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Telegram MarkdownV2 escaping
# ──────────────────────────────────────────────
_ESCAPE_CHARS = r'_*[]()~`>#+-=|{}.!'


def _esc(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2.

    Every character in _ESCAPE_CHARS must be preceded by a backslash
    for Telegram to render the message correctly.
    """
    out = str(text)
    for ch in _ESCAPE_CHARS:
        out = out.replace(ch, f'\\{ch}')
    return out


def _esc_url(url: str) -> str:
    """Escape only the parentheses inside a MarkdownV2 inline-link URL.

    Telegram requires () to be escaped inside the URL portion of
    [text](url), but everything else can stay raw.
    """
    return url.replace('(', '\\(').replace(')', '\\)')


# ──────────────────────────────────────────────
# Low-level send
# ──────────────────────────────────────────────
def _send_message(text: str, parse_mode: str = "MarkdownV2") -> bool:
    """POST a message to the configured Telegram chat.

    Returns True on success, False on failure (logged, never raises).
    """
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        logger.warning(
            "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping send."
        )
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        try:
            data = resp.json()
        except ValueError:
            logger.error(
                "Telegram returned a non-JSON response (HTTP %s): %s",
                resp.status_code,
                resp.text[:500],
            )
            return False
        if data.get("ok"):
            logger.info("Telegram message sent (chat_id=%s).", chat_id)
            return True
        else:
            logger.error(
                "Telegram API error: %s (error_code=%s)",
                data.get("description", "unknown"),
                data.get("error_code", "?"),
            )
            return False
    except requests.RequestException as exc:
        logger.error("Telegram HTTP error: %s", exc)
        return False


# ──────────────────────────────────────────────
def send_no_new_matches_status(total_jobs: int, alerted_jobs: int) -> bool:
    """Report an empty digest run so scheduled delivery is observable."""
    message = (
        "INFO: *Job Search Scan Complete*\n"
        "No jobs are awaiting notification in this run\\.\n"
        f"Tracked jobs: {_esc(total_jobs)} \\| Already notified: {_esc(alerted_jobs)}"
    )
    logger.info("Sending no-new-matches status (total=%d, alerted=%d).", total_jobs, alerted_jobs)
    return _send_message(message)

# Score helpers
# ──────────────────────────────────────────────
def _score_bar(score: float, width: int = 10) -> str:
    """Render a text progress bar: ████░░░░░░ 62/100"""
    filled = round(score / 100 * width)
    empty = width - filled
    bar = '█' * filled + '░' * empty
    return f"{bar} {score:.0f}/100"


def _score_emoji(score: float) -> str:
    if score >= 70:
        return "🟢"
    elif score >= 45:
        return "🟡"
    else:
        return "🔴"


# ──────────────────────────────────────────────
# URGENT ALERT  (single-job, immediate)
# ──────────────────────────────────────────────
def send_urgent_alert(job: JobRecord) -> bool:
    """Send an immediate single-job urgent alert.

    Message format:
    ┌──────────────────────────────────────┐
    │ 🚨 URGENT JOB ALERT 🚨              │
    │                                      │
    │ 💼 Junior React Developer            │
    │ 🏢 TCS                               │
    │ 📍 Hyderabad, India                  │
    │ 📊 Score: ████████░░ 78/100          │
    │ 🏷 Source: naukri                    │
    │ ⏰ Walk-in / Immediate Joining       │
    │                                      │
    │ 🔗 Apply Now                         │
    └──────────────────────────────────────┘
    """
    score = getattr(job, '_score', 0.0)

    # Build urgency reason string from the description/title
    urgency_reasons = []
    urgency_checks = [
        ("immediate join", "Immediate Joining"),
        ("walk-in", "Walk\\-in Drive"),
        ("walkin", "Walk\\-in Drive"),
        ("walk in", "Walk\\-in Drive"),
        ("urgent hiring", "Urgent Hiring"),
        ("urgent requirement", "Urgent Requirement"),
        ("spot offer", "Spot Offer"),
        ("last date", "Deadline Approaching"),
        ("apply by", "Deadline Approaching"),
        ("closing soon", "Closing Soon"),
        ("asap", "ASAP"),
    ]
    text_lower = f"{job.title} {job.description}".lower()
    for trigger, label in urgency_checks:
        if trigger in text_lower and label not in urgency_reasons:
            urgency_reasons.append(label)

    urgency_line = " / ".join(urgency_reasons) if urgency_reasons else "Urgent"

    msg = (
        f"🚨🚨🚨 *URGENT JOB ALERT* 🚨🚨🚨\n"
        f"\n"
        f"💼 *{_esc(job.title)}*\n"
        f"🏢 {_esc(job.company)}\n"
        f"📍 {_esc(job.location)}\n"
        f"📊 {_score_emoji(score)} {_esc(_score_bar(score))}\n"
        f"🏷 Source: {_esc(job.source)}\n"
    )

    if job.posted_date:
        msg += f"📅 Posted: {_esc(job.posted_date)}\n"

    msg += (
        f"⏰ *{_esc(urgency_line)}*\n"
        f"\n"
        f"[🔗 Apply Now]({_esc_url(job.apply_link)})"
    )

    logger.info(
        "Sending urgent alert: '%s' @ %s (score=%.1f)",
        job.title, job.company, score,
    )
    return _send_message(msg)


# ──────────────────────────────────────────────
# DIGEST  (batch of top N jobs)
# ──────────────────────────────────────────────
def send_digest(
    jobs: List[JobRecord],
    slot_label: str = "Daily Digest",
) -> bool:
    """Send a formatted digest of the top 8-10 jobs.

    Message format:
    ┌────────────────────────────────────────┐
    │ 📋 JOB DIGEST — Morning Scan          │
    │ 🕐 Jul 04, 2026 · 8 new matches       │
    │ ────────────────────────────────────── │
    │                                        │
    │ 1️⃣ Junior React Developer              │
    │    🏢 TCS · 📍 Hyderabad              │
    │    📊 🟢 ████████░░ 78/100            │
    │    🔗 Apply                            │
    │                                        │
    │ 2️⃣ Python Backend Intern               │
    │    🏢 Infosys · 📍 Remote             │
    │    📊 🟡 ██████░░░░ 55/100            │
    │    🔗 Apply                            │
    │    …                                   │
    └────────────────────────────────────────┘
    """
    if not jobs:
        logger.info("Digest: no jobs to send.")
        return True  # nothing to do is not an error

    # Cap at 10
    jobs = jobs[:10]

    now_str = datetime.now(timezone.utc).strftime("%b %d, %Y")
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    header = (
        f"📋 *JOB DIGEST — {_esc(slot_label)}*\n"
        f"🕐 {_esc(now_str)} · {len(jobs)} new matches\n"
        f"{'─' * 30}\n"
    )

    # Pre-generate Claude AI fit summaries for the jobs in this batch
    from notifier.digest_summary import generate_fit_summaries
    summaries_map = generate_fit_summaries(jobs)
    
    body_parts: List[str] = []
    for idx, job in enumerate(jobs):
        score = getattr(job, '_score', 0.0)
        num = number_emojis[idx] if idx < len(number_emojis) else f"{_esc(str(idx + 1))}\\."

        # Truncate long titles
        title = job.title[:60] + ("…" if len(job.title) > 60 else "")
        company = job.company[:30] + ("…" if len(job.company) > 30 else "")
        loc = job.location[:25] + ("…" if len(job.location) > 25 else "")

        # Mark urgent jobs with a tag
        from matching.urgency import is_urgent
        urgent_tag = " 🚨" if is_urgent(job) else ""
        
        # Get the AI-generated or fallback summary
        fit_reason = summaries_map.get(job.apply_link, "Strong match")

        entry = (
            f"{num} *{_esc(title)}*{urgent_tag}\n"
            f"   🏢 {_esc(company)} · 📍 {_esc(loc)}\n"
            f"   💡 _{_esc(fit_reason)}_\n"
            f"   📊 {_score_emoji(score)} {_esc(_score_bar(score))}\n"
            f"   [🔗 Apply]({_esc_url(job.apply_link)})\n"
        )
        body_parts.append(entry)

    footer = (
        f"\n{'─' * 30}\n"
        f"_Powered by Job Search Automation 🤖_"
    )

    full_msg = header + "\n".join(body_parts) + footer

    # Telegram messages are capped at 4096 chars. If we exceed,
    # split into two messages.
    if len(full_msg) > 4000:
        mid = len(jobs) // 2
        logger.info("Digest too long (%d chars), splitting into two messages.", len(full_msg))
        ok1 = send_digest(jobs[:mid], f"{slot_label} (1/2)")
        ok2 = send_digest(jobs[mid:], f"{slot_label} (2/2)")
        return ok1 and ok2

    logger.info("Sending digest '%s' with %d jobs.", slot_label, len(jobs))
    return _send_message(full_msg)

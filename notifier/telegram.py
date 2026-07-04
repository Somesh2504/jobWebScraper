"""
Notifier module. Sends messages to Telegram.
"""
import logging
import requests

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
from models import JobRecord

logger = logging.getLogger(__name__)

def send_telegram_message(text: str, parse_mode: str = "MarkdownV2") -> bool:
    """Send a message to the configured Telegram chat."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured. Skipping alert.")
        return False

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }

    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        logger.info("Telegram alert sent successfully.")
        return True
    except Exception as exc:
        logger.error("Failed to send Telegram alert: %s", exc)
        return False

def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    res = str(text)
    for c in escape_chars:
        res = res.replace(c, f"\\{c}")
    return res

def format_job_alert(job: JobRecord, score: float, is_urgent: bool) -> str:
    """Format a job record into a Telegram message."""
    urgent_tag = "🚨 *URGENT* 🚨\n" if is_urgent else ""
    
    title = escape_markdown(job.title)
    company = escape_markdown(job.company)
    loc = escape_markdown(job.location)
    score_str = escape_markdown(f"{score:.1f}/100")
    source = escape_markdown(job.source)
    
    msg = (
        f"{urgent_tag}"
        f"💼 *{title}*\n"
        f"🏢 {company}\n"
        f"📍 {loc}\n"
        f"📊 Match Score: {score_str}\n"
        f"🏷 Source: {source}\n\n"
        f"[Apply Here]({job.apply_link})"
    )
    return msg

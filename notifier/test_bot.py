"""
notifier/test_bot.py — Verify the Telegram bot can message you.

Usage:
    python notifier/test_bot.py

    1. Sends a plain connectivity test message.
    2. Sends a fake urgent-job alert.
    3. Sends a fake 5-job digest.

All three should appear in your Telegram chat within seconds.
If any fail, the script prints the Telegram API error.
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
)

import config
from models import JobRecord
from notifier.telegram_bot import _send_message, _esc, send_urgent_alert, send_digest
from matching.scorer import score_job

# ────────────────────────────────────────────
# Pre-flight check
# ────────────────────────────────────────────
if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
    print("\n❌  TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set.")
    print("   Fill them in .env (copy from .env.example) and re-run.\n")
    sys.exit(1)

print(f"Bot token : {config.TELEGRAM_BOT_TOKEN[:8]}…")
print(f"Chat ID   : {config.TELEGRAM_CHAT_ID}")
print()

# ────────────────────────────────────────────
# Test 1 — Bare connectivity
# ────────────────────────────────────────────
print("── Test 1: Connectivity ping ──")
ok = _send_message(
    f"✅ *Job Search Bot — connectivity test*\n\n"
    f"If you see this, the bot is working\\!",
    parse_mode="MarkdownV2",
)
print(f"   Result: {'✅ OK' if ok else '❌ FAILED'}\n")

# ────────────────────────────────────────────
# Test 2 — Urgent alert
# ────────────────────────────────────────────
print("── Test 2: Urgent alert ──")
urgent_job = JobRecord(
    title="Junior React Developer — Walk-in Drive",
    company="TCS Digital",
    apply_link="https://careers.tcs.com/example-react-dev-123",
    location="Hyderabad, Telangana",
    description=(
        "Immediate joining. Walk-in interview on 7 Jul 2026. "
        "React.js, Node.js, JavaScript, MongoDB. Fresher / 0-1 year. "
        "CTC: 4-6 LPA. Urgent hiring."
    ),
    posted_date="2 days ago",
    source="naukri",
)
# Score it so _score is attached
urgent_job._score = score_job(urgent_job)
ok2 = send_urgent_alert(urgent_job)
print(f"   Result: {'✅ OK' if ok2 else '❌ FAILED'}\n")

# ────────────────────────────────────────────
# Test 3 — Digest
# ────────────────────────────────────────────
print("── Test 3: Digest (5 fake jobs) ──")
fake_jobs = [
    JobRecord(
        title="SDE-1 (Full Stack) — Fresh Graduates",
        company="Google India",
        apply_link="https://careers.google.com/jobs/sde1-fullstack",
        location="Hyderabad",
        description="React, Node.js, Python, SQL, System Design. 0-1 year. Campus hire.",
        source="greenhouse",
    ),
    JobRecord(
        title="Software Engineer Intern",
        company="Microsoft IDC",
        apply_link="https://careers.microsoft.com/swe-intern",
        location="Hyderabad",
        description="TypeScript, React, Azure. Intern. Fresh graduate preferred.",
        source="lever",
    ),
    JobRecord(
        title="Backend Developer (Node.js) Fresher",
        company="Razorpay",
        apply_link="https://razorpay.com/careers/backend-dev",
        location="Remote, India",
        description="Node.js, Express, PostgreSQL, Redis, Docker. 0-2 years.",
        source="unstop",
    ),
    JobRecord(
        title="ML Engineer — Entry Level",
        company="Flipkart",
        apply_link="https://flipkart.com/careers/ml-engineer",
        location="Bangalore",
        description="Python, PyTorch, Machine Learning, Deep Learning. Fresher.",
        source="indeed",
    ),
    JobRecord(
        title="MERN Stack Developer",
        company="Infosys BPM",
        apply_link="https://careers.infosys.com/mern-dev",
        location="Hyderabad",
        description="MongoDB, Express, React, Node.js. Immediate joining. Walk-in.",
        source="internshala",
    ),
]

# Score them all
for j in fake_jobs:
    j._score = score_job(j)

# Sort descending by score
fake_jobs.sort(key=lambda j: j._score, reverse=True)

ok3 = send_digest(fake_jobs, slot_label="Morning Scan")
print(f"   Result: {'✅ OK' if ok3 else '❌ FAILED'}\n")

# ────────────────────────────────────────────
# Summary
# ────────────────────────────────────────────
all_ok = ok and ok2 and ok3
print("━" * 40)
if all_ok:
    print("🎉  All 3 tests passed! Check your Telegram chat.")
else:
    print("⚠️   Some tests failed — check the logs above.")
print("━" * 40)

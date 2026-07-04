import sqlite3
import hashlib
import re
from typing import List, Dict, Any
import os
import sys

# Add parent dir to path to import config and models
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
from models import JobRecord

def _get_dedupe_hash(title: str, company: str, apply_link: str) -> str:
    """Generate SHA256 deduplication hash from lowercased and stripped fields."""
    # Strip whitespace characters (spaces, tabs, newlines)
    s = f"{title}{company}{apply_link}".lower()
    s = re.sub(r'\s+', '', s)
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def init_db():
    """Initialize the SQLite database schema."""
    # Ensure directory exists
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            job_hash TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            apply_link TEXT NOT NULL,
            location TEXT,
            description TEXT,
            posted_date TEXT,
            source TEXT,
            is_alerted INTEGER DEFAULT 0,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

def insert_job_if_new(job: JobRecord) -> bool:
    """
    Insert a job into the DB if it doesn't exist based on the deduplication hash.
    Returns True if inserted, False if it's a duplicate.
    """
    job_hash = _get_dedupe_hash(job.title, job.company, job.apply_link)
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO jobs (
                job_hash, title, company, apply_link, location, 
                description, posted_date, source, is_alerted, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            job_hash, job.title, job.company, job.apply_link, job.location,
            job.description, job.posted_date, job.source, 
            1 if job.is_alerted else 0, job.created_at
        ))
        conn.commit()
        inserted = True
    except sqlite3.IntegrityError:
        inserted = False
    finally:
        conn.close()
        
    return inserted

def get_unalerted_jobs() -> List[JobRecord]:
    """Retrieve jobs that haven't been alerted yet, as JobRecord objects."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM jobs WHERE is_alerted = 0')
    rows = cursor.fetchall()
    conn.close()

    return [_row_to_job(row) for row in rows]


def get_all_stored_jobs() -> List[JobRecord]:
    """Retrieve ALL jobs in the database as JobRecord objects.

    Used by the urgency re-check workflow to scan stored jobs
    whose descriptions may have changed since last scoring.
    """
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM jobs')
    rows = cursor.fetchall()
    conn.close()

    return [_row_to_job(row) for row in rows]


def get_job_hash(job: JobRecord) -> str:
    """Public wrapper for the deduplication hash."""
    return _get_dedupe_hash(job.title, job.company, job.apply_link)


def _row_to_job(row) -> JobRecord:
    """Convert a sqlite3.Row to a JobRecord."""
    return JobRecord(
        title=row["title"],
        company=row["company"],
        apply_link=row["apply_link"],
        location=row["location"] or "",
        description=row["description"] or "",
        posted_date=row["posted_date"] or "",
        source=row["source"] or "",
        is_alerted=bool(row["is_alerted"]),
        created_at=row["created_at"] or "",
    )


def mark_alerted(job_hash: str):
    """Mark a specific job as alerted."""
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()

    cursor.execute('UPDATE jobs SET is_alerted = 1 WHERE job_hash = ?', (job_hash,))
    conn.commit()
    conn.close()


def get_stats() -> dict:
    """Return quick DB stats: total jobs, unalerted count, alerted count."""
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM jobs')
    total = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM jobs WHERE is_alerted = 0')
    unalerted = cursor.fetchone()[0]

    conn.close()
    return {"total": total, "unalerted": unalerted, "alerted": total - unalerted}


# Initialize DB on module import
init_db()

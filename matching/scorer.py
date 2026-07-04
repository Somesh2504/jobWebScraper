"""
matching/scorer.py — Job scoring engine.

Scores each JobRecord on a 0-100 scale across four dimensions:
    1. Skill keyword overlap  (40 pts)
    2. Entry-level signal      (25 pts)
    3. Semantic similarity     (25 pts) — cosine sim via sentence-transformers
    4. Location fit            (10 pts)

Uses the local all-MiniLM-L6-v2 model (free, ~80 MB, runs on CPU).
The resume embedding is computed once and cached for the session.
"""

import logging
import re
from functools import lru_cache
from typing import List, Optional

import numpy as np

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
from models import JobRecord

logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────
# Weights (must sum to 100)
# ───────────────────────────────────────────────────────
W_SKILL = 40.0
W_ENTRY = 25.0
W_SEMANTIC = 25.0
W_LOCATION = 10.0

# ───────────────────────────────────────────────────────
# Semantic model (lazy-loaded singleton)
# ───────────────────────────────────────────────────────
_model = None
_resume_embedding = None

MODEL_NAME = "all-MiniLM-L6-v2"


def _get_model():
    """Lazy-load the sentence-transformer model (first call takes ~5s)."""
    global _model
    if _model is None:
        try:
            logger.info("Loading sentence-transformer model '%s'...", MODEL_NAME)
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(MODEL_NAME)
            logger.info("Model loaded.")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. "
                "Semantic similarity scoring disabled. "
                "Run: pip install sentence-transformers"
            )
            _model = False  # sentinel: tried and failed
    return _model


def _get_resume_embedding() -> Optional[np.ndarray]:
    """Compute and cache the resume embedding. Returns None if model unavailable."""
    global _resume_embedding
    if _resume_embedding is None:
        model = _get_model()
        if model is False:
            return None
        resume_text = getattr(config, "RESUME_TEXT", "")
        if not resume_text or "PASTE YOUR RESUME" in resume_text:
            logger.warning(
                "config.RESUME_TEXT is empty/placeholder — semantic similarity will be 0. "
                "Paste your resume text into config.py."
            )
            return None
        _resume_embedding = model.encode(resume_text, normalize_embeddings=True)
    return _resume_embedding


# ───────────────────────────────────────────────────────
# 1. SKILL KEYWORD OVERLAP  (0 → W_SKILL)
# ───────────────────────────────────────────────────────
def _score_skills(job: JobRecord) -> float:
    """
    Count how many of config.MY_SKILLS appear in the job text.
    Returns a score in [0, W_SKILL].
    """
    text = f"{job.title} {job.description}".lower()

    if not text.strip():
        return 0.0

    matched = 0
    total = len(config.MY_SKILLS)
    if total == 0:
        return 0.0

    for skill in config.MY_SKILLS:
        # Use word-boundary matching so "sql" doesn't match "nosql"
        # but "node.js" still matches "node.js"
        pattern = re.escape(skill.lower())
        if re.search(r'(?:^|[\s,;/|(\[])' + pattern + r'(?:[\s,;/|)\].]|$)', text):
            matched += 1

    ratio = matched / total
    return ratio * W_SKILL


# ───────────────────────────────────────────────────────
# 2. ENTRY-LEVEL SIGNAL  (0 → W_ENTRY)
# ───────────────────────────────────────────────────────

# Positive signals → boost score
_POSITIVE_PATTERNS = [
    r'\bfresher\b',
    r'\bfresh\s+graduate\b',
    r'\bentry[\s-]level\b',
    r'\bjunior\b',
    r'\btrainee\b',
    r'\bintern(?:ship)?\b',
    r'\bcampus\b',
    r'\bnew\s+grad\b',
    r'\bearly\s+career\b',
    r'\b0[\s-]?(?:to|-)[\s-]?[12]\s*(?:year|yr)',
    r'\b0[\s-]?[12]\s*(?:year|yr)',
    r'\b(?:graduate|graduation)\b',
    r'\bassociate\b',
]

# Negative signals → penalize (requires senior experience)
_NEGATIVE_PATTERNS = [
    r'\b[5-9]\+?\s*(?:year|yr)s?\b',
    r'\b(?:1[0-9]|20)\+?\s*(?:year|yr)s?\b',
    r'\bsenior\b',
    r'\bstaff\s+engineer\b',
    r'\bprincipal\b',
    r'\b(?:lead|head|director|manager|vp)\b',
    r'\barchitect\b',
]


def _score_entry_level(job: JobRecord) -> float:
    """
    Boost for entry-level signals, penalize for senior-level signals.
    Returns a score in [0, W_ENTRY].

    Scoring logic:
        - Start at 50% (neutral)
        - Each positive signal adds +10% (capped at 100%)
        - Each negative signal subtracts 15% (floored at 0%)
    """
    text = f"{job.title} {job.description}".lower()
    if not text.strip():
        return W_ENTRY * 0.5  # neutral if no text

    score_pct = 0.5  # start neutral

    for pat in _POSITIVE_PATTERNS:
        if re.search(pat, text):
            score_pct += 0.10

    for pat in _NEGATIVE_PATTERNS:
        if re.search(pat, text):
            score_pct -= 0.15

    score_pct = max(0.0, min(1.0, score_pct))
    return score_pct * W_ENTRY


# ───────────────────────────────────────────────────────
# 3. SEMANTIC SIMILARITY  (0 → W_SEMANTIC)
# ───────────────────────────────────────────────────────
def _score_semantic(job: JobRecord) -> float:
    """
    Cosine similarity between resume embedding and JD embedding.
    Returns a score in [0, W_SEMANTIC].

    Uses normalized embeddings so cosine sim = dot product.
    """
    jd_text = f"{job.title} {job.description}".strip()
    if not jd_text:
        return 0.0

    resume_emb = _get_resume_embedding()
    if resume_emb is None:
        return 0.0

    model = _get_model()
    if model is False:
        return 0.0
    jd_emb = model.encode(jd_text, normalize_embeddings=True)

    # Cosine similarity (both normalized → dot product)
    cos_sim = float(np.dot(resume_emb, jd_emb))
    # Clamp to [0, 1] — negative similarity means totally unrelated
    cos_sim = max(0.0, min(1.0, cos_sim))

    return cos_sim * W_SEMANTIC


# ───────────────────────────────────────────────────────
# 4. LOCATION FIT  (0 → W_LOCATION)
# ───────────────────────────────────────────────────────
def _score_location(job: JobRecord) -> float:
    """
    Full points if job location matches any target location.
    Returns 0 or W_LOCATION (binary).
    """
    loc = job.location.lower().strip()
    if not loc:
        # Empty location: assume PAN India or not specified → partial credit
        return W_LOCATION * 0.5

    for target in config.TARGET_LOCATIONS:
        if target in loc:
            return W_LOCATION

    return 0.0


# ───────────────────────────────────────────────────────
# PUBLIC API
# ───────────────────────────────────────────────────────
def score_job(job: JobRecord) -> float:
    """
    Score a single job on a 0-100 scale.

    Args:
        job: A JobRecord to evaluate.

    Returns:
        A float score in [0, 100].
    """
    s_skill = _score_skills(job)
    s_entry = _score_entry_level(job)
    s_semantic = _score_semantic(job)
    s_location = _score_location(job)

    total = s_skill + s_entry + s_semantic + s_location

    logger.debug(
        "Score for '%s' @ %s: skill=%.1f entry=%.1f semantic=%.1f loc=%.1f → %.1f",
        job.title, job.company, s_skill, s_entry, s_semantic, s_location, total,
    )

    return round(total, 2)


def rank_jobs(jobs: List[JobRecord], top_n: int = 10) -> List[JobRecord]:
    """
    Score all jobs, sort by score descending, return the top N.

    Each returned JobRecord gets an extra `_score` attribute.

    Args:
        jobs:  List of JobRecords to rank.
        top_n: Number of top results to return.

    Returns:
        Top N JobRecords sorted by descending score.
    """
    if not jobs:
        return []

    scored: List[tuple[float, JobRecord]] = []
    for job in jobs:
        s = score_job(job)
        # Attach score as a runtime attribute for downstream use
        job._score = s  # type: ignore[attr-defined]
        scored.append((s, job))

    scored.sort(key=lambda x: x[0], reverse=True)

    top = [job for _, job in scored[:top_n]]

    logger.info(
        "Ranked %d jobs → top %d (best=%.1f, cutoff=%.1f)",
        len(jobs), len(top),
        scored[0][0] if scored else 0,
        scored[min(top_n - 1, len(scored) - 1)][0] if scored else 0,
    )

    return top

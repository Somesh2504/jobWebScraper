"""
Generates punchy one-line summaries for jobs using the Claude API.
Provides a graceful fallback if the API fails or is not configured.
"""
import json
import logging
import re
from typing import List, Dict

from google import genai
from google.genai import types

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
from models import JobRecord

logger = logging.getLogger(__name__)

def _get_fallback_summary(job: JobRecord) -> str:
    """Fallback: simple template based on matched skills."""
    text_to_check = f"{job.title} {job.description}".lower()
    matched_skills = [s for s in config.MY_SKILLS if s in text_to_check]
    
    if matched_skills:
        # Take up to top 3 skills
        skills_str = ", ".join(s.title() for s in matched_skills[:3])
        return f"Strong match: {skills_str}, entry-level"
    return "Strong match for your profile"

def generate_fit_summaries(jobs: List[JobRecord]) -> Dict[str, str]:
    """
    Generate a 1-line reason for each job explaining why it's a good fit.
    Returns a dict mapping job.apply_link to the string summary.
    """
    summaries = {}
    
    if not config.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set. Using fallback summaries.")
        for job in jobs:
            summaries[job.apply_link] = _get_fallback_summary(job)
        return summaries

    # We only process up to 10 jobs to save tokens/time
    jobs_to_process = jobs[:10]
    
    # Build prompt
    prompt = f"""
You are a career assistant helping a candidate find jobs.
Candidate Skills: {', '.join(config.MY_SKILLS)}

Here are {len(jobs_to_process)} job descriptions. For each one, provide a short, punchy ONE-LINE reason (max 10-12 words) why it fits the candidate. 
Focus on technical skill overlap or entry-level fit. Do not use filler words like "This fits because". Keep it direct (e.g., "Matches your React and Node.js skills" or "Great entry-level Python role").

Respond with ONLY a valid JSON object where keys are the Job IDs provided and values are the 1-line summaries. Do not include markdown formatting or backticks around the JSON.

"""
    for i, job in enumerate(jobs_to_process):
        # We use a simple index as the ID for the prompt to save tokens, 
        # then map it back to the apply_link.
        desc_snippet = job.description[:500] if job.description else "No description available."
        prompt += f"Job ID: {i}\nTitle: {job.title}\nCompany: {job.company}\nSnippet: {desc_snippet}\n\n"

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )
        
        content = response.text.strip()
            
        parsed = json.loads(content)
        
        # Map back to apply links
        for i, job in enumerate(jobs_to_process):
            str_idx = str(i)
            if str_idx in parsed:
                summaries[job.apply_link] = parsed[str_idx]
            else:
                summaries[job.apply_link] = _get_fallback_summary(job)
                
        logger.info("Successfully generated AI summaries for %d jobs.", len(parsed))
                
    except Exception as e:
        logger.error("Gemini API failed to generate summaries: %s. Using fallbacks.", e)
        for job in jobs_to_process:
            summaries[job.apply_link] = _get_fallback_summary(job)
            
    return summaries

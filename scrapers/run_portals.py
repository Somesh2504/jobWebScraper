"""
Runner script for public portal scrapers.
Calls all portal scrapers dynamically. LinkedIn runs at a reduced frequency.
"""
import logging
import importlib
import pkgutil
import random
import time
from typing import List

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import config
from storage import storage
from models import JobRecord

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PORTALS_PACKAGE = "scrapers.portals"

def run_all(reduced_frequency: bool = False):
    """
    Run all portal scrapers.
    If reduced_frequency is True, it will run the linkedin_public scraper.
    Usually we might only run linkedin_public on every 2nd or 3rd run to avoid bans.
    """
    logger.info("Starting public portals run... (reduced_frequency=%s)", reduced_frequency)
    
    try:
        portals_pkg = importlib.import_module(PORTALS_PACKAGE)
    except Exception as e:
        logger.error("Failed to import %s: %s", PORTALS_PACKAGE, e)
        return

    scraped_total = 0
    new_inserted = 0

    # Discover all modules in scrapers/portals/
    for _, module_name, _ in pkgutil.iter_modules(portals_pkg.__path__):
        if module_name == "linkedin_public" and not reduced_frequency:
            logger.info("Skipping linkedin_public (reduced_frequency=False)")
            continue
            
        full_module_name = f"{PORTALS_PACKAGE}.{module_name}"
        try:
            mod = importlib.import_module(full_module_name)
        except Exception as e:
            logger.error("Failed to load portal module %s: %s", full_module_name, e)
            continue
            
        if not hasattr(mod, "fetch_jobs"):
            continue
            
        logger.info("Running portal scraper: %s", module_name)
        
        # Call fetch_jobs for each keyword combination and target location
        # Since searching ALL combinations cross ALL portals can be huge,
        # we'll pick a random subset of keywords for each run or just the first few.
        # For full automation, we might loop all, but let's loop them.
        
        for kws in config.SEARCH_KEYWORDS:
            for loc in config.TARGET_LOCATIONS:
                logger.info(">> Portal %s searching: %s in %s", module_name, kws, loc)
                
                try:
                    jobs: List[JobRecord] = mod.fetch_jobs(kws, location=loc)
                    scraped_total += len(jobs)
                    
                    # Insert into DB
                    for job in jobs:
                        if storage.insert_job_if_new(job):
                            new_inserted += 1
                            
                except Exception as e:
                    logger.error("Error in %s for %s, %s: %s", module_name, kws, loc, e)
                
                # Global rate limit between searches
                delay = random.uniform(*config.REQUEST_DELAY)
                time.sleep(delay)
                
    logger.info("Portals run complete! Scraped: %d | New inserted: %d", scraped_total, new_inserted)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--reduced-frequency", action="store_true", help="Run linkedin_public scraper")
    args = parser.parse_args()
    
    run_all(reduced_frequency=args.reduced_frequency)

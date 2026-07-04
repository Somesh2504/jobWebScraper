# Company career portal scrapers (non-ATS)
# Each module exposes: fetch_jobs() -> List[JobRecord]

from scrapers.companies.tcs import fetch_jobs as tcs_fetch
from scrapers.companies.infosys import fetch_jobs as infosys_fetch
from scrapers.companies.wipro import fetch_jobs as wipro_fetch
from scrapers.companies.accenture import fetch_jobs as accenture_fetch
from scrapers.companies.cognizant import fetch_jobs as cognizant_fetch

__all__ = [
    "tcs_fetch",
    "infosys_fetch",
    "wipro_fetch",
    "accenture_fetch",
    "cognizant_fetch",
]

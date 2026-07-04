from dataclasses import dataclass, field
import datetime

@dataclass
class JobRecord:
    title: str
    company: str
    apply_link: str
    location: str = ""
    description: str = ""
    posted_date: str = ""
    source: str = ""
    is_alerted: bool = False
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

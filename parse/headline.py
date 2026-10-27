"""Parse getprog headline: role, company, years of experience."""
import re
from dataclasses import dataclass
from typing import Optional

EXPERIENCE_RE = re.compile(
    r"(\d+\+?)\s*y(?:ears?)?\s*experience\s*$",
    re.IGNORECASE,
)


@dataclass
class HeadlineParts:
    role: str
    current_company: str
    years_experience: str
    headline_raw: str
    parse_warning: Optional[str] = None


def parse_headline(headline: str) -> HeadlineParts:
    """Split e.g. 'Senior ML Engineer at Netflix 9 y experience' into parts."""
    raw = (headline or "").strip()
    if not raw:
        return HeadlineParts("", "", "", raw, "empty headline")

    years = ""
    rest = raw
    m = EXPERIENCE_RE.search(raw)
    if m:
        years = m.group(1)
        rest = raw[: m.start()].strip()
    elif re.search(r"experience", raw, re.I):
        return HeadlineParts(
            raw, "", years, raw, "could not parse years from experience suffix"
        )

    role = rest
    company = ""
    warning = None

    at_idx = rest.lower().rfind(" at ")
    if at_idx != -1:
        role = rest[:at_idx].strip()
        company = rest[at_idx + 4 :].strip()
    else:
        warning = "no ' at ' separator found for company"

    return HeadlineParts(role, company, years, raw, warning)

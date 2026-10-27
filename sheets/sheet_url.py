"""Parse Google Sheet URL into spreadsheet ID."""
import re
from typing import Optional

_SHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")


def extract_spreadsheet_id(url: str) -> Optional[str]:
    """Extract spreadsheet ID from a Google Sheets URL."""
    u = (url or "").strip()
    if not u:
        return None
    m = _SHEET_ID_RE.search(u)
    if m:
        return m.group(1)
    # Bare ID (no slashes, typical length)
    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", u):
        return u
    return None

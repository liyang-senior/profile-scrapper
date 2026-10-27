"""Compare candidates by LinkedIn URL, or name + role + company + photo."""
import re
from typing import Any, Dict, List


def _norm_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _norm_photo(value: Any) -> str:
    s = str(value or "").strip().lower().rstrip("/")
    m = re.match(r'^=image\("([^"]+)"', s)
    if m:
        return m.group(1).rstrip("/")
    return s


def _linkedin_slug(value: Any) -> str:
    s = str(value or "").strip().lower().rstrip("/")
    match = re.search(r"linkedin\.com/in/([^/?#]+)", s)
    return match.group(1) if match else ""


def is_same_person(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """True when the same person — prefer LinkedIn URL when available."""
    slug_a = _linkedin_slug(a.get("linkedin_url"))
    slug_b = _linkedin_slug(b.get("linkedin_url"))
    if slug_a and slug_b and slug_a == slug_b:
        return True

    if _norm_text(a.get("name")) != _norm_text(b.get("name")):
        return False
    if _norm_text(a.get("role")) != _norm_text(b.get("role")):
        return False
    if _norm_text(a.get("current_company")) != _norm_text(b.get("current_company")):
        return False
    if _norm_photo(a.get("photo")) != _norm_photo(b.get("photo")):
        return False
    return True


def is_duplicate_of_any(row: Dict[str, Any], others: List[Dict[str, Any]]) -> bool:
    for other in others:
        if is_same_person(row, other):
            return True
    return False

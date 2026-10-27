"""Map parsed role titles to Google Sheet tab names."""
from pathlib import Path
from typing import Dict, List

import yaml

LEVEL_PREFIXES = [
    "associate",
    "head of",
    "vice president",
    "vp",
    "director",
    "principal",
    "staff",
    "senior",
    "sr",
    "lead",
    "middle",
    "mid",
    "junior",
    "jr",
    "intern",
]

DEFAULT_TAB = "Other"
_ALIASES: Dict[str, List[str]] | None = None
_ALIASES_MTIME: float = -1.0
_ALIASES_PATH: Path | None = None


def _aliases_path() -> Path:
    from settings import ROOT, bundle_dir

    runtime = ROOT / "config" / "role_aliases.yaml"
    if runtime.exists():
        return runtime
    return bundle_dir() / "config" / "role_aliases.yaml"


def _normalize_role_text(role: str) -> str:
    """Lowercase and treat hyphens like spaces so matching ignores capitalization."""
    text = (role or "").casefold()
    for ch in "-_/":
        text = text.replace(ch, " ")
    return " ".join(text.split())


def invalidate_aliases_cache() -> None:
    global _ALIASES, _ALIASES_MTIME, _ALIASES_PATH
    _ALIASES = None
    _ALIASES_MTIME = -1.0
    _ALIASES_PATH = None


def load_aliases() -> Dict[str, List[str]]:
    """Load tab → alias phrases. Reloads when config/role_aliases.yaml changes on disk."""
    global _ALIASES, _ALIASES_MTIME, _ALIASES_PATH

    path = _aliases_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = -1.0

    if (
        _ALIASES is not None
        and _ALIASES_PATH == path
        and mtime == _ALIASES_MTIME
    ):
        return _ALIASES

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    _ALIASES = {
        str(tab): [_normalize_role_text(a) for a in (aliases or []) if str(a).strip()]
        for tab, aliases in data.items()
    }
    _ALIASES_MTIME = mtime
    _ALIASES_PATH = path
    return _ALIASES


def strip_level_prefix(role: str) -> str:
    """Remove leading seniority for tab matching; keep full role in sheet."""
    text = role.lower().strip()
    changed = True
    while changed:
        changed = False
        for prefix in sorted(LEVEL_PREFIXES, key=len, reverse=True):
            if text.startswith(prefix + " "):
                text = text[len(prefix) :].strip()
                changed = True
                break
    return text


def role_to_tab(role: str) -> str:
    """Return worksheet tab name for a role string (case-insensitive substring)."""
    if not role or not role.strip():
        return DEFAULT_TAB

    text = _normalize_role_text(role)
    aliases = load_aliases()

    best_tab = DEFAULT_TAB
    best_len = 0
    for tab, phrases in aliases.items():
        for phrase in phrases:
            if phrase and phrase in text and len(phrase) > best_len:
                best_len = len(phrase)
                best_tab = tab

    return best_tab


def sanitize_tab_name(name: str) -> str:
    """Google Sheets tab names: max 100 chars, no \\ / ? * [ ]"""
    invalid = set(r"\/[]?*")
    cleaned = "".join(c if c not in invalid else "_" for c in name)
    return cleaned[:100] or DEFAULT_TAB

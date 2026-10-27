"""Load and save user settings."""
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
import yaml

from extract.search_params import migrate_settings_search, search_from_url


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """Read-only assets (PyInstaller extract dir, or project root in dev)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def project_root() -> Path:
    """Writable project folder (next to the .exe when frozen)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = project_root()
SETTINGS_PATH = ROOT / "config" / "user_settings.json"

# Simple mtime cache — avoids re-reading the JSON file every Streamlit render.
_settings_cache: Optional[Dict[str, Any]] = None
_settings_mtime: float = 0.0


def ensure_runtime_layout() -> None:
    """Create data/logs/config next to the exe (or project root in dev)."""
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    (ROOT / "logs").mkdir(parents=True, exist_ok=True)
    (ROOT / "config").mkdir(parents=True, exist_ok=True)

    _ensure_role_aliases_file()

    readme = ROOT / "README.txt"
    if is_frozen() and not readme.exists():
        readme.write_text(
            "Getprog Scraper\n"
            "===============\n\n"
            "Run GetprogScraper.exe in this folder.\n\n"
            "Saved here (copy the whole folder to move the app):\n"
            "  config\\user_settings.json  — search + Sheet / Apps Script URLs\n"
            "  config\\role_aliases.yaml   — Sheet tab names + similar job titles (editable)\n"
            "  data\\{SheetName}.csv      — scraped profiles (named after the Google Sheet)\n"
            "  logs\\run.log               — scrape log\n"
            "  storage_state.json         — getprog login session\n\n"
            "Edit config\\role_aliases.yaml to add/rename tabs or similar titles,\n"
            "then start a new scrape (restart the app if it was already open).\n",
            encoding="utf-8",
        )


def _ensure_role_aliases_file() -> None:
    """Keep config/role_aliases.yaml next to the exe so users can edit tab names."""
    aliases_dst = ROOT / "config" / "role_aliases.yaml"
    aliases_src = bundle_dir() / "config" / "role_aliases.yaml"
    if not aliases_src.exists():
        return

    if not aliases_dst.exists():
        shutil.copy2(aliases_src, aliases_dst)
        return

    # Add any new default tabs missing from the user's file; never overwrite their edits.
    try:
        with open(aliases_src, encoding="utf-8") as f:
            bundled = yaml.safe_load(f) or {}
        with open(aliases_dst, encoding="utf-8") as f:
            runtime = yaml.safe_load(f) or {}
    except Exception:
        return

    if not isinstance(bundled, dict) or not isinstance(runtime, dict):
        return

    added = False
    for tab, aliases in bundled.items():
        if tab not in runtime:
            runtime[tab] = aliases
            added = True
    if not added:
        return

    with open(aliases_dst, "w", encoding="utf-8") as f:
        yaml.safe_dump(runtime, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    try:
        from parse.role_groups import invalidate_aliases_cache

        invalidate_aliases_cache()
    except Exception:
        pass


def load_settings() -> Dict[str, Any]:
    global _settings_cache, _settings_mtime
    ensure_runtime_layout()
    # Return cached copy if the file hasn't been modified since last read.
    try:
        mtime = SETTINGS_PATH.stat().st_mtime if SETTINGS_PATH.exists() else 0.0
    except OSError:
        mtime = 0.0
    if _settings_cache is not None and mtime == _settings_mtime:
        return dict(_settings_cache)

    load_dotenv(ROOT / ".env")
    data: Dict[str, Any] = {
        "getprog_email": os.getenv("GETPROG_EMAIL", ""),
        "getprog_password": os.getenv("GETPROG_PASSWORD", ""),
        "google_sheet_url": os.getenv("GOOGLE_SHEET_URL", ""),
        "apps_script_url": os.getenv("APPS_SCRIPT_URL", ""),
        "headless": os.getenv("HEADLESS", "true").lower() in ("1", "true", "yes"),
        "max_pages": int(os.getenv("MAX_PAGES", "10")),
        "push_to_sheets": os.getenv("PUSH_TO_SHEETS", "true").lower() in ("1", "true", "yes"),
    }
    search_url = os.getenv("SEARCH_URL", "")
    if search_url:
        data["search"] = search_from_url(search_url)
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data.update(json.load(f))
    if data.get("getprog_email"):
        data["getprog_email"] = str(data["getprog_email"]).strip()
    migrate_settings_search(data)
    _settings_cache = data
    _settings_mtime = mtime
    return dict(data)


def invalidate_settings_cache() -> None:
    global _settings_cache
    _settings_cache = None


def save_settings(data: Dict[str, Any]) -> None:
    migrate_settings_search(data)
    payload = dict(data)
    payload.pop("search_url", None)
    if payload.get("getprog_email"):
        payload["getprog_email"] = str(payload["getprog_email"]).strip()
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    invalidate_settings_cache()

"""Upload candidates to Google Sheets via Apps Script."""
import csv
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from sheets.apps_script_client import push_via_apps_script


def push_candidates(
    candidates: List[Dict[str, Any]],
    apps_script_url: str,
    spreadsheet_id: str,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, int]:
    return push_via_apps_script(
        candidates,
        web_app_url=apps_script_url,
        spreadsheet_id=spreadsheet_id,
        log_fn=log_fn,
    )


def push_csv(
    csv_path: Path,
    apps_script_url: str,
    spreadsheet_id: str,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, int]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        candidates = list(csv.DictReader(f))
    return push_candidates(candidates, apps_script_url, spreadsheet_id, log_fn=log_fn)


def latest_backup_csv(settings=None):
    from pipeline import latest_backup_csv as pipeline_latest_csv

    return pipeline_latest_csv(settings)

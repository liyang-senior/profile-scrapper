"""Scrape getprog, save one CSV, optionally upload new rows to Google Sheets."""
import csv
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dedupe import is_same_person
from extract.api_client import row_has_email
from extract.dom import scrape_search_results
from extract.search_params import job_queries_from_search, migrate_settings_search, validate_search
from settings import ROOT

DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
MAIN_CSV = DATA_DIR / "candidates.csv"
STOP_FLAG = LOGS_DIR / "stop.flag"
PID_FILE = LOGS_DIR / "scrape.pid"

_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*]')
_RESERVED_FILENAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

CSV_FIELDS = [
    "photo",
    "name",
    "email",
    "sender",
    "sent",
    "role",
    "current_company",
    "years_experience",
    "github_url",
    "linkedin_url",
    "location",
    "languages",
    "phone_numbers",
    "role_tab",
]


def sanitize_csv_stem(sheet_name: str) -> str:
    """Turn a Google Sheet title into a safe CSV filename stem (e.g. LatAm → LatAm)."""
    stem = _INVALID_FILENAME.sub("-", (sheet_name or "").strip())
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    stem = stem[:120].rstrip(" .")
    if not stem:
        return "candidates"
    if stem.upper() in _RESERVED_FILENAMES:
        return f"_{stem}"
    return stem


def csv_path_for_sheet_name(sheet_name: Optional[str]) -> Path:
    stem = sanitize_csv_stem(sheet_name) if sheet_name else "candidates"
    return DATA_DIR / f"{stem}.csv"


def cached_spreadsheet_name(settings: Optional[Dict[str, Any]]) -> Optional[str]:
    settings = settings or {}
    from sheets.sheet_url import extract_spreadsheet_id

    sid = extract_spreadsheet_id(settings.get("google_sheet_url") or "") or ""
    cached_id = str(settings.get("spreadsheet_id") or "").strip()
    name = str(settings.get("spreadsheet_name") or "").strip()
    if name and sid and sid == cached_id:
        return name
    return None


def remember_spreadsheet(settings: Dict[str, Any], name: str, spreadsheet_id: str) -> None:
    from settings import save_settings

    settings["spreadsheet_name"] = name
    settings["spreadsheet_id"] = spreadsheet_id
    save_settings(settings)


def fetch_sheet_name(
    settings: Optional[Dict[str, Any]],
    log_fn=None,
) -> Optional[str]:
    """Read the Google Spreadsheet title via Apps Script (doGet)."""
    settings = settings or {}
    script_url = str(settings.get("apps_script_url") or "").strip()
    sheet_url = str(settings.get("google_sheet_url") or "").strip()
    if not script_url or not sheet_url:
        return None
    try:
        from sheets.apps_script_client import fetch_spreadsheet_info

        info = fetch_spreadsheet_info(script_url, sheet_url)
        remember_spreadsheet(settings, info["name"], info["id"])
        return info["name"]
    except Exception as exc:
        if log_fn:
            log_fn(f"Could not read spreadsheet name: {exc}")
        return None


def resolve_csv_path(
    settings: Optional[Dict[str, Any]] = None,
    *,
    fetch: bool = False,
    log_fn=None,
) -> Path:
    """CSV path for the current Google Sheet title, e.g. data/LatAm.csv."""
    settings = settings or {}
    name = None
    if fetch:
        name = fetch_sheet_name(settings, log_fn=log_fn)
    if not name:
        name = cached_spreadsheet_name(settings)
    return csv_path_for_sheet_name(name)


def _load_existing_csv(csv_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = csv_path or MAIN_CSV
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def latest_backup_csv(settings: Optional[Dict[str, Any]] = None) -> Optional[Path]:
    path = resolve_csv_path(settings, fetch=False)
    return path if path.exists() else None


def clear_csv(settings: Optional[Dict[str, Any]] = None) -> Tuple[Path, bool]:
    """Delete only data/{SheetName}.csv for the current Google Spreadsheet.

    Never deletes other CSVs (e.g. US.csv stays if the sheet is LatAm).
    Never falls back to candidates.csv unless that is the spreadsheet title.
    """
    settings = settings or {}
    name = fetch_sheet_name(settings) or cached_spreadsheet_name(settings)
    if not name:
        raise RuntimeError(
            "Cannot clear CSV: could not read the Google Sheet name. "
            "Set Sheet URL and Apps Script URL, then click Test Sheets."
        )
    stem = sanitize_csv_stem(name)
    path = DATA_DIR / f"{stem}.csv"
    deleted = False
    if DATA_DIR.exists():
        for f in DATA_DIR.glob("*.csv"):
            if f.stem.lower() != stem.lower():
                continue
            f.unlink()
            deleted = True
            path = f
            break
    return path, deleted


def filter_new_candidates(
    candidates: List[Dict[str, Any]],
    log_fn=None,
    csv_path: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Return candidates not already in the CSV (match name, role, company, photo one by one)."""
    path = csv_path or MAIN_CSV
    existing_rows = _load_existing_csv(path)
    if log_fn:
        if path.exists():
            log_fn(f"CSV check: {path} ({len(existing_rows)} rows loaded for dedupe)")
        else:
            log_fn(f"CSV check: no file at {path} — all fetched profiles treated as new")

    new_rows: List[Dict[str, Any]] = []
    skipped = 0

    for row in candidates:
        if any(is_same_person(row, existing) for existing in existing_rows):
            skipped += 1
            continue
        if any(is_same_person(row, previous) for previous in new_rows):
            skipped += 1
            continue
        new_rows.append(row)

    return new_rows, skipped


def append_csv(candidates: List[Dict[str, Any]], csv_path: Optional[Path] = None) -> int:
    """Append new rows to this sheet's CSV. Returns number of rows appended."""
    path = csv_path or MAIN_CSV
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists() and path.stat().st_size > 0

    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if not file_exists:
            w.writeheader()
        w.writerows(candidates)

    return len(candidates)


def clear_log() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    (LOGS_DIR / "run.log").write_text("", encoding="utf-8")


def request_stop() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    STOP_FLAG.write_text("1", encoding="utf-8")


def clear_stop() -> None:
    if STOP_FLAG.exists():
        STOP_FLAG.unlink()


def is_stop_requested() -> bool:
    return STOP_FLAG.exists()


def write_pid() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def clear_pid() -> None:
    if PID_FILE.exists():
        PID_FILE.unlink()


def read_scrape_pid() -> Optional[int]:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def run_scrape(settings: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / "run.log"
    clear_stop()
    write_pid()

    def log(msg: str) -> None:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")

    stopped = False
    csv_path = MAIN_CSV
    try:
        log("Starting scrape")
        csv_path = resolve_csv_path(settings, fetch=True, log_fn=log)
        sheet_name = cached_spreadsheet_name(settings)
        script_url = str(settings.get("apps_script_url") or "").strip()
        sheet_url = str(settings.get("google_sheet_url") or "").strip()
        if script_url and sheet_url and not sheet_name:
            raise RuntimeError(
                "Could not read the Google Sheet name. "
                "Use Test Sheets in the sidebar, then scrape again."
            )
        if sheet_name:
            log(f"Spreadsheet: {sheet_name} → CSV {csv_path.name}")
        else:
            log(f"No spreadsheet name yet — using {csv_path.name}")
        leftover = DATA_DIR / "candidates.csv"
        if csv_path != leftover and leftover.exists():
            log(f"Note: {leftover.name} is unused for this sheet (dedupe uses {csv_path.name})")

        max_pages = int(settings.get("max_pages") or 10)
        email = (settings.get("getprog_email") or "").strip()
        password = settings.get("getprog_password") or ""

        if not email or not password:
            raise RuntimeError("Enter getprog email and password in the sidebar, then Save.")
        migrate_settings_search(settings)
        search = settings.get("search") or {}
        validate_search(search)
        queries = job_queries_from_search(search)
        log(
            "Job queries: "
            + "; ".join(queries)
            + " (each line is a separate search; tabs ignore capitalization)"
        )

        candidates: List[Dict[str, Any]] = []
        for i, query in enumerate(queries, 1):
            if is_stop_requested():
                break
            log(f"Search {i}/{len(queries)}: {query}")
            one = dict(search)
            one["text"] = query
            batch = scrape_search_results(
                search=one,
                email=email,
                password=password,
                headless=bool(settings.get("headless", True)),
                dry_run=dry_run,
                max_pages=max_pages,
                log_fn=log,
                stop_check=is_stop_requested,
            )
            candidates.extend(batch)
            log(f"  {query}: {len(batch)} profiles with email")

        if is_stop_requested():
            stopped = True
            log("Stopped by user")
            return {"count": 0, "new_count": 0, "skipped": 0, "stopped": True, "csv_path": str(csv_path)}

        log(f"Fetched {len(candidates)} profiles this run")

        with_email = [r for r in candidates if row_has_email(r)]
        dropped_no_email = len(candidates) - len(with_email)
        if dropped_no_email:
            log(f"Skipped {dropped_no_email} profiles with no Gmail address (not saved)")

        new_rows, skipped = filter_new_candidates(with_email, log_fn=log, csv_path=csv_path)
        log(f"New profiles: {len(new_rows)} | Already in CSV (skipped): {skipped}")

        if not new_rows:
            log("No new profiles to save.")
            log("Scrape complete")
            return {
                "count": len(candidates),
                "new_count": 0,
                "skipped": skipped,
                "skipped_no_email": dropped_no_email,
                "total_csv_rows": len(_load_existing_csv(csv_path)),
                "csv_path": str(csv_path),
                "log_path": str(log_file),
            }

        appended = append_csv(new_rows, csv_path=csv_path)
        total_rows = len(_load_existing_csv(csv_path))
        log(f"CSV: {csv_path} (+{appended} rows, {total_rows} total)")

        if settings.get("push_to_sheets"):
            script_url = (settings.get("apps_script_url") or "").strip()
            sheet_url = (settings.get("google_sheet_url") or "").strip()
            if not script_url:
                raise RuntimeError("Enter Apps Script URL (/exec or /dev) in the sidebar.")
            if not sheet_url:
                raise RuntimeError(
                    "Enter your Google Sheet URL in the sidebar. "
                    "The Apps Script must be bound to that same spreadsheet."
                )
            from sheets.sheet_url import extract_spreadsheet_id
            from sheets.writer import push_candidates

            sheet_id = extract_spreadsheet_id(sheet_url)
            if not sheet_id:
                raise RuntimeError("Could not read spreadsheet ID from Google Sheet URL.")

            log(f"Uploading {len(new_rows)} new rows to Google Sheets…")
            counts = push_candidates(
                new_rows,
                apps_script_url=script_url,
                spreadsheet_id=sheet_id,
                log_fn=log,
            )
            log(f"Sheets upload OK: {counts}")

        log("Scrape complete")
        return {
            "count": len(candidates),
            "new_count": len(new_rows),
            "skipped": skipped,
            "skipped_no_email": dropped_no_email,
            "total_csv_rows": total_rows,
            "csv_path": str(csv_path),
            "log_path": str(log_file),
        }

    except Exception as exc:
        if is_stop_requested():
            log("Stopped by user")
            return {"count": 0, "new_count": 0, "skipped": 0, "stopped": True, "csv_path": str(csv_path)}
        log(f"ERROR: {exc}")
        raise
    finally:
        clear_pid()
        if not stopped:
            clear_stop()

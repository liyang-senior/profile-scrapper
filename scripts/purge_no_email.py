"""Remove rows without email from CSV and Google Sheets."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from extract.api_client import row_has_email
from pipeline import resolve_csv_path
from settings import load_settings
from sheets.apps_script_client import purge_no_email_rows
from sheets.sheet_url import extract_spreadsheet_id


def purge_csv(csv_path: Path) -> int:
    if not csv_path.exists():
        print(f"No CSV at {csv_path}")
        return 0

    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("CSV is empty")
        return 0

    kept = [r for r in rows if row_has_email(r)]
    removed = len(rows) - len(kept)
    if not removed:
        print("No rows without email in CSV.")
        return 0

    fieldnames = list(rows[0].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(kept)

    print(f"Removed {removed} rows without email from {csv_path} ({len(kept)} remaining)")
    return removed


def main() -> None:
    settings = load_settings()
    csv_path = resolve_csv_path(settings, fetch=True)
    purge_csv(csv_path)

    script_url = (settings.get("apps_script_url") or "").strip()
    sheet_url = (settings.get("google_sheet_url") or "").strip()
    if not script_url or not sheet_url:
        print("Skip sheet purge — set apps_script_url and google_sheet_url to clean the sheet too.")
        return

    sid = extract_spreadsheet_id(sheet_url)
    if not sid:
        print("Invalid google_sheet_url")
        return

    print("Purging no-email rows from Google Sheets…")
    try:
        removed = purge_no_email_rows(script_url, sid)
        print(f"Removed {removed} rows from Sheets.")
    except Exception as exc:
        print(f"Sheet purge failed (redeploy Code.gs first): {exc}")


if __name__ == "__main__":
    main()

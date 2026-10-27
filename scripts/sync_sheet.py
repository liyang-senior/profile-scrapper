"""Re-push candidates.csv to Google Sheets (updates missing photos/emails on existing rows)."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parse.role_groups import role_to_tab
from pipeline import resolve_csv_path
from settings import load_settings
from sheets.writer import push_csv


def main() -> None:
    settings = load_settings()
    csv_path = resolve_csv_path(settings, fetch=True)
    script_url = (settings.get("apps_script_url") or "").strip()
    sheet_url = (settings.get("google_sheet_url") or "").strip()
    if not script_url or not sheet_url:
        print("Set apps_script_url and google_sheet_url in config/user_settings.json")
        return
    if not csv_path.exists():
        print(f"No CSV at {csv_path}")
        return

    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        if not row.get("role_tab"):
            row["role_tab"] = role_to_tab(row.get("role") or "")

    print(f"Syncing {len(rows)} rows to Google Sheets (existing rows get photo/email fixes)…")
    counts = push_csv(csv_path, script_url, sheet_url, log_fn=print)
    print("Done:", counts)


if __name__ == "__main__":
    main()

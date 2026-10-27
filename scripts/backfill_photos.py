"""Fill empty photo cells in candidates.csv using getprog-style fallbacks."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from extract.profile_photo import resolve_profile_photo
from pipeline import resolve_csv_path
from settings import load_settings


def main() -> None:
    csv_path = resolve_csv_path(load_settings(), fetch=True)
    if not csv_path.exists():
        print(f"No CSV at {csv_path}")
        return

    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("CSV is empty")
        return

    fieldnames = list(rows[0].keys())
    updated = 0

    for row in rows:
        if (row.get("photo") or "").strip():
            continue
        name = (row.get("name") or "").strip()
        parts = name.split()
        profile = {
            "full_name": name,
            "first_name": parts[0] if parts else "",
            "last_name": parts[-1] if len(parts) > 1 else "",
            "profile_pic_url": "",
            "github_url": row.get("github_url") or "",
            "linkedin_url": row.get("linkedin_url") or "",
        }
        row["photo"] = resolve_profile_photo(profile)
        updated += 1

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Updated {updated} empty photo cells in {csv_path}")


if __name__ == "__main__":
    main()

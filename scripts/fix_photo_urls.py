"""Restore working photo URLs in candidates.csv (fix broken S3 / missing photos)."""
import csv
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from extract.profile_photo import (
    is_getprog_photo,
    photo_url_is_accessible,
    profile_from_csv_row,
    resolve_profile_photo,
)
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

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        for row in rows:
            photo = (row.get("photo") or "").strip()
            if photo and is_getprog_photo(photo) and photo_url_is_accessible(photo, client):
                continue

            profile = profile_from_csv_row(row)
            if photo:
                profile["profile_pic_url"] = photo

            new_photo = resolve_profile_photo(profile, http_client=client)
            if new_photo and new_photo != photo:
                row["photo"] = new_photo
                updated += 1

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Fixed {updated} photo URLs in {csv_path}")


if __name__ == "__main__":
    main()

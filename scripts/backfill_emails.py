"""Re-fetch emails from getprog for CSV rows that are missing them."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx

from auth.getprog_session import ensure_authenticated, API_BASE
from extract.api_client import _extract_emails, _fetch_full_profile, _profile_has_emails
from pipeline import resolve_csv_path
from settings import load_settings


def _row_has_email(row: dict) -> bool:
    return bool((row.get("email") or "").strip())


def main() -> None:
    settings = load_settings()
    csv_path = resolve_csv_path(settings, fetch=True)
    if not csv_path.exists():
        print(f"No CSV at {csv_path}")
        return

    email = (settings.get("getprog_email") or "").strip()
    password = settings.get("getprog_password") or ""
    if not email or not password:
        print("Set getprog email/password in config/user_settings.json")
        return

    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("CSV is empty")
        return

    token = ensure_authenticated(email, password)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Referer": "https://app.getprog.ai/",
        "Origin": "https://app.getprog.ai",
    }

    updated = 0
    skipped = 0
    with httpx.Client(base_url=API_BASE, headers=headers, timeout=120.0) as client:
        for row in rows:
            if _row_has_email(row):
                continue
            linkedin = (row.get("linkedin_url") or "").strip()
            if not linkedin:
                skipped += 1
                continue
            search_body = {
                "text": (row.get("name") or "").strip(),
                "page": 0,
                "size": 5,
                "with_emails": True,
            }
            resp = client.post("/api/search/", json=search_body)
            if resp.status_code != 200:
                skipped += 1
                continue
            pid = None
            for item in resp.json().get("results") or []:
                profile = item.get("profile") or {}
                if (profile.get("linkedin_url") or "").strip().lower() == linkedin.lower():
                    pid = profile.get("id")
                    break
                if (row.get("name") or "").strip().lower() == str(profile.get("full_name") or "").lower():
                    pid = profile.get("id")
            if not pid:
                skipped += 1
                continue
            extra = _fetch_full_profile(client, int(pid))
            if not extra:
                skipped += 1
                continue
            profile = dict(extra)
            if not _profile_has_emails(profile):
                skipped += 1
                continue
            emails = _extract_emails(profile.get("emails"))
            primary = str(profile.get("primary_email") or "").strip()
            if primary and primary.lower() not in {e.lower() for e in emails}:
                emails = [primary] + emails
            row["email"] = "\n".join(emails)
            updated += 1
            print(f"  {row.get('name', '')}: {row['email'][:60]}")

    if updated:
        fieldnames = list(rows[0].keys())
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    print(f"Updated {updated} email cells in {csv_path} ({skipped} still missing)")


if __name__ == "__main__":
    main()

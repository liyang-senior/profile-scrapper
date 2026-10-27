#!/usr/bin/env python3
import argparse
import sys

from auth.getprog_session import login_getprog
from pipeline import run_scrape
from settings import load_settings


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--login", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    s = load_settings()

    if args.login:
        login_getprog(s["getprog_email"], s["getprog_password"], headless=False)
        print("OK - storage_state.json")
    elif args.run or args.dry_run:
        r = run_scrape(s, dry_run=args.dry_run)
        if r.get("stopped"):
            print("Stopped by user")
        else:
            print(
                f"{r.get('new_count', 0)} new rows -> {r['csv_path']} "
                f"({r.get('total_csv_rows', '?')} total, {r.get('skipped', 0)} skipped)"
            )
    else:
        p.print_help()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)

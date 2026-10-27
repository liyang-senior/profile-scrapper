#!/usr/bin/env python3
"""App entry point — Streamlit UI, or scrape worker when launched with --scrape."""
from __future__ import annotations

import sys
from pathlib import Path


def _run_scrape() -> None:
    # drop "--scrape" so scrape_getprog argparse sees --run / --dry-run / --login
    sys.argv = [sys.argv[0], *sys.argv[2:]]
    from scrape_getprog import main as scrape_main

    scrape_main()


def _run_streamlit() -> None:
    from settings import bundle_dir, ensure_runtime_layout, is_frozen

    ensure_runtime_layout()

    import streamlit.web.cli as stcli

    if is_frozen():
        app_path = bundle_dir() / "app.py"
    else:
        app_path = Path(__file__).resolve().parent / "app.py"

    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.headless=true",
        "--global.developmentMode=false",
        "--browser.gatherUsageStats=false",
    ]
    raise SystemExit(stcli.main())


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--scrape":
        _run_scrape()
    else:
        _run_streamlit()


if __name__ == "__main__":
    main()

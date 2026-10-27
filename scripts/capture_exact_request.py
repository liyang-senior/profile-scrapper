"""Intercept exact search request from browser."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from settings import load_settings

s = load_settings()
requests = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(ROOT / "storage_state_test.json"))
        page = ctx.new_page()

        def on_request(req):
            if "/api/search/" in req.url and req.method == "POST":
                requests.append(
                    {
                        "url": req.url,
                        "headers": req.headers,
                        "post_data": req.post_data,
                        "post_data_json": req.post_data_json,
                    }
                )

        page.on("request", on_request)
        page.goto(s["search_url"], wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(3000)
        browser.close()

    out = ROOT / "logs" / "search_request_exact.json"
    out.write_text(json.dumps(requests, indent=2), encoding="utf-8")
    print(out.read_text(encoding="utf-8")[:5000])


if __name__ == "__main__":
    main()

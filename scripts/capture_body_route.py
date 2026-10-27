"""Route intercept to read search POST body bytes."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from settings import load_settings

s = load_settings()
captured = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(ROOT / "storage_state_test.json"))
        page = ctx.new_page()

        def handle(route, request):
            if "/api/search/" in request.url and request.method == "POST":
                captured.append(
                    {
                        "url": request.url,
                        "headers": request.headers,
                        "post_data": request.post_data,
                        "post_data_buffer": request.post_data_buffer.decode("utf-8", errors="replace")
                        if request.post_data_buffer
                        else None,
                    }
                )
            route.continue_()

        page.route("**/*", handle)
        page.goto(s["search_url"], wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(3000)

        # profile click - intercept profile API
        cards = page.locator("[class*='profile'], [class*='candidate'], article").first
        if cards.count():
            page.on("request", lambda req: captured.append({"profile_req": req.url, "method": req.method, "data": req.post_data}) if "api.app.getprog" in req.url and req.method in ("GET", "POST") and "search" not in req.url else None)

        browser.close()

    print(json.dumps(captured, indent=2)[:8000])


if __name__ == "__main__":
    main()

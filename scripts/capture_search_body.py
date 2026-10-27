"""Capture search POST body and profile detail endpoints."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from settings import load_settings

s = load_settings()
search_posts = []
profile_calls = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(ROOT / "storage_state_test.json"))
        page = ctx.new_page()

        def on_request(req):
            if "api.app.getprog.ai" not in req.url:
                return
            if "/api/search/" in req.url and req.method == "POST":
                search_posts.append({"url": req.url, "body": req.post_data})
            if "profile" in req.url.lower() or "get_profile" in req.url.lower():
                profile_calls.append({"url": req.url, "method": req.method, "body": req.post_data})

        def on_response(resp):
            url = resp.url
            if "/api/search/" in url and resp.request.method == "POST" and resp.ok:
                try:
                    body = resp.json()
                    if body.get("results"):
                        r0 = body["results"][0]
                        search_posts.append(
                            {
                                "sample_result_keys": list(r0.keys()),
                                "profile_keys": list(r0.get("profile", {}).keys())[:30],
                            }
                        )
                except Exception:
                    pass
            if ("profile" in url.lower() or "get-profile" in url.lower()) and resp.ok:
                try:
                    profile_calls.append(
                        {"url": url, "response_keys": list(resp.json().keys())}
                    )
                except Exception:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)
        page.goto(s["search_url"], wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(3000)

        # click first profile link if any
        link = page.locator("a[href*='profile'], a[href*='candidate']").first
        if link.count():
            href = link.get_attribute("href")
            profile_calls.append({"clicked_href": href})
            link.click()
            page.wait_for_timeout(5000)

        browser.close()

    out = ROOT / "logs" / "search_body_discovery.json"
    out.write_text(json.dumps({"search": search_posts, "profiles": profile_calls}, indent=2), encoding="utf-8")
    print(out.read_text(encoding="utf-8")[:4000])


if __name__ == "__main__":
    main()

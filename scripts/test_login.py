"""Test login flow and capture getprog API calls."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from settings import ROOT, load_settings

s = load_settings()
captured = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()

        def on_response(resp):
            try:
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                url = resp.url
                if "mixpanel" in url:
                    return
                entry = {
                    "url": url,
                    "status": resp.status,
                    "method": resp.request.method,
                }
                if resp.ok and "json" in resp.headers.get("content-type", ""):
                    body = resp.json()
                    if isinstance(body, dict):
                        entry["keys"] = list(body.keys())
                        if "results" in body:
                            entry["results_len"] = len(body["results"])
                captured.append(entry)
            except Exception as ex:
                captured.append({"url": resp.url, "error": str(ex)})

        page.on("response", on_response)
        page.goto("https://app.getprog.ai/login", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        email_sel = 'input[type="email"], input[name="email"]'
        if page.locator(email_sel).count():
            page.locator(email_sel).first.fill(s["getprog_email"])

        cont = page.locator(
            'button:has-text("Continue"), button:has-text("continue"), button:has-text("email")'
        )
        if cont.count():
            cont.first.click()
        page.wait_for_timeout(3000)

        pass_sel = 'input[type="password"]'
        page.wait_for_selector(pass_sel, timeout=30000)
        page.locator(pass_sel).first.fill(s["getprog_password"])

        submit = page.locator(
            'button[type="submit"], button:has-text("Sign in"), button:has-text("Log in")'
        )
        if submit.count():
            submit.first.click()
        page.wait_for_timeout(8000)

        print("after login url:", page.url)

        page.goto(s["search_url"], wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(5000)
        print("search url:", page.url)

        ls = page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
        cookies = ctx.cookies()
        ctx.storage_state(path=str(ROOT / "storage_state_test.json"))
        browser.close()

    out = {
        "captured": captured,
        "localStorage": {k: (v[:300] if len(v) > 300 else v) for k, v in ls.items()},
        "cookie_names": [c["name"] for c in cookies],
    }
    path = ROOT / "logs" / "login_discovery.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("api calls:", len(captured))
    for c in captured:
        if "api" in c.get("url", "") or c.get("results_len"):
            print(c)
    print("cookies:", [c["name"] for c in cookies])
    print("ls keys:", list(ls.keys()))


if __name__ == "__main__":
    main()

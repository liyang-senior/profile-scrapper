"""Test Playwright request API with auth from storage."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from settings import load_settings

s = load_settings()


def auth_headers(page):
    tokens = json.loads(page.evaluate("() => localStorage.getItem('authTokens')"))
    return {
        "Authorization": f"Bearer {tokens['accessToken']}",
        "Origin": "https://app.getprog.ai",
        "Referer": "https://app.getprog.ai/",
        "Content-Type": "application/json",
    }


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(ROOT / "storage_state_test.json"))
        page = ctx.new_page()
        page.goto("https://app.getprog.ai/search", wait_until="domcontentloaded")
        hdrs = auth_headers(page)
        req = ctx.request

        body = {
            "locations": ["California"],
            "seniority": ["Senior"],
            "text": "Senior machine learning engineers with knowledge of LLMs\n",
            "page": 0,
            "size": 100,
        }

        for pg in [0, 1]:
            body["page"] = pg
            r = req.post("https://api.app.getprog.ai/api/search/", headers=hdrs, data=json.dumps(body))
            data = r.json()
            print(f"page {pg}: status={r.status} results={len(data.get('results', []))} total={data.get('results_count')}")

        pid = data["results"][0]["profile"]["id"]

        for params in [
            {"id": pid},
            {"id": pid, "with_emails": "true"},
            {"id": pid, "full_profile": "true"},
        ]:
            for path in [
                "/api/get-profile/",
                "/api/profile/",
                "/api/profiles/detail/",
            ]:
                rr = req.get(f"https://api.app.getprog.ai{path}", headers=hdrs, params=params)
                if rr.status != 404:
                    print(f"GET {path} {params} -> {rr.status}", rr.text()[:250])

        for extra in [{"full_profiles": True}, {"with_emails": True}, {"full_profiles": True, "with_emails": True}]:
            b = {**body, "page": 0, **extra}
            rr = req.post("https://api.app.getprog.ai/api/search/", headers=hdrs, data=json.dumps(b))
            prof = rr.json()["results"][0]["profile"]
            print(
                "search extra",
                extra,
                "email=",
                prof.get("primary_email"),
                "work_exp=",
                prof.get("work_experiences") is not None,
            )

        browser.close()


if __name__ == "__main__":
    main()

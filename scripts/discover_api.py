"""One-off: capture XHR/fetch URLs while loading a getprog search page."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from auth.getprog_session import STORAGE_FILE, login_getprog
from settings import load_settings


def main():
    s = load_settings()
    if not STORAGE_FILE.exists():
        login_getprog(s["getprog_email"], s["getprog_password"], headless=False)

    captured = []
    search_url = s.get("search_url") or ""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(storage_state=str(STORAGE_FILE))
        page = ctx.new_page()

        def on_response(resp):
            try:
                rt = resp.request.resource_type
                if rt not in ("xhr", "fetch"):
                    return
                ct = resp.headers.get("content-type", "")
                entry = {
                    "url": resp.url,
                    "status": resp.status,
                    "method": resp.request.method,
                    "content_type": ct,
                }
                if resp.ok and "json" in ct:
                    body = resp.json()
                    entry["body_keys"] = list(body.keys()) if isinstance(body, dict) else type(body).__name__
                    if isinstance(body, dict):
                        for k in ("results", "candidates", "profiles", "data", "items", "hits", "total"):
                            if k in body:
                                entry[f"has_{k}"] = True
                                if isinstance(body[k], list):
                                    entry[f"{k}_len"] = len(body[k])
                captured.append(entry)
            except Exception as e:
                captured.append({"url": resp.url, "error": str(e)})

        page.on("response", on_response)
        page.goto(search_url, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(5000)
        browser.close()

    out = ROOT / "logs" / "api_discovery.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(captured, indent=2), encoding="utf-8")
    print(f"Saved {len(captured)} entries -> {out}")
    for c in captured:
        if c.get("body_keys") or "search" in c.get("url", "").lower():
            print(c)


if __name__ == "__main__":
    main()

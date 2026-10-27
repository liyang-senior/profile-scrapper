"""Capture one live /api/search/ POST from the getprog web UI and compare to our builder."""
import json
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from auth.getprog_session import ensure_authenticated, login_getprog
from extract.search_params import build_search_body
from settings import ROOT as PROJECT, load_settings

OUT = PROJECT / "logs" / "api_compare.json"


def main() -> None:
    s = load_settings()
    search = s.get("search") or {}
    our = build_search_body(search, page=0, size=100)
    our_with = dict(our)
    our_with["with_emails"] = True

    email = s["getprog_email"]
    password = s["getprog_password"]
    login_getprog(email, password, headless=True)
    ensure_authenticated(email, password)

    text = quote(str(search.get("text") or "AI Engineer"))
    countries = search.get("countries") or ["United States"]
    locations = search.get("locations") or []
    seniority = search.get("seniority") or []
    qs = [f"text={text}", "page=0", "size=100"]
    for c in countries:
        qs.append(f"countries[]={quote(str(c))}")
    for loc in locations:
        qs.append(f"locations[]={quote(str(loc))}")
    for sen in seniority:
        qs.append(f"seniority[]={quote(str(sen))}")
    if search.get("is_first_name_female"):
        qs.append("is_first_name_female=true")
    for yo in search.get("yo_experience") or []:
        qs.append(f"yo_experience[]={quote(str(yo))}")
    url = "https://app.getprog.ai/search/results?" + "&".join(qs)

    captured = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(PROJECT / "storage_state.json"))
        page = ctx.new_page()

        def on_request(req):
            if "/api/search/" in req.url and req.method == "POST":
                captured.append(
                    {
                        "url": req.url,
                        "post_data_json": req.post_data_json,
                        "headers": {
                            k: v
                            for k, v in (req.headers or {}).items()
                            if k.lower() in ("content-type", "authorization", "origin", "referer")
                        },
                    }
                )

        page.on("request", on_request)
        page.goto(url, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(4000)
        browser.close()

    web = captured[0]["post_data_json"] if captured else None
    report = {
        "page_url": url,
        "captured_count": len(captured),
        "web_body": web,
        "our_body": our,
        "our_body_with_emails": our_with,
        "keys_only_on_web": sorted(set(web or {}) - set(our_with)),
        "keys_only_on_ours": sorted(set(our_with) - set(web or {})),
        "value_diffs": {},
    }
    if web:
        for k in sorted(set(web) | set(our_with)):
            if web.get(k) != our_with.get(k):
                report["value_diffs"][k] = {"web": web.get(k), "ours": our_with.get(k)}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False)[:8000])


if __name__ == "__main__":
    main()

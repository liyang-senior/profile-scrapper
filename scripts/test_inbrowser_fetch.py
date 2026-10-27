"""Test in-browser fetch for search + profile APIs."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from auth.getprog_session import login_getprog
from settings import load_settings

s = load_settings()


def main():
    login_getprog(s["getprog_email"], s["getprog_password"], headless=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(ROOT / "storage_state.json"))
        page = ctx.new_page()
        page.goto(s["search_url"], wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(2000)

        sub = page.evaluate(
            """async () => {
            const r = await fetch('https://api.app.getprog.ai/api/users/current/subscription/', {
                headers: { Authorization: 'Bearer ' + JSON.parse(localStorage.authTokens).accessToken }
            });
            return r.json();
        }"""
        )
        print("subscription:", sub)

        search_result = page.evaluate(
            """async () => {
            const token = JSON.parse(localStorage.authTokens).accessToken;
            const body = {
                locations: ['California'],
                seniority: ['Senior'],
                text: 'Senior machine learning engineers with knowledge of LLMs\\n',
                page: 1,
                size: 100,
            };
            const r = await fetch('https://api.app.getprog.ai/api/search/', {
                method: 'POST',
                headers: {
                    Authorization: 'Bearer ' + token,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(body),
            });
            const data = await r.json();
            return { status: r.status, count: data.results?.length, total: data.results_count, detail: data.detail, pid: data.results?.[0]?.profile?.id };
        }"""
        )
        print("search page 1:", search_result)

        if search_result.get("pid"):
            pid = search_result["pid"]
            for extra in [
                {},
                {"with_emails": True},
                {"full_profiles": True},
                {"full_profiles": True, "with_emails": True},
            ]:
                prof = page.evaluate(
                    """async (args) => {
                    const token = JSON.parse(localStorage.authTokens).accessToken;
                    const paths = [
                        ['GET', 'https://api.app.getprog.ai/api/get-profile/?id=' + args.pid + '&with_emails=true'],
                        ['POST', 'https://api.app.getprog.ai/api/get-profile/'],
                    ];
                    const out = [];
                    for (const [method, url] of paths) {
                        const opts = { method, headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' } };
                        if (method === 'POST') opts.body = JSON.stringify({ id: args.pid, ...args.extra });
                        const r = await fetch(url, opts);
                        const t = await r.text();
                        out.push({ url, status: r.status, preview: t.slice(0, 300) });
                    }
                    return out;
                }""",
                    {"pid": pid, "extra": extra},
                )
                print("profile fetch", extra, prof)

        browser.close()


if __name__ == "__main__":
    main()

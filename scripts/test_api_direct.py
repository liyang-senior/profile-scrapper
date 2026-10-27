"""Direct API tests using saved auth tokens."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx

from settings import load_settings

state = json.loads((ROOT / "storage_state_test.json").read_text(encoding="utf-8"))
ls = next(o["localStorage"] for o in state["origins"] if o["origin"] == "https://app.getprog.ai")
tokens = json.loads(next(x["value"] for x in ls if x["name"] == "authTokens"))
access = tokens["accessToken"]

s = load_settings()
headers = {"Authorization": f"Bearer {access}", "Content-Type": "application/json"}

# parse search URL params
from urllib.parse import parse_qs, urlparse

parsed = urlparse(s["search_url"])
qs = parse_qs(parsed.query, keep_blank_values=True)

def first(key, default=""):
    v = qs.get(key, [default])
    return v[0] if v else default

def list_vals(key):
    return qs.get(key, [])

payload = {
    "text": first("text"),
    "locations": list_vals("locations[]") or list_vals("locations"),
    "seniority": list_vals("seniority[]") or list_vals("seniority"),
    "size": int(first("size", "100") or 100),
    "page": 0,
}
print("payload", json.dumps(payload, indent=2))

client = httpx.Client(base_url="https://api.app.getprog.ai", headers=headers, timeout=120)

for page in [0, 1]:
    payload["page"] = page
    r = client.post("/api/search/", json=payload)
    print(f"page {page} status", r.status_code)
    if r.status_code != 200:
        print(r.text[:500])
        break
    data = r.json()
    print(f"  results_count={data.get('results_count')} len={len(data.get('results', []))}")

# try profile endpoints
pid = data["results"][0]["profile"]["id"]
for path, params in [
    ("/api/get_profile/", {"id": pid}),
    ("/api/profile/", {"id": pid}),
    (f"/api/profiles/{pid}/", None),
    ("/api/get_profile/", {"id": pid, "with_emails": True}),
    ("/api/search/profile/", {"id": pid}),
]:
    try:
        if params:
            r = client.get(path, params=params)
        else:
            r = client.get(path)
        print(path, params, "->", r.status_code, list(r.json().keys()) if r.status_code == 200 and r.headers.get('content-type','').startswith('application/json') else r.text[:100])
    except Exception as e:
        print(path, "err", e)

# try search with full_profiles / with_emails in POST body
for extra in [{"full_profiles": True}, {"with_emails": True}, {"full_profiles": True, "with_emails": True}]:
    p = {**payload, "page": 0, **extra}
    r = client.post("/api/search/", json=p)
    prof = r.json()["results"][0]["profile"]
    print("extra", extra, "email", prof.get("primary_email"), "emails", prof.get("emails"), "work_exp", prof.get("work_experiences") is not None)

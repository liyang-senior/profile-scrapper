"""POST rows to Google Apps Script web app (/exec or /dev)."""
import json
from typing import Any, Callable, Dict, List, Optional

import httpx

from extract.api_client import _join_lines, row_has_email
from sheets.sheet_url import extract_spreadsheet_id

BATCH_SIZE = 40
DEFAULT_TIMEOUT = 180.0


def normalize_apps_script_url(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if not u:
        raise ValueError("Apps Script URL is empty.")
    if not u.lower().endswith(("/exec", "/dev")):
        raise ValueError("Apps Script URL must end with /exec or /dev")
    return u


def check_apps_script_url(
    web_app_url: str,
    spreadsheet_id: Optional[str] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Ping the web app with GET (doGet)."""
    url = normalize_apps_script_url(web_app_url)
    params = {}
    if spreadsheet_id:
        params["spreadsheet_id"] = spreadsheet_id
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, params=params)
    return _parse_response(resp, web_app_url=url)


def fetch_spreadsheet_info(
    web_app_url: str,
    sheet_url: str,
    timeout: float = 30.0,
) -> Dict[str, str]:
    """Return {name, id} for the spreadsheet (name is the Google Sheets file title)."""
    sid = extract_spreadsheet_id(sheet_url)
    if not sid:
        raise ValueError("Could not read spreadsheet ID from Google Sheet URL.")
    result = check_apps_script_url(web_app_url, spreadsheet_id=sid, timeout=timeout)
    name = str(result.get("spreadsheet") or "").strip()
    if not name:
        raise RuntimeError("Apps Script did not return the spreadsheet name.")
    return {"name": name, "id": sid}


def _parse_response(resp: httpx.Response, web_app_url: str = "") -> Dict[str, Any]:
    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError(f"Empty response (HTTP {resp.status_code}). Check Apps Script deployment.")

    if text.lstrip().startswith("<"):
        hint = " Redeploy as Web app with Who has access: Anyone."
        if resp.status_code == 401 and web_app_url.lower().endswith("/dev"):
            hint = (
                " HTTP 401 on /dev — use Deploy → Test deployments → copy the test URL, "
                "or create a New deployment (/exec) with Anyone access."
            )
        elif resp.status_code == 401:
            hint = " HTTP 401 — set Who has access: Anyone on the web app deployment."
        raise RuntimeError(f"Got HTML instead of JSON (HTTP {resp.status_code}).{hint}")

    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON (HTTP {resp.status_code}): {text[:200]}") from exc

    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(str(data["error"]))
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {data}")

    return data if isinstance(data, dict) else {"ok": True, "raw": data}


def _post_batch(
    client: httpx.Client,
    post_url: str,
    candidates: List[Dict[str, Any]],
    spreadsheet_id: str,
) -> Dict[str, Any]:
    payload = {
        "spreadsheet_id": spreadsheet_id,
        "candidates": [
            {
                "photo": c.get("photo", ""),
                "name": c.get("name", ""),
                "email": c.get("email", ""),
                "sender": c.get("sender", ""),
                "sent": c.get("sent", ""),
                "role": c.get("role", ""),
                "current_company": c.get("current_company", ""),
                "years_experience": c.get("years_experience", ""),
                "github_url": c.get("github_url", ""),
                "linkedin_url": c.get("linkedin_url", ""),
                "location": c.get("location", ""),
                "languages": _join_lines(c.get("languages", "")),
                "phone_numbers": _join_lines(c.get("phone_numbers", "")),
                "role_tab": c.get("role_tab", "Other"),
            }
            for c in candidates
            if row_has_email(c)
        ],
    }
    resp = client.post(
        post_url,
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    data = _parse_response(resp, web_app_url=post_url)
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "Upload failed"))
    return data.get("counts", {})


def purge_no_email_rows(
    web_app_url: str,
    spreadsheet_id: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> int:
    """Ask Apps Script to delete sheet rows that have no email."""
    sid = extract_spreadsheet_id(spreadsheet_id) or spreadsheet_id
    post_url = normalize_apps_script_url(web_app_url)
    payload = {"spreadsheet_id": sid, "purge_no_email": True, "candidates": []}
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.post(
            post_url,
            content=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
    data = _parse_response(resp, web_app_url=post_url)
    return int(data.get("purged") or 0)


def _count_uploaded(counts: Dict[str, Any]) -> int:
    """Rows actually appended this batch (avoid double-counting tab totals + _appended)."""
    if counts.get("_appended") is not None:
        return int(counts["_appended"])
    return sum(int(n or 0) for k, n in counts.items() if not str(k).startswith("_"))


def push_via_apps_script(
    candidates: List[Dict[str, Any]],
    web_app_url: str,
    spreadsheet_id: str,
    timeout: float = DEFAULT_TIMEOUT,
    batch_size: int = BATCH_SIZE,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, int]:
    if not candidates:
        return {}

    sid = extract_spreadsheet_id(spreadsheet_id) or spreadsheet_id
    if not sid:
        raise ValueError("Invalid Google Sheet URL or spreadsheet ID.")

    post_url = normalize_apps_script_url(web_app_url)
    merged: Dict[str, int] = {}
    total_appended = 0
    total = len(candidates)
    batches = (total + batch_size - 1) // batch_size

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for i, start in enumerate(range(0, total, batch_size)):
            batch = candidates[start : start + batch_size]
            if log_fn:
                log_fn(f"  Upload batch {i + 1}/{batches} ({len(batch)} rows)…")
            counts = _post_batch(client, post_url, batch, sid)
            uploaded = _count_uploaded(counts)
            total_appended += uploaded
            if log_fn:
                log_fn(f"  Batch {i + 1} uploaded: {uploaded} rows -> tabs {counts}")
            for tab, n in counts.items():
                if str(tab).startswith("_"):
                    continue
                merged[tab] = merged.get(tab, 0) + int(n or 0)

    if total_appended:
        merged["_appended"] = total_appended
    return merged

"""getprog.ai login and session persistence."""
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Module-level token cache: avoids re-validating the JWT on every autocomplete keystroke.
# Key = lowercased email; value = (access_token, expires_at_unix).
_token_cache: Dict[str, Tuple[str, float]] = {}
_TOKEN_TTL = 240.0  # 4 minutes — well within a typical JWT lifetime

import httpx
from playwright.sync_api import Page, sync_playwright

from settings import ROOT

STORAGE_FILE = ROOT / "storage_state.json"
LOGIN_URL = "https://app.getprog.ai/login"
APP_ORIGIN = "https://app.getprog.ai"
API_BASE = "https://api.app.getprog.ai"


def storage_path() -> Path:
    return STORAGE_FILE


def _fill_email(page: Page, email: str) -> None:
    email_sel = 'input[type="email"], input[name="email"], input[autocomplete="email"]'
    page.wait_for_selector(email_sel, timeout=30000)
    page.locator(email_sel).first.fill(email)


def _click_continue(page: Page) -> None:
    btn = page.locator(
        'button:has-text("Continue"), button:has-text("continue"), '
        'button[type="submit"]:has-text("email")'
    )
    if btn.count():
        btn.first.click()
        return
    page.keyboard.press("Enter")


def _fill_password_and_submit(page: Page, password: str) -> None:
    pass_sel = 'input[type="password"], input[name="password"]'
    page.wait_for_selector(pass_sel, timeout=60000)
    page.locator(pass_sel).first.fill(password)
    submit = page.locator(
        'button[type="submit"], button:has-text("Sign in"), button:has-text("Log in")'
    )
    if submit.count():
        submit.first.click()
    else:
        page.keyboard.press("Enter")


def _wait_for_auth(page: Page, timeout_ms: int = 90000) -> None:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        tokens = page.evaluate("() => localStorage.getItem('authTokens')")
        if tokens:
            return
        if "/login" not in page.url and "/sign-in" not in page.url:
            page.wait_for_timeout(1000)
            tokens = page.evaluate("() => localStorage.getItem('authTokens')")
            if tokens:
                return
        page.wait_for_timeout(500)
    raise RuntimeError("Login timed out — complete sign-in in the browser window if shown.")


def _load_storage_state() -> dict:
    if STORAGE_FILE.exists():
        try:
            return json.loads(STORAGE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"cookies": [], "origins": []}


def save_auth_tokens(access: str, refresh: str) -> Path:
    """Persist getprog tokens in Playwright storage_state format."""
    state = _load_storage_state()
    token_value = json.dumps({"accessToken": access, "refreshToken": refresh})

    origin_entry = None
    for origin in state.setdefault("origins", []):
        if origin.get("origin") == APP_ORIGIN:
            origin_entry = origin
            break

    if origin_entry is None:
        origin_entry = {"origin": APP_ORIGIN, "localStorage": []}
        state["origins"].append(origin_entry)

    ls = origin_entry.setdefault("localStorage", [])
    for item in ls:
        if item.get("name") == "authTokens":
            item["value"] = token_value
            break
    else:
        ls.append({"name": "authTokens", "value": token_value})

    STORAGE_FILE.write_text(json.dumps(state), encoding="utf-8")
    return STORAGE_FILE


def login_via_api(email: str, password: str) -> Path:
    """Sign in via getprog REST API (fast, works headless)."""
    email = (email or "").strip()
    password = password or ""
    if not email or not password:
        raise ValueError("Email and password are required.")

    with httpx.Client(base_url=API_BASE, timeout=60.0) as client:
        client.post("/api/users/exists/", json={"email": email})
        resp = client.post("/api/sign-in/", json={"email": email, "password": password})

    if resp.status_code != 200:
        detail = resp.text[:300]
        raise RuntimeError(f"Login failed (HTTP {resp.status_code}): {detail}")

    data = resp.json()
    access = data.get("access")
    refresh = data.get("refresh")
    if not access:
        raise RuntimeError("Login failed — no access token in response.")

    return save_auth_tokens(access, refresh or "")


def _fetch_current_user(access_token: str) -> Optional[Dict[str, Any]]:
    try:
        with httpx.Client(base_url=API_BASE, timeout=30.0) as client:
            resp = client.get(
                "/api/users/current/",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code != 200:
            return None
        return resp.json()
    except httpx.HTTPError:
        return None


def _fetch_subscription(access_token: str) -> Dict[str, Any]:
    try:
        with httpx.Client(base_url=API_BASE, timeout=30.0) as client:
            resp = client.get(
                "/api/users/current/subscription/",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code != 200:
            return {}
        return resp.json() or {}
    except httpx.HTTPError:
        return {}


def get_refresh_token() -> Optional[str]:
    tokens = _read_auth_tokens()
    return tokens.get("refreshToken") if tokens else None


def _refresh_access_token(refresh_token: str) -> Optional[str]:
    try:
        with httpx.Client(base_url=API_BASE, timeout=30.0) as client:
            resp = client.post("/api/token/refresh/", json={"refresh": refresh_token})
        if resp.status_code != 200:
            return None
        data = resp.json()
        access = data.get("access")
        if not access:
            return None
        save_auth_tokens(access, data.get("refresh") or refresh_token)
        return access
    except httpx.HTTPError:
        return None


def _resolve_valid_token(email: str = "", password: str = "", *, allow_login: bool = False) -> Optional[str]:
    """Return a working access token, refreshing or logging in only when allowed."""
    token = get_access_token()
    if token and _fetch_current_user(token):
        return token

    refresh = get_refresh_token()
    if refresh:
        new_token = _refresh_access_token(refresh)
        if new_token and _fetch_current_user(new_token):
            return new_token

    if allow_login and email and password:
        login_via_api(email, password)
        token = get_access_token()
        if token and _fetch_current_user(token):
            return token

    return None


def check_login_status(
    email: str = "",
    password: str = "",
    *,
    allow_login: bool = False,
) -> Dict[str, Any]:
    """Verify login against getprog API (not just local file)."""
    email = (email or "").strip()
    password = password or ""

    try:
        token = _resolve_valid_token(email, password, allow_login=allow_login)
    except Exception as exc:
        return {
            "logged_in": False,
            "email": email,
            "message": str(exc),
            "requests_left": None,
            "requests_limit": None,
        }

    if not token:
        return {
            "logged_in": False,
            "email": email or "",
            "message": "Not logged in — click **Login getprog** or check email/password in the sidebar.",
            "requests_left": None,
            "requests_limit": None,
        }

    user = _fetch_current_user(token)
    if user is None:
        return {
            "logged_in": False,
            "email": email or "",
            "message": "Session expired — click **Login getprog** to sign in again.",
            "requests_left": None,
            "requests_limit": None,
        }

    sub = _fetch_subscription(token)
    requests_left = sub.get("requests_left")
    requests_limit = sub.get("requests_limit")
    display_email = user.get("email") or email
    msg = f"Logged in as {display_email}"
    if requests_left is not None:
        limit_note = f" (limit {requests_limit})" if requests_limit is not None else ""
        msg += f" — {requests_left} search credits remaining{limit_note}"

    return {
        "logged_in": True,
        "email": display_email,
        "message": msg,
        "requests_left": requests_left,
        "requests_limit": requests_limit,
    }


def ensure_authenticated(email: str, password: str) -> str:
    """Return a valid access token, logging in again if needed.

    The result is cached for _TOKEN_TTL seconds so repeated calls (e.g. from
    autocomplete on every keystroke) don't each fire an HTTP validation request.
    """
    key = (email or "").strip().lower()
    cached_token, expires_at = _token_cache.get(key, ("", 0.0))
    if cached_token and time.time() < expires_at:
        return cached_token

    status = check_login_status(email, password, allow_login=True)
    if not status["logged_in"]:
        _token_cache.pop(key, None)
        raise RuntimeError(status.get("message") or "Could not log in to getprog.ai")

    token = get_access_token()
    if not token:
        raise RuntimeError("Login succeeded but no access token was saved.")

    _token_cache[key] = (token, time.time() + _TOKEN_TTL)
    return token


def invalidate_token_cache(email: str = "") -> None:
    """Force the next ensure_authenticated call to re-validate (e.g. after logout)."""
    if email:
        _token_cache.pop((email or "").strip().lower(), None)
    else:
        _token_cache.clear()


def login_getprog(email: str, password: str, headless: bool = False) -> Path:
    """Log in to getprog and save session tokens."""
    try:
        return login_via_api(email, password)
    except Exception:
        pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)

        _fill_email(page, email)
        _click_continue(page)
        page.wait_for_timeout(2000)

        _fill_password_and_submit(page, password)
        _wait_for_auth(page)

        page.goto("https://app.getprog.ai/search", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        tokens_raw = page.evaluate("() => localStorage.getItem('authTokens')")
        if not tokens_raw:
            browser.close()
            raise RuntimeError("Browser login finished but authTokens were not set.")

        context.storage_state(path=str(STORAGE_FILE))
        browser.close()

    return STORAGE_FILE


def _read_auth_tokens() -> Optional[dict]:
    if not STORAGE_FILE.exists():
        return None
    try:
        state = json.loads(STORAGE_FILE.read_text(encoding="utf-8"))
        for origin in state.get("origins", []):
            if origin.get("origin") != APP_ORIGIN:
                continue
            for item in origin.get("localStorage", []):
                if item.get("name") == "authTokens":
                    return json.loads(item["value"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    return None


def has_session() -> bool:
    tokens = _read_auth_tokens()
    return bool(tokens and tokens.get("accessToken"))


def get_access_token() -> Optional[str]:
    tokens = _read_auth_tokens()
    return tokens.get("accessToken") if tokens else None

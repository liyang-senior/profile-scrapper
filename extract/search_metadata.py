"""Autocomplete helpers for getprog search filters."""
from typing import Any, Dict, List, Optional

import httpx

from auth.getprog_session import API_BASE, ensure_authenticated

_NAME_ENDPOINTS = {
    "countries": "/api/countries/",
    "locations": "/api/locations/",
    "regions": "/api/regions/",
    "companies": "/api/companies/",
    "skills": "/api/skills/",
    "languages": "/api/languages/",
    "schools": "/api/schools/",
}


def _fetch_names(
    endpoint: str,
    query: str,
    access_token: str,
    limit: int = 12,
) -> List[str]:
    with httpx.Client(base_url=API_BASE, timeout=30.0) as client:
        resp = client.get(
            endpoint,
            params={"search": (query or "").strip()},
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if resp.status_code != 200:
        return []

    data = resp.json()
    if not isinstance(data, list):
        return []

    ranked: List[tuple[str, int]] = []
    for item in data:
        if isinstance(item, dict) and item.get("name"):
            ranked.append((str(item["name"]), int(item.get("frequency") or 0)))
        elif isinstance(item, str):
            ranked.append((item, 0))

    ranked.sort(key=lambda pair: pair[1], reverse=True)
    names: List[str] = []
    for name, _freq in ranked[:limit]:
        if name not in names:
            names.append(name)
    return names


def fetch_filter_options(
    kind: str,
    query: str,
    email: str,
    password: str,
    limit: int = 12,
) -> List[str]:
    endpoint = _NAME_ENDPOINTS.get(kind)
    if not endpoint:
        return []
    token = ensure_authenticated(email, password)
    return _fetch_names(endpoint, query, token, limit=limit)


def probe_search_api(
    search: Dict[str, Any],
    email: str,
    password: str,
) -> Dict[str, Any]:
    """Validate search filters against getprog before a full scrape (costs 1 credit)."""
    from extract.search_params import (
        build_search_body,
        format_api_error,
        post_search_with_fallback,
        validate_search,
    )

    validate_search(search)
    token = ensure_authenticated(email, password)
    body = build_search_body(search, page=0, size=1)
    # Do NOT add with_emails — it can cause HTTP 400 on some filter combinations.

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Referer": "https://app.getprog.ai/",
    }

    with httpx.Client(base_url=API_BASE, headers=headers, timeout=60.0) as client:
        resp, label, attempts = post_search_with_fallback(client, body)

    if resp.status_code != 200:
        detail = format_api_error(resp, body)
        raise RuntimeError(
            f"Search validation failed (HTTP {resp.status_code}): {detail}"
        )

    data = resp.json()
    return {
        "results_count": data.get("results_count"),
        "body": body,
        "adjusted": label,
    }


def preview_search_count(
    search: Dict[str, Any],
    email: str,
    password: str,
) -> Optional[int]:
    from extract.search_params import build_search_body, format_api_error

    token = ensure_authenticated(email, password)
    body = build_search_body(search, page=0, size=1)
    # Do NOT add with_emails to avoid spurious 400 errors.

    with httpx.Client(base_url=API_BASE, timeout=60.0) as client:
        resp = client.post(
            "/api/search/",
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Referer": "https://app.getprog.ai/",
            },
        )

    if resp.status_code != 200:
        raise RuntimeError(
            f"Search preview failed (HTTP {resp.status_code}): {format_api_error(resp, body)}"
        )

    data = resp.json()
    return data.get("results_count")

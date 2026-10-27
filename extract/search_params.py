"""Build getprog search API bodies from structured UI settings."""
import json
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

import httpx

GEO_KEYS = ("countries", "locations", "regions", "sub_regions")
CORE_KEYS = ("text", "page", "size", *GEO_KEYS)

# Keys that are sent in the search body but can be stripped for a fallback retry.

SENIORITY_OPTIONS = ["Senior", "Middle", "Junior", "Rockstar"]
YO_OPTIONS = ["0-3", "3-5", "5-10", "10+"]

# Internal settings key -> getprog API JSON key
LIST_API_KEYS = {
    "yo_employement": "yo_employment",
}

LIST_FIELDS = (
    "countries",
    "locations",
    "regions",
    "sub_regions",
    "seniority",
    "languages",
    "schools",
    "yo_experience",
    "yo_employement",
)

SEMICOLON_FIELDS = (
    "required_skills",
    "bonus_skills",
    "so_skills",
    "prog_langs",
    "github_repos",
    "companies",
    "companies_domains",
    "current_companies",
    "current_companies_domains",
    "companies_to_exclude",
    "current_companies_to_exclude",
    "companies_domains_to_exclude",
    "current_companies_domains_to_exclude",
)

# Stored as lists in settings; sent as comma-separated strings to the API.
COMMA_STRING_FIELDS = ("required_skills", "bonus_skills")

TEXT_FIELDS = ("current_job_title",)

BOOL_FIELDS = ("is_top_school", "is_first_name_female")

FLOAT_FIELDS = ("likely_to_move_prob",)

INT_FIELDS = ("top",)

DEFAULT_SEARCH: Dict[str, Any] = {
    "text": "",
    "countries": [],
    "locations": [],
    "regions": [],
    "sub_regions": [],
    "seniority": [],
    "required_skills": [],
    "bonus_skills": [],
    "so_skills": "",
    "prog_langs": "",
    "github_repos": "",
    "companies": [],
    "companies_domains": "",
    "current_companies": [],
    "current_companies_domains": "",
    "companies_to_exclude": [],
    "current_companies_to_exclude": [],
    "companies_domains_to_exclude": "",
    "current_companies_domains_to_exclude": "",
    "yo_experience": [],
    "yo_employement": [],
    "languages": [],
    "schools": [],
    "current_job_title": "",
    "is_top_school": False,
    "is_first_name_female": False,
    "likely_to_move_prob": None,
    "top": None,
}


def _as_list(val: Any) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        if ";" in s:
            return [part.strip() for part in s.split(";") if part.strip()]
        if "," in s:
            return [part.strip() for part in s.split(",") if part.strip()]
        return [s]
    return [str(val).strip()] if str(val).strip() else []


def _join_semicolon(val: Any) -> str:
    items = _as_list(val)
    return ";".join(items)


def normalize_search(raw: Any) -> Dict[str, Any]:
    """Return a complete search dict with defaults filled in."""
    out = dict(DEFAULT_SEARCH)
    if not isinstance(raw, dict):
        return out

    out["text"] = str(raw.get("text") or "").strip()

    for key in LIST_FIELDS:
        out[key] = _as_list(raw.get(key))

    # Accept either spelling from saved settings / old URLs.
    if not out["yo_employement"] and raw.get("yo_employment") is not None:
        out["yo_employement"] = _as_list(raw.get("yo_employment"))

    out["seniority"] = [x for x in out["seniority"] if x in SENIORITY_OPTIONS]
    if not out["seniority"]:
        out["seniority"] = _infer_seniority_from_text(out["text"])
    out["yo_experience"] = [x for x in out["yo_experience"] if x in YO_OPTIONS]
    out["yo_employement"] = [x for x in out["yo_employement"] if x in YO_OPTIONS]

    for key in SEMICOLON_FIELDS:
        if key.endswith("_exclude") or key in ("companies", "current_companies"):
            out[key] = _as_list(raw.get(key))
        elif key in COMMA_STRING_FIELDS:
            out[key] = _as_list(raw.get(key))
        else:
            out[key] = str(raw.get(key) or "").strip()

    for key in TEXT_FIELDS:
        out[key] = str(raw.get(key) or "").strip()

    for key in BOOL_FIELDS:
        out[key] = bool(raw.get(key))

    for key in FLOAT_FIELDS:
        val = raw.get(key)
        if val in (None, "", False):
            out[key] = None
        else:
            try:
                out[key] = float(val)
            except (TypeError, ValueError):
                out[key] = None

    for key in INT_FIELDS:
        val = raw.get(key)
        if val in (None, "", False):
            out[key] = None
        else:
            try:
                out[key] = int(val)
            except (TypeError, ValueError):
                out[key] = None

    return out


def _infer_seniority_from_text(text: str) -> List[str]:
    lower = (text or "").lower()
    for level in SENIORITY_OPTIONS:
        if level.lower() in lower:
            return [level]
    return []


def search_from_url(search_url: str) -> Dict[str, Any]:
    """Parse a getprog search results URL into structured search settings."""
    parsed = urlparse(search_url)
    qs = parse_qs(parsed.query, keep_blank_values=True)

    def first(key: str, default: str = "") -> str:
        vals = qs.get(key, [])
        return unquote(vals[0]) if vals else default

    def multi(*keys: str) -> List[str]:
        out: List[str] = []
        for key in keys:
            out.extend(unquote(v) for v in qs.get(key, []))
        return out

    raw: Dict[str, Any] = {
        "text": first("text"),
        "countries": multi("countries[]", "countries"),
        "locations": multi("locations[]", "locations"),
        "regions": multi("regions[]", "regions"),
        "sub_regions": multi("sub_regions[]", "sub_regions"),
        "seniority": multi("seniority[]", "seniority"),
    }

    for scalar in SEMICOLON_FIELDS:
        raw[scalar] = first(scalar)

    for key in ("languages", "schools", "yo_experience", "yo_employement", "yo_employment"):
        val = first(key)
        if val:
            if key == "yo_employment":
                raw["yo_employement"] = val
            else:
                raw[key] = val

    for scalar in TEXT_FIELDS:
        raw[scalar] = first(scalar)

    for scalar in BOOL_FIELDS:
        val = first(scalar).strip().lower()
        raw[scalar] = val in ("1", "true", "yes")

    for scalar in FLOAT_FIELDS:
        raw[scalar] = first(scalar) or None

    for scalar in INT_FIELDS:
        raw[scalar] = first(scalar) or None

    return normalize_search(raw)


def migrate_settings_search(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure settings contain a structured search object."""
    if settings.get("search"):
        settings["search"] = normalize_search(settings["search"])
        return settings

    search_url = (settings.get("search_url") or "").strip()
    if search_url:
        settings["search"] = search_from_url(search_url)
    else:
        settings["search"] = normalize_search({})

    return settings


def _has_geo_filter(search: Dict[str, Any]) -> bool:
    return bool(
        (search.get("countries") or [])
        or (search.get("locations") or [])
        or (search.get("regions") or [])
    )


def job_queries_from_search(search: Dict[str, Any]) -> List[str]:
    """One job title per line. Blank lines ignored; duplicates (any case) dropped."""
    text = str((search or {}).get("text") or "")
    queries: List[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        q = line.strip()
        if not q:
            continue
        key = q.casefold()
        if key in seen:
            continue
        seen.add(key)
        queries.append(q)
    return queries


def validate_search(search: Dict[str, Any]) -> None:
    if not job_queries_from_search(search):
        raise RuntimeError(
            "Enter a search query (job title, skills, or keywords), then Save. "
            "Use one job title per line to scrape several roles in one run."
        )

    s = normalize_search(search)

    if not _has_geo_filter(s):
        raise RuntimeError(
            "Add at least one **Country** or **Location** (not both required - either is enough). "
            "Select from the dropdown, then Save."
        )
    invalid_seniority = [x for x in _as_list(search.get("seniority")) if x not in SENIORITY_OPTIONS]
    if invalid_seniority:
        raise RuntimeError(
            f"Invalid seniority value(s): {', '.join(invalid_seniority)}. "
            f"Choose from: {', '.join(SENIORITY_OPTIONS)}."
        )

    for label, key in (
        ("Years of coding experience", "yo_experience"),
        ("Years of employment", "yo_employement"),
    ):
        invalid = [x for x in _as_list(search.get(key)) if x not in YO_OPTIONS]
        if invalid:
            raise RuntimeError(
                f"Invalid {label} value(s): {', '.join(invalid)}. "
                f"Choose from: {', '.join(YO_OPTIONS)}."
            )

    if s.get("likely_to_move_prob") is not None and not 0 < float(s["likely_to_move_prob"]) <= 1:
        raise RuntimeError("Likely to move must be between 0 and 1 (or leave at 0).")

    if s.get("top") is not None and int(s["top"]) < 1:
        raise RuntimeError("Top N profiles must be at least 1 (or leave at 0).")


def format_api_error(resp: httpx.Response, body: Optional[Dict[str, Any]] = None) -> str:
    """Turn a getprog API error response into a readable message."""
    text = (resp.text or "").strip()
    if not text:
        if resp.status_code == 400:
            has_geo = bool(
                body
                and (
                    body.get("countries")
                    or body.get("locations")
                    or body.get("regions")
                )
            )
            if has_geo:
                return (
                    "HTTP 400 - getprog rejected the search filters. "
                    "Country/location is set - try clearing **Years of employment**, "
                    "**Years of coding experience**, or **Diversity filters**, then Save and retry."
                )
            return (
                "HTTP 400 - getprog requires at least one **Country** or **Location**. "
                "Select a value from the dropdown below the search box (typing alone is not enough), then Save."
            )
        if resp.status_code == 403:
            return (
                "HTTP 403 - no permission to search. "
                "You may be out of search credits (each failed retry also uses 1 credit) "
                "or your plan does not allow this filter."
            )
        return f"HTTP {resp.status_code} with empty response body"

    try:
        data = resp.json()
    except Exception:
        return text[:500]

    if isinstance(data, dict):
        if isinstance(data.get("detail"), str):
            return data["detail"]
        parts: List[str] = []
        for key, msgs in data.items():
            if isinstance(msgs, list):
                flat = []
                for item in msgs:
                    if isinstance(item, list):
                        flat.extend(str(x) for x in item)
                    else:
                        flat.append(str(item))
                parts.append(f"{key}: {', '.join(flat)}")
            else:
                parts.append(f"{key}: {msgs}")
        if parts:
            return "; ".join(parts)

    return json.dumps(data, ensure_ascii=False)[:500]


def build_search_body(search: Dict[str, Any], page: int, size: int) -> Dict[str, Any]:
    """Convert structured search settings to getprog POST /api/search/ JSON."""
    s = normalize_search(search)
    validate_search(s)

    body: Dict[str, Any] = {
        "text": s["text"],
        "page": page,
        "size": size,
    }

    for key in LIST_FIELDS:
        values = s.get(key) or []
        if values:
            api_key = LIST_API_KEYS.get(key, key)
            body[api_key] = list(values)

    for key in SEMICOLON_FIELDS:
        val = s.get(key)
        if key in COMMA_STRING_FIELDS:
            joined = ",".join(_as_list(val))
        elif key in (
            "companies",
            "current_companies",
            "companies_to_exclude",
            "current_companies_to_exclude",
        ):
            joined = ";".join(_as_list(val))
        else:
            joined = str(val or "").strip()
        if joined:
            body[key] = joined

    for key in TEXT_FIELDS:
        val = str(s.get(key) or "").strip()
        if val:
            body[key] = val

    for key in BOOL_FIELDS:
        if s.get(key):
            # getprog web UI sends the string "true" (not a JSON boolean).
            body[key] = "true"

    for key in FLOAT_FIELDS:
        val = s.get(key)
        if val is not None:
            body[key] = val

    for key in INT_FIELDS:
        val = s.get(key)
        if val is not None:
            body[key] = val

    return body


def _minimal_geo_body(body: Dict[str, Any]) -> Dict[str, Any]:
    alt: Dict[str, Any] = {}
    for key in CORE_KEYS:
        val = body.get(key)
        if val is None or val == "" or val == []:
            continue
        alt[key] = val
    return alt


# Keys stripped only on the last-resort fallback (changes result set).
_FILTER_KEYS = ("yo_employment", "yo_experience", "is_first_name_female", "seniority")
_MAX_SEARCH_RETRIES = 2


def search_fallback_bodies(body: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """Ordered fallbacks after HTTP 400 - at most _MAX_SEARCH_RETRIES are tried."""
    fallbacks: List[Tuple[str, Dict[str, Any]]] = []
    seen: set[str] = set()

    def add(label: str, alt: Dict[str, Any]) -> None:
        key = json.dumps(alt, sort_keys=True, default=str)
        if key in seen:
            return
        seen.add(key)
        fallbacks.append((label, alt))

    if body.get("with_emails"):
        no_emails = {k: v for k, v in body.items() if k != "with_emails"}
        add("omit with_emails (slower email enrichment)", no_emails)

    if any(k in body for k in _FILTER_KEYS) or body.get("with_emails"):
        stripped = {k: v for k, v in body.items() if k not in (*_FILTER_KEYS, "with_emails")}
        add("strip optional filters", stripped)

    return fallbacks[:_MAX_SEARCH_RETRIES]


def search_fallback_body(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Legacy: first fallback body, if any."""
    bodies = search_fallback_bodies(body)
    return bodies[0][1] if bodies else None


def post_search_with_fallback(
    client: httpx.Client,
    body: Dict[str, Any],
    check_credits_fn: Optional[Callable[[], Optional[int]]] = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Tuple[httpx.Response, Optional[str], int]:
    """POST /api/search/; on HTTP 400 try up to _MAX_SEARCH_RETRIES fallbacks."""
    attempts = 1
    resp = client.post("/api/search/", json=body)
    if resp.status_code == 200:
        return resp, None, attempts
    if resp.status_code != 400:
        return resp, None, attempts

    for label, alt in search_fallback_bodies(body):
        if check_credits_fn is not None:
            left = check_credits_fn()
            if left is not None and left <= 0:
                break

        attempts += 1
        retry = client.post("/api/search/", json=alt)
        if retry.status_code == 200:
            if log_fn:
                log_fn(f"Search OK after adjustment: {label}")
            return retry, label, attempts
        if log_fn:
            log_fn(f"  Retry ({label}): HTTP {retry.status_code}")

    return resp, None, attempts

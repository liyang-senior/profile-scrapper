"""Scrape getprog via api.app.getprog.ai using saved session tokens."""

import ast

import json

import re

from concurrent.futures import ThreadPoolExecutor, as_completed

from typing import Any, Callable, Dict, List, Optional, Tuple



import httpx



from auth.getprog_session import ensure_authenticated

from dedupe import is_duplicate_of_any

from extract.profile_photo import is_getprog_photo, resolve_profile_photo

from extract.search_params import (
    build_search_body,
    format_api_error,
    post_search_with_fallback,
    search_from_url,
)

from parse.headline import parse_headline

from parse.role_groups import role_to_tab



API_BASE = "https://api.app.getprog.ai"



DEFAULT_PAGE_SIZE = 100

_MAX_PAGES_SAFETY = 500

ENRICH_MAX_WORKERS = 20





def _search_body_from_url(search_url: str, page: int, size: int) -> Dict[str, Any]:

    return build_search_body(search_from_url(search_url), page, size)





def _join_lines(val: Any, sep: str = "\n") -> str:

    """Normalize list / list-like API values into plain text (one item per line)."""

    if val is None:

        return ""

    if isinstance(val, list):

        return sep.join(str(x).strip() for x in val if x is not None and str(x).strip())

    s = str(val).strip()

    if not s or s == "[]":

        return ""

    if s.startswith("[") and s.endswith("]"):

        try:

            parsed = ast.literal_eval(s)

            if isinstance(parsed, list):

                return sep.join(

                    str(x).strip() for x in parsed if x is not None and str(x).strip()

                )

        except (SyntaxError, ValueError):

            pass

        quoted = re.findall(r"""['"]([^'"]+)['"]""", s)

        if quoted:

            return sep.join(x.strip() for x in quoted if x.strip())

        try:

            parsed = json.loads(s.replace("'", '"'))

            if isinstance(parsed, list):

                return sep.join(

                    str(x).strip() for x in parsed if x is not None and str(x).strip()

                )

        except json.JSONDecodeError:

            pass

    if sep == "\n" and (";" in s or "," in s):

        parts = [

            p.strip().strip("[]'\"")

            for p in s.replace(";", "\n").replace(",", "\n").split("\n")

            if p.strip() and p.strip() != "[]"

        ]

        return sep.join(parts)

    return s





def _extract_emails(raw: Any) -> List[str]:

    """Normalize getprog email fields into a flat list of address strings."""

    found: List[str] = []



    def add(val: Any) -> None:

        if val is None:

            return

        if isinstance(val, list):

            for item in val:

                add(item)

            return

        s = str(val).strip()

        if not s:

            return

        if s.startswith("[") and s.endswith("]"):

            try:

                parsed = ast.literal_eval(s)

                if isinstance(parsed, list):

                    add(parsed)

                    return

            except (SyntaxError, ValueError):

                pass

            try:

                parsed = json.loads(s.replace("'", '"'))

                if isinstance(parsed, list):

                    add(parsed)

                    return

            except json.JSONDecodeError:

                pass

        for part in re.split(r"[\n;,]+", s):

            addr = part.strip().strip("[]'\"")

            if addr and "@" in addr:

                found.append(addr)



    add(raw)

    seen: set[str] = set()

    out: List[str] = []

    for addr in found:

        key = addr.lower()

        if key not in seen:

            seen.add(key)

            out.append(addr)

    return out





def _github_url(profile: Dict[str, Any]) -> str:

    url = str(profile.get("github_url") or "").strip()

    if url:

        return url

    handle = str(profile.get("github_handle") or "").strip().strip("@/")

    if handle:

        return f"https://github.com/{handle}"

    return ""





def _years_experience(profile: Dict[str, Any], headline_parts: Any) -> str:

    years = profile.get("years_of_experience")

    if years is None:

        years = profile.get("years_of_employment")

    if years is not None:

        return str(years)

    return headline_parts.years_experience or ""





def _profile_to_row(

    profile: Dict[str, Any],

    match_metadata: Optional[Dict[str, Any]] = None,

    http_client: Optional[httpx.Client] = None,

) -> Dict[str, Any]:

    _ = match_metadata

    title = profile.get("title") or ""

    parts = parse_headline(title)



    role = parts.role or title

    company = profile.get("company") or parts.current_company



    emails = gmail_only_emails(_extract_emails(profile.get("emails")))

    primary = profile.get("primary_email")

    if primary:

        primary = str(primary).strip()

        if primary and is_gmail_address(primary) and primary.lower() not in {e.lower() for e in emails}:

            emails = [primary] + emails


    return {

        "photo": resolve_profile_photo(profile, http_client=http_client),

        "name": profile.get("full_name") or "",

        "email": "\n".join(emails),

        "sender": "",

        "sent": "",

        "role": role,

        "current_company": company,

        "years_experience": _years_experience(profile, parts),

        "github_url": _github_url(profile),

        "linkedin_url": profile.get("linkedin_url") or "",

        "location": profile.get("location") or "",

        "languages": _join_lines(profile.get("languages"), "\n"),

        "phone_numbers": _join_lines(profile.get("phone_numbers"), "\n"),

        "role_tab": role_to_tab(role),

    }





def _extract_profile_data(data: Any) -> Dict[str, Any]:
    if isinstance(data, dict):
        if data.get("profile"):
            return dict(data["profile"])
        if data.get("id"):
            return dict(data)
    return {}


def _fetch_full_profile(client: httpx.Client, profile_id: int) -> Dict[str, Any]:
    """Fetch a single profile with emails. Tries the most reliable payloads first."""
    # POST with emails — works on accounts that have profile access
    for payload in (
        {"id": profile_id, "with_emails": True, "full_profiles": True},
        {"id": profile_id, "with_emails": True},
    ):
        resp = client.post("/api/get-profile/", json=payload)
        if resp.status_code == 200:
            result = _extract_profile_data(resp.json())
            if result:
                return result

    # GET fallback
    resp = client.get("/api/get-profile/", params={"id": profile_id, "with_emails": "true"})
    if resp.status_code == 200:
        result = _extract_profile_data(resp.json())
        if result:
            return result

    return {}





def _merge_profile(profile: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:

    for key, value in extra.items():

        if value is None:

            continue

        if key in ("emails", "phone_numbers", "languages"):
            if isinstance(value, str) and value.strip() in ("", "[]"):
                continue
            if isinstance(value, list) and not value:
                continue
            if not value:
                continue

        profile[key] = value

    return profile





def _profile_has_emails(profile: Dict[str, Any]) -> bool:
    """True when the profile has at least one usable email address."""
    if _extract_emails(profile.get("emails")):
        return True
    primary = str(profile.get("primary_email") or "").strip()
    return bool(primary and "@" in primary)


def _profile_needs_email_enrichment(profile: Dict[str, Any]) -> bool:
    return not _profile_has_emails(profile)


def is_gmail_address(addr: str) -> bool:
    """True for @gmail.com / @googlemail.com addresses."""
    a = str(addr or "").strip().lower()
    if "@" not in a:
        return False
    domain = a.rsplit("@", 1)[-1].strip()
    return domain in ("gmail.com", "googlemail.com")


def gmail_only_emails(emails: List[str]) -> List[str]:
    """Keep only Gmail addresses from a list."""
    return [e for e in emails if is_gmail_address(e)]


def row_has_email(row: Dict[str, Any]) -> bool:
    """True when a scraped row has at least one Gmail address."""
    email = str(row.get("email") or "").strip()
    if not email:
        return False
    for part in re.split(r"[\n;,]+", email):
        if is_gmail_address(part.strip()):
            return True
    return False





def _enrich_profiles_parallel(

    client: httpx.Client,

    profiles: List[Tuple[Dict[str, Any], int]],

) -> int:

    """Fetch full profiles in parallel when emails are missing. Returns enrich count."""

    if not profiles:

        return 0



    enriched = 0



    def _fetch(item: Tuple[Dict[str, Any], int]) -> Tuple[Dict[str, Any], Dict[str, Any]]:

        profile, pid = item

        return profile, _fetch_full_profile(client, pid)



    workers = min(ENRICH_MAX_WORKERS, len(profiles))

    with ThreadPoolExecutor(max_workers=workers) as pool:

        futures = [pool.submit(_fetch, item) for item in profiles]

        for fut in as_completed(futures):

            try:

                profile, extra = fut.result()

            except Exception:

                continue

            if extra:

                _merge_profile(profile, extra)

                if _profile_has_emails(profile):

                    enriched += 1

    return enriched





def _photo_source(profile: Dict[str, Any], row_photo: str) -> str:

    if is_getprog_photo(row_photo):

        return "getprog"

    if "avatars.githubusercontent.com" in row_photo:

        return "github"

    if "ui-avatars.com" in row_photo:

        return "initials"

    if row_photo:

        return "other"

    return "none"





def _check_subscription(client: httpx.Client) -> Dict[str, Any]:

    resp = client.get("/api/users/current/subscription/")

    if resp.status_code != 200:

        return {}

    return resp.json() or {}





def _post_search(

    client: httpx.Client,

    body: Dict[str, Any],

    check_credits_fn: Optional[Callable[[], Optional[int]]] = None,

    log_fn: Optional[Callable[[str], None]] = None,

) -> Tuple[httpx.Response, int]:

    resp, _label, attempts = post_search_with_fallback(

        client, body, check_credits_fn=check_credits_fn, log_fn=log_fn

    )

    return resp, attempts





def scrape_via_api(

    search: Dict[str, Any],

    email: str,

    password: str,

    headless: bool = True,

    dry_run: bool = False,

    max_pages: int = 10,

    fetch_full_profiles: bool = True,

    log_fn: Optional[Callable[[str], None]] = None,

    stop_check: Optional[Callable[[], bool]] = None,

) -> List[Dict[str, Any]]:

    """Paginate search API and optionally fetch full profile for each candidate."""

    _ = headless

    access_token = ensure_authenticated(email, password)



    all_rows: List[Dict[str, Any]] = []

    page_limit = min(max_pages, _MAX_PAGES_SAFETY)

    photo_stats = {"getprog": 0, "github": 0, "initials": 0, "other": 0, "none": 0}
    email_stats = {"saved": 0, "skipped_no_email": 0}



    headers = {

        "Authorization": f"Bearer {access_token}",

        "Content-Type": "application/json",

        "Referer": "https://app.getprog.ai/",

        "Origin": "https://app.getprog.ai",

        "Accept": "application/json",

    }



    with httpx.Client(base_url=API_BASE, headers=headers, timeout=120.0) as client:

        sub = _check_subscription(client)

        requests_left = sub.get("requests_left")

        if requests_left is not None and requests_left <= 0:

            raise RuntimeError(

                "No search credits left on your free trial (requests_left=0). "

                "Upgrade your plan or wait for credits to reset, then try again."

            )

        if requests_left is not None and log_fn:

            log_fn(f"Credits: {requests_left} search requests remaining (limit {sub.get('requests_limit')})")



        effective_max = page_limit

        if requests_left is not None:

            effective_max = min(page_limit, max(1, int(requests_left)))

        _credits_ref = [requests_left]

        def _live_credits() -> Optional[int]:
            """Re-check credits in real time (called before fallback retries)."""
            sub2 = _check_subscription(client)
            left = sub2.get("requests_left")
            _credits_ref[0] = left
            return left

        for page_num in range(effective_max):

            if stop_check and stop_check():

                if log_fn:

                    log_fn("Stop requested — halting after current page")

                break

            # Stop early if credits have been exhausted mid-scrape.
            if _credits_ref[0] is not None and _credits_ref[0] <= 0:

                if log_fn:

                    log_fn("No search credits remaining — stopping.")

                break

            body = build_search_body(search, page_num, DEFAULT_PAGE_SIZE)

            # Do NOT send with_emails on search — the getprog web UI does not, and
            # adding it can change the result set. Emails are filled via /api/get-profile/.

            if log_fn:
                log_fn(f"Search page {page_num} (size={DEFAULT_PAGE_SIZE})…")
                if page_num == 0:
                    log_fn(
                        "API search body: "
                        f"text={body.get('text')!r}, "
                        f"countries={body.get('countries')}, "
                        f"locations={body.get('locations')}, "
                        f"seniority={body.get('seniority')}, "
                        f"yo_experience={body.get('yo_experience')}, "
                        f"is_first_name_female={body.get('is_first_name_female')!r}"
                    )

            resp, attempts = _post_search(client, body, check_credits_fn=_live_credits, log_fn=log_fn)

            if resp.status_code != 200:

                detail = format_api_error(resp, body)

                # Re-check credits to give a meaningful error message.
                sub_after = _check_subscription(client)
                left = sub_after.get("requests_left")
                _credits_ref[0] = left

                if resp.status_code in (400, 403) and left is not None and left <= 0:

                    raise RuntimeError(

                        "Search credits exhausted (0 remaining). "

                        "Each failed retry also uses 1 credit. "

                        "Wait for reset or upgrade on getprog.ai."

                    )

                if log_fn:

                    log_fn(f"Search request body: {body}")

                    if not (resp.text or "").strip():

                        log_fn("Search response body: (empty)")

                    if left is not None:

                        log_fn(f"Credits remaining: {left}")

                if resp.status_code == 403:

                    raise RuntimeError(

                        f"Search blocked (HTTP 403): {detail} "

                        "Check search credits on getprog.ai (Pricing plans)."

                    )

                raise RuntimeError(f"Search failed (HTTP {resp.status_code}): {detail}")



            data = resp.json()

            batch = data.get("results") or []

            total = data.get("results_count")



            if log_fn:

                log_fn(f"  Page {page_num}: {len(batch)} profiles (total matching: {total})")



            if not batch:

                break



            page_profiles: List[Dict[str, Any]] = []

            enrich_queue: List[Tuple[Dict[str, Any], int]] = []



            for item in batch:

                profile = dict(item.get("profile") or {})

                meta = item.get("match_metadata") or {}

                pid = profile.get("id")



                if fetch_full_profiles and pid and _profile_needs_email_enrichment(profile):

                    enrich_queue.append((profile, int(pid)))



                page_profiles.append((profile, meta))



            if enrich_queue:

                enriched = _enrich_profiles_parallel(client, enrich_queue)

                if log_fn:

                    log_fn(f"  Fetched emails for {enriched}/{len(enrich_queue)} profiles (parallel)")



            for profile, meta in page_profiles:

                # Do NOT pass http_client here — that triggers a serial HEAD request
                # per profile to validate S3 photo URLs, adding ~0.4s × 100 = 40s per page.
                # Photos are trusted as-is from the API; run fix_photo_urls.py separately if needed.
                row = _profile_to_row(profile, meta)

                if not row_has_email(row):
                    email_stats["skipped_no_email"] += 1
                    continue

                photo_stats[_photo_source(profile, row.get("photo") or "")] += 1
                email_stats["saved"] += 1

                if is_duplicate_of_any(row, all_rows):

                    continue

                all_rows.append(row)



            if dry_run:

                break



            if len(batch) < DEFAULT_PAGE_SIZE:

                break



    if log_fn and (all_rows or email_stats["skipped_no_email"]):

        total = len(all_rows)

        getprog_n = photo_stats["getprog"]

        if total:
            log_fn(
                f"Photos: {getprog_n}/{total} getprog LinkedIn "
                f"({photo_stats['github']} GitHub, {photo_stats['initials']} initials)"
            )

        if email_stats["skipped_no_email"]:
            log_fn(
                f"Skipped {email_stats['skipped_no_email']} profiles with no Gmail "
                "(not saved to CSV or Sheets)"
            )

        if total:
            log_fn(f"Saved {email_stats['saved']} profiles with email")



    return all_rows



"""Resolve profile photo URLs the same way getprog displays avatars."""

import re

from typing import Any, Dict, Optional



import httpx

from urllib.parse import quote



UI_AVATAR_BASE = "https://ui-avatars.com/api/"

S3_AVATAR_BASE = "https://s3.us-west-1.amazonaws.com/progai-linkedin-avatars"

PROGAI_S3_MARKER = "progai-linkedin-avatars"



_url_access_cache: Dict[str, bool] = {}





def linkedin_slug(url: str) -> str:

    match = re.search(r"linkedin\.com/in/([^/?#]+)", str(url or ""), re.I)

    return match.group(1).lower().strip() if match else ""





def progai_avatar_from_linkedin(linkedin_url: str) -> str:

    """Reconstruct getprog S3 avatar URL from a LinkedIn profile URL."""

    slug = linkedin_slug(linkedin_url)

    if not slug:

        return ""

    return f"{S3_AVATAR_BASE}/{slug}.png"





def is_getprog_photo(url: str) -> bool:

    return PROGAI_S3_MARKER in str(url or "").lower()





def is_fallback_photo(url: str) -> bool:

    """True when the URL is a substitute avatar, not getprog's LinkedIn photo."""

    u = str(url or "").strip().lower()

    if not u:

        return True

    if is_getprog_photo(u):

        return False

    return "ui-avatars.com" in u or "avatars.githubusercontent.com" in u





def _github_handle(profile: Dict[str, Any]) -> str:

    handle = str(profile.get("github_handle") or "").strip().strip("@/")

    if handle:

        return handle



    github_url = str(profile.get("github_url") or "").strip()

    match = re.search(r"github\.com/([^/?#]+)", github_url, re.I)

    if not match:

        return ""

    slug = match.group(1)

    if slug.lower() in {"orgs", "organizations", "sponsors", "settings", "marketplace"}:

        return ""

    return slug





def _initials(profile: Dict[str, Any]) -> str:

    """Match getprog frontend: first+last initial, else github initial."""

    first = str(profile.get("first_name") or "").strip()

    last = str(profile.get("last_name") or "").strip()

    if first and last:

        return f"{first[0]}{last[0]}".upper()



    handle = _github_handle(profile)

    if handle:

        return handle[0].upper()



    full_name = str(profile.get("full_name") or "").strip()

    parts = [p for p in full_name.split() if p]

    if len(parts) >= 2:

        return f"{parts[0][0]}{parts[-1][0]}".upper()

    if parts:

        return parts[0][0].upper()

    return "?"





def _initials_avatar_url(profile: Dict[str, Any]) -> str:

    """Colored initials image similar to getprog when no real photo exists."""

    label = str(profile.get("full_name") or _initials(profile)).strip()

    initials = _initials(profile)

    params = (

        f"?name={quote(label)}"

        f"&size=128"

        "&background=1F4E78"

        "&color=ffffff"

        "&bold=true"

        f"&length={len(initials)}"

    )

    return f"{UI_AVATAR_BASE}{params}"





def _needs_access_check(url: str) -> bool:

    return PROGAI_S3_MARKER in url.lower()





def photo_url_is_accessible(

    url: str,

    client: Optional[httpx.Client] = None,

) -> bool:

    """Return True when the URL returns a public image (HEAD 200)."""

    url = (url or "").strip()

    if not url.startswith("http"):

        return False

    if url in _url_access_cache:

        return _url_access_cache[url]



    owns_client = client is None

    if owns_client:

        client = httpx.Client(timeout=10.0, follow_redirects=True)



    ok = False

    try:

        assert client is not None

        resp = client.head(url)

        ctype = (resp.headers.get("content-type") or "").lower()

        ok = resp.status_code == 200 and (

            "image" in ctype or not ctype.startswith("application/xml")

        )

    except httpx.HTTPError:

        ok = False

    finally:

        if owns_client and client is not None:

            client.close()



    _url_access_cache[url] = ok

    return ok





def clear_photo_url_cache() -> None:

    _url_access_cache.clear()





def ensure_profile_pic_url(profile: Dict[str, Any]) -> None:

    """Fill profile_pic_url from getprog data when search omitted it (in-place)."""

    pic = str(profile.get("profile_pic_url") or "").strip()

    if pic and pic.lower() not in ("null", "none", "[]"):

        return

    profile["profile_pic_url"] = ""

    linkedin = str(profile.get("linkedin_url") or "").strip()

    guessed = progai_avatar_from_linkedin(linkedin)

    if guessed:

        profile["profile_pic_url"] = guessed





def resolve_profile_photo(

    profile: Dict[str, Any],

    *,

    use_initials_fallback: bool = True,

    validate_urls: bool = False,

    http_client: Optional[httpx.Client] = None,

) -> str:

    """

    Return a photo URL matching getprog search results.



    Priority (same as getprog UI):

    1. API profile_pic_url

    2. S3 URL derived from LinkedIn slug

    3. GitHub avatar

    4. Initials placeholder

    """

    ensure_profile_pic_url(profile)

    pic = str(profile.get("profile_pic_url") or "").strip()
    if pic and is_getprog_photo(pic) and http_client is not None and not photo_url_is_accessible(pic, http_client):
        pic = ""
        profile["profile_pic_url"] = ""

    if pic:
        if not validate_urls:
            return pic
        if not _needs_access_check(pic) or photo_url_is_accessible(pic, http_client):
            return pic

    linkedin_guess = progai_avatar_from_linkedin(str(profile.get("linkedin_url") or ""))
    if linkedin_guess:
        if (
            http_client is not None
            and is_getprog_photo(linkedin_guess)
            and not photo_url_is_accessible(linkedin_guess, http_client)
        ):
            linkedin_guess = ""
        elif linkedin_guess and (
            not validate_urls or photo_url_is_accessible(linkedin_guess, http_client)
        ):
            return linkedin_guess



    handle = _github_handle(profile)

    if handle:

        github_url = f"https://avatars.githubusercontent.com/{handle}?v=4"

        if not validate_urls or photo_url_is_accessible(github_url, http_client):

            return github_url



    if use_initials_fallback:

        return _initials_avatar_url(profile)

    return ""





def profile_from_csv_row(row: Dict[str, Any]) -> Dict[str, Any]:

    """Build a minimal getprog-like profile dict from a CSV row."""

    name = (row.get("name") or "").strip()

    parts = name.split()

    gh = (row.get("github_url") or "").strip()

    photo = (row.get("photo") or "").strip()

    profile_pic = photo if is_getprog_photo(photo) else ""

    return {

        "full_name": name,

        "first_name": parts[0] if parts else "",

        "last_name": parts[-1] if len(parts) > 1 else "",

        "profile_pic_url": profile_pic,

        "github_url": gh,

        "github_handle": _github_handle({"github_url": gh}),

        "linkedin_url": row.get("linkedin_url") or "",

    }



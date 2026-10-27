"""Scrape getprog search results (API-first)."""
from typing import Any, Callable, Dict, List, Optional

from extract.api_client import scrape_via_api
from extract.search_params import normalize_search


def scrape_search_results(
    search: Dict[str, Any],
    email: str,
    password: str,
    headless: bool = True,
    dry_run: bool = False,
    max_pages: int = 10,
    log_fn: Optional[Callable[[str], None]] = None,
    stop_check: Optional[Callable[[], bool]] = None,
) -> List[Dict[str, Any]]:
    """Scrape candidates from getprog search settings using the API."""
    return scrape_via_api(
        search=normalize_search(search),
        email=email,
        password=password,
        headless=headless,
        dry_run=dry_run,
        max_pages=max_pages,
        fetch_full_profiles=True,
        log_fn=log_fn,
        stop_check=stop_check,
    )

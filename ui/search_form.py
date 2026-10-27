"""getprog-style search form for Streamlit."""
from typing import Any, Dict, List, Optional

import streamlit as st

from extract.search_metadata import fetch_filter_options, preview_search_count
from extract.search_params import (
    DEFAULT_SEARCH,
    SENIORITY_OPTIONS,
    YO_OPTIONS,
    job_queries_from_search,
    normalize_search,
)

GETPROG_CSS = """
<style>
.getprog-search-panel {
    margin-bottom: 12px;
}
.getprog-search-panel h3 {
    margin: 0 0 14px;
    font-size: 22px;
    font-weight: 600;
    color: #0f172a;
}
.getprog-field-label {
    font-size: 13px;
    font-weight: 500;
    color: #334155;
    margin: 10px 0 6px;
}
.getprog-field-label.is-missing {
    color: #dc2626;
}
.getprog-required {
    color: #dc2626;
    margin-left: 3px;
    font-weight: 600;
}
.getprog-hint {
    color: #64748b;
    font-size: 12px;
    margin-top: -4px;
    margin-bottom: 8px;
}
div[data-testid="stTextArea"] textarea {
    min-height: 110px !important;
    border-radius: 12px !important;
    border: 1px solid #d7dee8 !important;
    font-size: 15px !important;
}
div[data-testid="stExpander"] details {
    border: 1px solid #d7dee8;
    border-radius: 12px;
    background: #fff;
}
div[data-testid="stExpander"] summary {
    font-weight: 600;
    color: #2563eb;
}
.getprog-diversity-box {
    background: #ffffff;
    border: 1px solid #d7dee8;
    border-radius: 12px;
    padding: 14px 16px;
    margin: 14px 0 16px;
}
.getprog-diversity-box .getprog-field-label {
    margin-top: 0;
    margin-bottom: 10px;
    font-size: 14px;
    font-weight: 600;
    color: #0f172a;
}
</style>
"""

_SEARCH_LIMIT = 15


def _set_if_missing(key: str, value: Any) -> None:
    if key not in st.session_state:
        st.session_state[key] = value


def sync_search_widgets(search: Dict[str, Any]) -> None:
    """Seed widget session state before widgets render (never overwrite after)."""
    search = normalize_search(search)
    _set_if_missing("search_text_main", search.get("text", ""))
    for field in (
        "countries",
        "locations",
        "regions",
        "companies",
        "current_companies",
        "languages",
        "schools",
    ):
        _set_if_missing(f"search_ms_{field}", list(search.get(field) or []))
    _set_if_missing(
        "search_seniority",
        [x for x in (search.get("seniority") or []) if x in SENIORITY_OPTIONS],
    )
    _set_if_missing(
        "search_yo_experience",
        [x for x in (search.get("yo_experience") or []) if x in YO_OPTIONS],
    )
    _set_if_missing(
        "search_yo_employement",
        [x for x in (search.get("yo_employement") or []) if x in YO_OPTIONS],
    )
    _set_if_missing("search_sub_regions", "; ".join(search.get("sub_regions") or []))
    for field in (
        "so_skills",
        "prog_langs",
        "github_repos",
        "companies_domains",
        "current_companies_domains",
        "companies_domains_to_exclude",
        "current_companies_domains_to_exclude",
        "current_job_title",
    ):
        _set_if_missing(f"search_scalar_{field}", str(search.get(field) or ""))
    for field in (
        "required_skills",
        "bonus_skills",
        "companies_to_exclude",
        "current_companies_to_exclude",
    ):
        current = search.get(field) or []
        if isinstance(current, str):
            current = [x.strip() for x in current.replace(";", ",").split(",") if x.strip()]
        _set_if_missing(f"search_txt_{field}", ", ".join(current))
    _set_if_missing("search_is_top_school", bool(search.get("is_top_school")))
    _set_if_missing("search_is_first_name_female", bool(search.get("is_first_name_female")))
    likely = search.get("likely_to_move_prob")
    _set_if_missing("search_likely_to_move", float(likely) if likely is not None else 0.0)
    top_val = search.get("top")
    _set_if_missing("search_top", int(top_val) if top_val else 0)


def collect_search_from_widgets(fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build current search settings from Streamlit widget state (safe before form renders)."""
    base = normalize_search(fallback or {})
    raw: Dict[str, Any] = dict(base)

    if "search_text_main" in st.session_state:
        raw["text"] = st.session_state["search_text_main"]

    for field in (
        "countries",
        "locations",
        "regions",
        "companies",
        "current_companies",
        "languages",
        "schools",
    ):
        key = f"search_ms_{field}"
        if key in st.session_state:
            raw[field] = list(st.session_state.get(key) or [])

    if "search_seniority" in st.session_state:
        raw["seniority"] = list(st.session_state.get("search_seniority") or [])
    if "search_yo_experience" in st.session_state:
        raw["yo_experience"] = list(st.session_state.get("search_yo_experience") or [])
    if "search_yo_employement" in st.session_state:
        raw["yo_employement"] = list(st.session_state.get("search_yo_employement") or [])

    if "search_sub_regions" in st.session_state:
        raw["sub_regions"] = [
            x.strip()
            for x in str(st.session_state.get("search_sub_regions") or "").split(";")
            if x.strip()
        ]

    for field in (
        "so_skills",
        "prog_langs",
        "github_repos",
        "companies_domains",
        "current_companies_domains",
        "companies_domains_to_exclude",
        "current_companies_domains_to_exclude",
        "current_job_title",
    ):
        key = f"search_scalar_{field}"
        if key in st.session_state:
            raw[field] = st.session_state.get(key) or ""

    for field in (
        "required_skills",
        "bonus_skills",
        "companies_to_exclude",
        "current_companies_to_exclude",
    ):
        key = f"search_txt_{field}"
        if key in st.session_state:
            raw[field] = [
                x.strip()
                for x in str(st.session_state.get(key) or "").split(",")
                if x.strip()
            ]

    if "search_is_top_school" in st.session_state:
        raw["is_top_school"] = bool(st.session_state.get("search_is_top_school"))
    if "search_is_first_name_female" in st.session_state:
        raw["is_first_name_female"] = bool(st.session_state.get("search_is_first_name_female"))

    if "search_likely_to_move" in st.session_state:
        likely = st.session_state.get("search_likely_to_move")
        raw["likely_to_move_prob"] = float(likely) if likely else None
    if "search_top" in st.session_state:
        top_val = st.session_state.get("search_top")
        raw["top"] = int(top_val) if top_val else None

    return normalize_search(raw)


def _render_field_label(
    label: str,
    *,
    required: bool = False,
    missing: bool = False,
    hint: str = "",
) -> None:
    suffix = " *" if required else ""
    colour = "#dc2626" if missing else "#334155"
    st.markdown(
        f'<div class="getprog-field-label" style="color:{colour}">{label}{suffix}</div>',
        unsafe_allow_html=True,
    )
    if hint:
        st.caption(hint)


def _has_geo_filter(search: Dict[str, Any]) -> bool:
    for field in ("countries", "locations", "regions"):
        if st.session_state.get(f"search_ms_{field}"):
            return True
        if search.get(field):
            return True
    return False


def _render_autocomplete_tags(
    label: str,
    field: str,
    kind: str,
    search: Dict[str, Any],
    email: str,
    password: str,
    disabled: bool,
    placeholder: str,
    *,
    required: bool = False,
    geo_missing: bool = False,
) -> None:
    ms_key = f"search_ms_{field}"
    opts_key = f"search_api_opts_{field}"
    last_query_key = f"search_last_query_{field}"
    query_key = f"search_query_{field}"

    selected: List[str] = list(st.session_state.get(ms_key, search.get(field) or []))
    field_missing = geo_missing and required and not selected
    hint = ""
    if required:
        hint = "Required — pick Country or Location (one is enough; Region also counts)."
    _render_field_label(label, required=required, missing=field_missing, hint=hint)
    if not required:
        st.markdown(
            '<div class="getprog-hint">Type to search getprog, then pick from the list.</div>',
            unsafe_allow_html=True,
        )

    query = st.text_input(
        f"{label} search",
        key=query_key,
        placeholder=placeholder,
        disabled=disabled,
        label_visibility="collapsed",
    )

    q = query.strip()
    if email and password and not disabled and len(q) >= 2:
        need_fetch = opts_key not in st.session_state or st.session_state.get(last_query_key) != q
        if need_fetch:
            try:
                st.session_state[opts_key] = fetch_filter_options(
                    kind, q, email, password, limit=_SEARCH_LIMIT
                )
                st.session_state[last_query_key] = q
            except Exception:
                if opts_key not in st.session_state:
                    st.session_state[opts_key] = []
    elif opts_key not in st.session_state:
        st.session_state[opts_key] = []

    cached = list(st.session_state.get(opts_key, []))
    options = list(dict.fromkeys(selected + cached))

    if not email or not password:
        st.caption("Type 2+ characters to load suggestions (after Save).")

    if not options:
        search[field] = selected
        return

    chosen = st.multiselect(
        label,
        options=options,
        key=ms_key,
        disabled=disabled,
        label_visibility="collapsed",
        placeholder=f"Select {label.lower()}…",
    )
    search[field] = chosen


def _render_text_list_field(
    label: str,
    field: str,
    search: Dict[str, Any],
    disabled: bool,
    placeholder: str,
    help_text: str = "",
    *,
    required: bool = False,
) -> None:
    _render_field_label(label, required=required, hint=help_text)
    raw = st.text_input(
        label,
        key=f"search_txt_{field}",
        placeholder=placeholder,
        disabled=disabled,
        label_visibility="collapsed",
    )
    search[field] = [x.strip() for x in raw.split(",") if x.strip()]


def _render_scalar_field(
    label: str,
    field: str,
    search: Dict[str, Any],
    disabled: bool,
    placeholder: str = "",
    help_text: str = "",
    *,
    required: bool = False,
) -> None:
    _render_field_label(label, required=required, hint=help_text)
    search[field] = st.text_input(
        label,
        key=f"search_scalar_{field}",
        placeholder=placeholder,
        disabled=disabled,
        label_visibility="collapsed",
    )


def render_search_form(
    settings: Dict[str, Any],
    email: str,
    password: str,
    disabled: bool = False,
) -> Dict[str, Any]:
    """Render getprog search UI and return structured search settings."""
    search = normalize_search(settings.get("search") or DEFAULT_SEARCH)

    st.markdown(GETPROG_CSS, unsafe_allow_html=True)
    st.subheader("Search", divider=False)

    job_text = str(st.session_state.get("search_text_main", search.get("text") or ""))
    job_missing = not job_text.strip()
    _render_field_label(
        "Job query",
        required=True,
        missing=job_missing,
        hint="One job title per line. Each line is a separate search with the same filters.",
    )
    search["text"] = st.text_area(
        "Job query",
        placeholder="AI Engineer\nML Engineer\nFull Stack Engineer\nBI Engineer\nData Engineer\nProduct Manager\nDevOps Engineer",
        height=120,
        disabled=disabled,
        label_visibility="collapsed",
        key="search_text_main",
    )

    with st.container(border=True):
        st.caption("**Diversity filters**")
        search["is_first_name_female"] = st.checkbox(
            "Name contains a female first name",
            key="search_is_first_name_female",
            disabled=disabled,
            help="Same filter as getprog.ai — limits results to profiles with a female first name.",
        )

    geo_missing = not _has_geo_filter(search)

    _render_autocomplete_tags(
        "Country",
        "countries",
        "countries",
        search,
        email,
        password,
        disabled,
        "Search countries…",
        required=True,
        geo_missing=geo_missing,
    )
    _render_autocomplete_tags(
        "Location",
        "locations",
        "locations",
        search,
        email,
        password,
        disabled,
        "Search locations…",
        required=True,
        geo_missing=geo_missing,
    )

    search["seniority"] = st.multiselect(
        "Seniority",
        options=SENIORITY_OPTIONS,
        key="search_seniority",
        disabled=disabled,
        placeholder="Select seniority levels…",
    )

    search["yo_experience"] = st.multiselect(
        "Years of coding experience (GitHub)",
        options=YO_OPTIONS,
        key="search_yo_experience",
        disabled=disabled,
        placeholder="e.g. 5-10",
    )

    search["yo_employement"] = st.multiselect(
        "Years of employment (LinkedIn)",
        options=YO_OPTIONS,
        key="search_yo_employement",
        disabled=disabled,
        placeholder="e.g. 5-10",
    )

    with st.expander("All Filters", expanded=False):
        _render_autocomplete_tags(
            "Region",
            "regions",
            "regions",
            search,
            email,
            password,
            disabled,
            "Search regions…",
        )

        sub_regions = st.text_input(
            "Sub-region",
            key="search_sub_regions",
            placeholder="Northern America; Western Europe",
            disabled=disabled,
            label_visibility="collapsed",
        )
        search["sub_regions"] = [x.strip() for x in sub_regions.split(";") if x.strip()]

        _render_text_list_field(
            "Required skills",
            "required_skills",
            search,
            disabled,
            "react, javascript, typescript",
            "Required skills use AND — more skills narrows results.",
        )
        _render_text_list_field(
            "Bonus skills",
            "bonus_skills",
            search,
            disabled,
            "python, pytorch",
            "Bonus skills use OR — more skills broadens results.",
        )
        _render_scalar_field(
            "Stack Overflow skills",
            "so_skills",
            search,
            disabled,
            "docker; sql",
            "Separate with semicolons.",
        )
        _render_scalar_field(
            "Programming languages",
            "prog_langs",
            search,
            disabled,
            "javascript; python; java",
            "Separate with semicolons.",
        )
        _render_scalar_field(
            "GitHub repos",
            "github_repos",
            search,
            disabled,
            "tensorflow/tensorflow",
            "Separate with semicolons.",
        )

        _render_autocomplete_tags(
            "Companies (ever worked at)",
            "companies",
            "companies",
            search,
            email,
            password,
            disabled,
            "Search companies…",
        )
        _render_scalar_field(
            "Company domains (ever worked at)",
            "companies_domains",
            search,
            disabled,
            "google.com; meta.com",
        )
        _render_autocomplete_tags(
            "Current companies",
            "current_companies",
            "companies",
            search,
            email,
            password,
            disabled,
            "Search current companies…",
        )
        _render_scalar_field(
            "Current company domains",
            "current_companies_domains",
            search,
            disabled,
            "google.com; meta.com",
        )
        _render_text_list_field(
            "Exclude companies",
            "companies_to_exclude",
            search,
            disabled,
            "Acme Corp",
        )
        _render_text_list_field(
            "Exclude current companies",
            "current_companies_to_exclude",
            search,
            disabled,
            "Acme Corp",
        )
        _render_scalar_field(
            "Exclude company domains",
            "companies_domains_to_exclude",
            search,
            disabled,
            "acme.com",
        )
        _render_scalar_field(
            "Exclude current company domains",
            "current_companies_domains_to_exclude",
            search,
            disabled,
            "acme.com",
        )

        _render_autocomplete_tags(
            "Languages",
            "languages",
            "languages",
            search,
            email,
            password,
            disabled,
            "Search languages…",
        )
        _render_autocomplete_tags(
            "Schools",
            "schools",
            "schools",
            search,
            email,
            password,
            disabled,
            "Search schools…",
        )
        _render_scalar_field(
            "Current job title",
            "current_job_title",
            search,
            disabled,
            "engineering manager",
        )

        search["is_top_school"] = st.checkbox(
            "Top CS schools only",
            key="search_is_top_school",
            disabled=disabled,
        )

        likely = st.number_input(
            "Likely to move (0–1)",
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            key="search_likely_to_move",
            disabled=disabled,
            help="Leave at 0 to ignore this filter.",
        )
        search["likely_to_move_prob"] = likely if likely else None

        top_val = st.number_input(
            "Top N profiles",
            min_value=0,
            max_value=10000,
            step=10,
            key="search_top",
            disabled=disabled,
            help="Leave at 0 to ignore this filter.",
        )
        search["top"] = top_val if top_val else None

    if not disabled and email and password and job_queries_from_search(search):
        if st.button("Preview result count", key="search_preview_btn"):
            try:
                previews = []
                for query in job_queries_from_search(search):
                    one = dict(search)
                    one["text"] = query
                    previews.append((query, preview_search_count(one, email, password)))
                st.session_state["search_preview_counts"] = previews
            except Exception as exc:
                st.session_state["search_preview_counts"] = None
                st.error(str(exc))

    preview_counts = st.session_state.get("search_preview_counts")
    if preview_counts:
        for query, count in preview_counts:
            label = f"{count:,}" if count is not None else "?"
            st.caption(f"**{query}:** {label} matching profiles")

    out = normalize_search(search)
    out["is_first_name_female"] = bool(st.session_state.get("search_is_first_name_female", False))
    return out

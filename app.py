"""Streamlit UI — scrape getprog, save CSV, upload to Google Sheets."""
import re
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

import streamlit as st

from auth.getprog_session import check_login_status, login_getprog
from extract.search_params import validate_search
from pipeline import (
    clear_csv,
    clear_log,
    clear_stop,
    csv_path_for_sheet_name,
    latest_backup_csv,
    read_scrape_pid,
    request_stop,
    resolve_csv_path,
)
from settings import ROOT, load_settings, save_settings
from ui.search_form import collect_search_from_widgets, render_search_form, sync_search_widgets

LOG = ROOT / "logs" / "run.log"

LAYOUT_CSS = """
<style>
section.main > div.block-container {
    padding-top: 0.75rem;
    padding-left: 0.75rem;
    padding-right: 0.75rem;
    max-width: 100%;
}
div[data-testid="column"]:has(.settings-panel-marker) {
    max-width: 330px !important;
    min-width: 300px !important;
    flex: 0 0 330px !important;
}
div[data-testid="column"]:has(.settings-panel-marker) input {
    font-size: 0.9rem;
}
.action-bar { margin-bottom: 0.5rem; }
</style>
"""


def tail_log() -> str:
    return LOG.read_text(encoding="utf-8", errors="replace")[-12000:] if LOG.exists() else ""


def spawn(*args: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--scrape", *args]
    else:
        cmd = [sys.executable, str(ROOT / "scrape_getprog.py"), *args]
    subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )


def kill_scrape_process() -> None:
    pid = read_scrape_pid()
    if pid is None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                check=False,
            )
        else:
            import os
            import signal

            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


def _current_scrape_log(log_text: str) -> str:
    if "Starting scrape" not in log_text:
        return ""
    return log_text.split("Starting scrape")[-1]


def scrape_finished(log_text: str) -> bool:
    tail = _current_scrape_log(log_text)
    if not tail:
        return False
    if "Scrape complete" in tail:
        return True
    if "Stopped by user" in tail:
        return True
    return "ERROR:" in tail


def scrape_status(log_text: str) -> str:
    tail = _current_scrape_log(log_text)
    if not tail:
        return "failed"
    if "Stopped by user" in tail:
        return "stopped"
    if "ERROR:" in tail:
        if "CSV:" in tail and "Uploading" in tail:
            return "failed_after_csv"
        return "failed"
    if "New profiles: 0" in tail:
        return "done_no_new"
    return "done"


def _log_messages(log_text: str) -> List[str]:
    msgs: List[str] = []
    for line in log_text.splitlines():
        if "] " in line:
            msgs.append(line.split("] ", 1)[1].strip())
    return msgs


def _parse_progress(log_text: str, max_pages: int = 10) -> Dict[str, Any]:
    tail = log_text.split("Starting scrape")[-1] if "Starting scrape" in log_text else log_text
    pages: List[str] = []
    credits = ""
    fetched = 0
    new_count = 0
    skipped = 0
    csv_note = ""
    upload_total = 0
    uploaded_rows = 0
    upload_batch = 0
    upload_batches = 0
    upload_done = False
    error = ""
    phase = "starting"

    for msg in _log_messages(tail):
        if msg.startswith("Credits:"):
            credits = msg
        m = re.search(r"Page (\d+): (\d+) profiles", msg)
        if m:
            pages.append(f"Page {m.group(1)}: {m.group(2)} profiles")
            phase = "fetching"
        m = re.search(r"Fetched (\d+) profiles", msg)
        if m:
            fetched = int(m.group(1))
            phase = "dedupe"
        m = re.search(r"New profiles: (\d+) \| Already in CSV \(skipped\): (\d+)", msg)
        if m:
            new_count = int(m.group(1))
            skipped = int(m.group(2))
            phase = "save"
        if msg.startswith("CSV:"):
            csv_note = msg
            phase = "upload"
        m = re.search(r"Uploading (\d+) new rows", msg)
        if m:
            upload_total = int(m.group(1))
            phase = "upload"
        m = re.search(r"Upload batch (\d+)/(\d+)", msg)
        if m:
            upload_batch = int(m.group(1))
            upload_batches = int(m.group(2))
            phase = "upload"
        m = re.search(r"Batch (\d+) uploaded: (\d+) rows", msg)
        if m:
            appended_m = re.search(r"'_appended':\s*(\d+)", msg)
            if appended_m:
                uploaded_rows += int(appended_m.group(1))
            else:
                uploaded_rows += int(m.group(2))
            upload_batch = int(m.group(1))
            phase = "upload"
        if msg.startswith("Sheets upload OK"):
            upload_done = True
            phase = "done"
        if msg.startswith("ERROR:"):
            error = msg.replace("ERROR:", "").strip()

    pages_done = len(pages)
    progress_pct = 0.05
    progress_label = "Starting scrape…"

    if phase == "fetching" and pages_done:
        progress_pct = min(0.55, pages_done / max(max_pages, 1) * 0.55)
        progress_label = f"Fetching page {pages_done} of {max_pages}…"
    elif phase in ("dedupe", "save") and fetched:
        progress_pct = 0.60
        progress_label = f"Fetched {fetched} profiles — checking CSV for duplicates…"
    elif phase == "save" and (new_count or skipped):
        progress_pct = 0.65
        progress_label = f"Saving {new_count} new profiles ({skipped} already in CSV)"
    elif phase == "upload" and upload_total and not upload_done:
        done = min(uploaded_rows, upload_total)
        progress_pct = min(1.0, 0.70 + (done / upload_total) * 0.29)
        batch_note = f", batch {upload_batch}/{upload_batches}" if upload_batches else ""
        progress_label = f"Uploading to Google Sheets — {done}/{upload_total} rows{batch_note}…"
    elif upload_done or phase == "done":
        progress_pct = 1.0
        progress_label = "Scrape complete"

    progress_pct = min(1.0, max(0.0, progress_pct))

    return {
        "credits": credits,
        "pages": pages,
        "pages_done": pages_done,
        "max_pages": max_pages,
        "fetched": fetched,
        "new_count": new_count,
        "skipped": skipped,
        "csv_note": csv_note,
        "upload_total": upload_total,
        "uploaded_rows": uploaded_rows,
        "upload_batch": upload_batch,
        "upload_batches": upload_batches,
        "upload_done": upload_done,
        "error": error,
        "phase": phase,
        "progress_pct": progress_pct,
        "progress_label": progress_label,
        "events": _log_messages(tail),
    }


def render_live_progress(log_text: str, max_pages: int = 10) -> None:
    p = _parse_progress(log_text, max_pages=max_pages)

    st.progress(p["progress_pct"], text=p["progress_label"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Profiles fetched", p["fetched"] if p["fetched"] else "—")
    c2.metric("New (to save)", p["new_count"] if p["events"] else "—")
    c3.metric(
        "Already in CSV",
        p["skipped"] if p["events"] else "—",
        help="Profiles from this search that were already saved in a previous scrape (not an error).",
    )
    if p["upload_total"]:
        label = "Uploaded to Sheets"
        val = f"{p['uploaded_rows']}/{p['upload_total']}" if not p["upload_done"] else str(p["uploaded_rows"])
        c4.metric(label, val)
    else:
        c4.metric("Upload", "—")

    if p["skipped"] and p["fetched"]:
        st.caption(
            f"{p['skipped']} of {p['fetched']} fetched profiles were already in your CSV from a previous run "
            f"and were not saved again."
        )

    if p["credits"]:
        st.caption(p["credits"])

    for page in p["pages"][-8:]:
        st.markdown(f"- {page}")

    for msg in p["events"]:
        if msg.startswith("CSV:"):
            st.markdown(f"- **{msg}**")
        elif msg.startswith("Uploading"):
            st.markdown(f"- {msg}")
        elif msg.startswith("  Upload batch") or msg.startswith("  Batch"):
            st.markdown(f"- {msg}")
        elif msg.startswith("Sheets upload OK"):
            st.markdown(f"- **{msg}**")

    if p["error"]:
        st.error(p["error"])


def _default_login_status() -> Dict[str, Any]:
    return {
        "logged_in": False,
        "message": "Click **Login getprog** to connect (no API call until then).",
        "requests_left": None,
        "requests_limit": None,
    }


def collect_settings(s: Dict[str, Any]) -> Dict[str, Any]:
    """Merge live widget values (sheet URLs, search filters, etc.) before saving."""
    out = dict(s)
    for key, widget in (
        ("getprog_email", "cfg_email"),
        ("getprog_password", "cfg_password"),
        ("google_sheet_url", "cfg_sheet_url"),
        ("apps_script_url", "cfg_script_url"),
    ):
        if widget in st.session_state:
            out[key] = st.session_state[widget]
    if "cfg_headless" in st.session_state:
        out["headless"] = bool(st.session_state["cfg_headless"])
    if "cfg_max_pages" in st.session_state:
        out["max_pages"] = int(st.session_state["cfg_max_pages"] or 10)
    if "cfg_push" in st.session_state:
        out["push_to_sheets"] = bool(st.session_state["cfg_push"])
    out["search"] = collect_search_from_widgets(out.get("search") or {})
    return out


def persist_settings(s: Dict[str, Any]) -> Dict[str, Any]:
    """Save account, Sheet/Apps Script URLs, and current search settings to disk."""
    payload = collect_settings(s)
    from sheets.sheet_url import extract_spreadsheet_id

    disk = load_settings()
    new_id = extract_spreadsheet_id(payload.get("google_sheet_url") or "") or ""
    old_id = extract_spreadsheet_id(disk.get("google_sheet_url") or "") or ""
    if new_id != old_id:
        payload.pop("spreadsheet_name", None)
        payload.pop("spreadsheet_id", None)
    else:
        if not payload.get("spreadsheet_name"):
            payload["spreadsheet_name"] = disk.get("spreadsheet_name") or ""
        if not payload.get("spreadsheet_id"):
            payload["spreadsheet_id"] = disk.get("spreadsheet_id") or ""
    save_settings(payload)
    return payload


def render_settings_panel(s: Dict[str, Any], busy: bool) -> Dict[str, Any]:
    """Compact account settings — narrow left column."""
    st.markdown('<div class="settings-panel-marker"></div>', unsafe_allow_html=True)
    st.caption("Account")

    s["getprog_email"] = st.text_input("Email", s.get("getprog_email", ""), key="cfg_email")
    s["getprog_password"] = st.text_input(
        "Password", s.get("getprog_password", ""), type="password", key="cfg_password"
    )
    s["headless"] = st.checkbox("Headless", value=bool(s.get("headless", True)), key="cfg_headless")
    s["max_pages"] = st.number_input(
        "Max pages",
        min_value=1,
        max_value=50,
        value=int(s.get("max_pages") or 10),
        key="cfg_max_pages",
        help="100 profiles per page",
    )

    if st.button("Save", disabled=busy, key="cfg_save", use_container_width=True):
        s = persist_settings(s)
        st.session_state.login_status = None
        st.session_state["ui_notice"] = {
            "type": "success",
            "text": "Saved — Sheet URL, Apps Script URL, and search settings kept.",
        }
        st.rerun()

    with st.expander("Google Sheets", expanded=False):
        s["google_sheet_url"] = st.text_input(
            "Sheet URL",
            s.get("google_sheet_url", ""),
            key="cfg_sheet_url",
        )
        s["push_to_sheets"] = st.checkbox(
            "Push to Sheets", value=bool(s.get("push_to_sheets", True)), key="cfg_push"
        )
        s["apps_script_url"] = st.text_input(
            "Apps Script URL",
            s.get("apps_script_url", ""),
            key="cfg_script_url",
        )
        if st.button("Test Sheets", disabled=busy, key="cfg_test_sheets", use_container_width=True):
            s = persist_settings(s)
            script_url = (s.get("apps_script_url") or "").strip()
            sheet_url = (s.get("google_sheet_url") or "").strip()
            if not script_url or not sheet_url:
                st.error("Enter Sheet URL and Apps Script URL.")
            else:
                try:
                    from sheets.apps_script_client import check_apps_script_url
                    from sheets.sheet_url import extract_spreadsheet_id

                    sid = extract_spreadsheet_id(sheet_url)
                    if not sid:
                        st.error("Invalid Sheet URL.")
                    else:
                        result = check_apps_script_url(script_url, spreadsheet_id=sid)
                        name = str(result.get("spreadsheet") or "").strip()
                        if name:
                            s["spreadsheet_name"] = name
                            s["spreadsheet_id"] = sid
                            s = persist_settings(s)
                        csv_name = csv_path_for_sheet_name(name or None).name
                        st.success(f"OK: {name or sid} → `{csv_name}`")
                except Exception as exc:
                    st.error(str(exc))

    if st.button("Clear CSV", disabled=busy, key="cfg_clear_csv", use_container_width=True):
        s = persist_settings(s)
        try:
            cleared, deleted = clear_csv(s)
            if deleted:
                text = f"Cleared {cleared.name} only (matched the Google Sheet). Other CSVs were left as-is."
            else:
                text = f"No {cleared.name} to clear — that file is already gone. Other CSVs were not touched."
            st.session_state["ui_notice"] = {"type": "success", "text": text}
        except RuntimeError as exc:
            st.session_state["ui_notice"] = {"type": "error", "text": str(exc)}
        st.rerun()

    if busy and st.button("Stop scrape", type="secondary", use_container_width=True, key="cfg_stop"):
        request_stop()
        kill_scrape_process()
        st.session_state.scraping = False
        st.rerun()

    return s


def render_action_bar(s: Dict[str, Any], busy: bool) -> None:
    """Login / Start buttons — rendered before the heavy search form."""
    login = st.session_state.get("login_status") or _default_login_status()

    st.markdown('<div class="action-bar">', unsafe_allow_html=True)
    btn1, btn2 = st.columns(2)
    with btn1:
        if st.button("Login getprog", use_container_width=True, disabled=busy, type="secondary"):
            s = persist_settings(s)
            login_getprog(s["getprog_email"], s["getprog_password"], headless=False)
            st.session_state.login_status = check_login_status(
                s["getprog_email"],
                s["getprog_password"],
                allow_login=True,
            )
            st.rerun()
    with btn2:
        if st.button("Start scrape", use_container_width=True, disabled=busy, type="primary"):
            s = persist_settings(s)
            try:
                validate_search(s.get("search") or {})
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                email = (s.get("getprog_email") or "").strip()
                password = s.get("getprog_password") or ""
                if not email or not password:
                    st.error("Enter email and password (left), then Save.")
                else:
                    clear_log()
                    spawn("--run")
                    st.session_state.scraping = True
                    st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    if busy:
        return

    if login.get("logged_in"):
        st.success(login.get("message", "Logged in"))
        if login.get("requests_left") is not None:
            limit = login.get("requests_limit")
            limit_txt = f" / {limit}" if limit is not None else ""
            st.caption(f"Search credits: **{login['requests_left']}{limit_txt}**")
    else:
        st.caption(login.get("message", "Not logged in"))


def show_ui_notice() -> None:
    notice = st.session_state.pop("ui_notice", None)
    if not notice:
        return
    text = notice.get("text") or ""
    kind = notice.get("type") or "info"
    if kind == "success":
        st.success(text)
        try:
            st.toast(text, icon="✅")
        except Exception:
            pass
    elif kind == "warning":
        st.warning(text)
    elif kind == "error":
        st.error(text)
    else:
        st.info(text)


st.set_page_config(
    page_title="Scraper",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(LAYOUT_CSS, unsafe_allow_html=True)

if "session_boot" not in st.session_state:
    st.session_state.session_boot = True
    clear_stop()
    st.session_state.login_status = None
    for key in list(st.session_state.keys()):
        if str(key).startswith("search_"):
            del st.session_state[key]

if "scraping" not in st.session_state:
    st.session_state.scraping = False

if st.session_state.get("login_status") is None:
    st.session_state.login_status = _default_login_status()

s = load_settings()
log_text = tail_log()

# Seed search widgets from saved settings so Save / Clear / Start can persist them
# even when those buttons run before the search form renders.
if st.session_state.get("search_widgets_ready") is None:
    sync_search_widgets(s.get("search") or {})
    st.session_state.search_widgets_ready = True

if st.session_state.scraping:
    if scrape_finished(log_text):
        st.session_state.scraping = False
        st.session_state.last_scrape_status = scrape_status(log_text)
        st.session_state.login_status = None
        st.rerun()
    if read_scrape_pid() is None and _current_scrape_log(log_text):
        st.session_state.scraping = False
        st.session_state.last_scrape_status = scrape_status(log_text)
        st.session_state.login_status = None
        st.rerun()

busy = st.session_state.scraping

settings_col, main_col = st.columns([1, 3.2], gap="medium")

with settings_col:
    s = render_settings_panel(s, busy)

with main_col:
    st.title("Scraper")
    show_ui_notice()
    render_action_bar(s, busy)

    if busy:
        render_live_progress(log_text, max_pages=int(s.get("max_pages") or 10))
    else:
        with st.expander("Search filters", expanded=True):
            s["search"] = render_search_form(
                s,
                s.get("getprog_email", ""),
                s.get("getprog_password", ""),
                disabled=busy,
            )

        if st.session_state.get("last_scrape_status"):
            status = st.session_state.pop("last_scrape_status")
            if status == "done":
                st.success("Done — new profiles saved to CSV and uploaded to Google Sheets.")
            elif status == "done_no_new":
                st.info("Done — no new profiles (all already in CSV).")
            elif status == "stopped":
                st.warning("Stopped — scrape cancelled.")
            elif status == "failed_after_csv":
                st.warning("CSV saved, but Google Sheets upload failed — see log.")
            else:
                st.error("Failed — see log below.")

    if busy:
        st.caption(f"Updated {datetime.now().strftime('%H:%M:%S')}")
        time.sleep(2)
        st.rerun()

    latest = latest_backup_csv(s)
    if latest:
        st.caption(f"CSV: `{latest}`")
    else:
        expected = resolve_csv_path(s, fetch=False)
        if expected.name != "candidates.csv":
            st.caption(f"CSV: `{expected}` (not created yet)")

    with st.expander("Full log", expanded=False):
        st.code(log_text or "(empty)")

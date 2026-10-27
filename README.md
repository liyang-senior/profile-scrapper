# getprog scraper

Scrapes getprog search results and saves to **`data/{SheetName}.csv`** (named after the Google Spreadsheet, e.g. `LatAm.csv`). Only **new** profiles (by email) are appended and uploaded. Optionally pushes to **Google Sheets** by Role tab with profile photos.

## Requirements

- **Python 3.10 or newer** — check with `python --version` or `py --version`
- **Internet access** — for getprog login, API calls, and optional Google Sheets upload
- **Windows, macOS, or Linux**

After copying this folder to a new machine, create a fresh virtual environment. Do **not** rely on a copied `.venv` folder from another PC.

## Install (first time)

Open a terminal in the project folder (the directory that contains `app.py` and `requirements.txt`).

### 1. Create a virtual environment

**Windows (PowerShell):**

```powershell
cd path\to\Python Scraper
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**Windows (Command Prompt):**

```cmd
cd path\to\Python Scraper
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS / Linux:**

```bash
cd path/to/Python\ Scraper
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt should show `(.venv)` when the environment is active.

### 2. Install Python packages

With the virtual environment activated:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

This installs:

| Package | Purpose |
|---------|---------|
| `streamlit` | Web UI |
| `playwright` | Browser login to getprog |
| `httpx` | API and Google Sheets requests |
| `python-dotenv` | Optional `.env` settings |
| `PyYAML` | Config helpers |

### 3. Install the Playwright browser

Login uses Chromium. Install it once after `pip install`:

```powershell
playwright install chromium
```

Without this step, the first scrape may fail with a Playwright browser error.

## Run the app

With the virtual environment still activated, from the project folder:

```powershell
streamlit run app.py
```

Streamlit prints a local URL (usually **http://localhost:8501**). Open it in your browser.

To stop the app, press **Ctrl+C** in the terminal.

### Run again later

You only need steps 1–3 once. On later runs:

```powershell
cd path\to\Python Scraper
.\.venv\Scripts\Activate.ps1    # or source .venv/bin/activate on macOS/Linux
streamlit run app.py
```

## Optional: environment variables

Instead of typing settings in the sidebar every time, you can copy `.env.example` to `.env` (if present) or create `.env` in the project root:

```env
GETPROG_EMAIL=you@example.com
GETPROG_PASSWORD=your-password
SEARCH_URL=https://app.getprog.ai/...
GOOGLE_SHEET_URL=https://docs.google.com/spreadsheets/d/.../edit
APPS_SCRIPT_URL=https://script.google.com/macros/s/.../exec
```

Settings saved in the app are stored in **`config/user_settings.json`**.

## Google Sheets setup

1. Create or open your **Google Sheet** — copy its URL
2. **Extensions → Apps Script** — paste `google_apps_script/Code.gs` into that sheet's project
3. **Deploy → New deployment → Web app**
   - Execute as: **Me**
   - Who has access: **Anyone**
4. Copy the **`/exec`** URL (not `/dev`)
5. In the scraper sidebar enter:
   - **Google Sheet URL** — the spreadsheet where rows should go
   - **Apps Script Web App URL** — the `/exec` URL from step 4
6. Click **Test Sheets connection**

See **`google_apps_script/README.md`** for more detail on `/dev` vs `/exec` deployments.

The scraper sends your Sheet ID with each upload so data goes to the correct spreadsheet.

## Email outreach (separate from scraping)

Two Google Sheets:

1. **Candidates** — the Sheet URL in the scraper sidebar. Profiles land on role tabs (`sender` / `sent` stay blank until mail goes out).
2. **Templates only** — a different spreadsheet with columns **No | Title | Templates**. Paste its URL into `TEMPLATES_URL` in `google_apps_script/EmailOutreach.gs`.

Each sender Gmail account gets its own Apps Script copy of `EmailOutreach.gs`. That script reads unsent candidate rows, picks a random **Title** (subject) and a random **Templates** body, sends mail, then writes `sender` and `sent`.

See **`google_apps_script/README_OUTREACH.md`** for install steps.

## Scraped columns

photo, name, email (all emails, one per line in the cell), role, current company, years of experience, GitHub URL, LinkedIn URL, location, languages, phone numbers, role tab

## Run as exe (Windows) — single file, no source shared

From the project folder:

```powershell
.\build_exe.ps1
```

Share / copy this **whole folder**:

```text
dist\
  GetprogScraper.exe
  config\          <- search settings + Sheet URLs (after Save)
  data\            <- {SheetName}.csv after scrapes (e.g. LatAm.csv)
  logs\            <- run.log
  README.txt
```

Put **`icon.png`** in the project folder before building — the script converts it and embeds it as the exe icon.

All runtime files are written **next to the exe**. To move the app, copy the entire `dist` folder (not only the `.exe`).

On first run it creates `config\user_settings.json`, `data\{SheetName}.csv`, `logs\run.log`, and `storage_state.json` in that same folder.

Recipients need Playwright Chromium installed once on their PC (`playwright install chromium`) for getprog login.

Rebuild after code changes with the same `.\build_exe.ps1`, then redistribute the new `dist\GetprogScraper.exe`.

## Use

1. Enter getprog credentials and job queries (**one title per line**, e.g. AI Engineer, Full Stack Engineer, BI Engineer, ML Engineer, Data Engineer, Product Manager, DevOps Engineer)
2. **Start scrape** — disabled while running; use **Stop scrape** to cancel
3. New profiles with Gmail append to `data/{SheetName}.csv` (e.g. `LatAm.csv`) and upload to Sheets tabs by **role_tab** (from `config/role_aliases.yaml`; case-insensitive)

Tab names and similar titles live in **`config/role_aliases.yaml`**. After building the exe, edit that file next to `GetprogScraper.exe` (do not need to rebuild). Restart the app if it was already running, then scrape again.

## Notes

- Duplicate profiles already in **that sheet's CSV** are **skipped** (same name, role, company, and photo — compared one row at a time)
- Use **`/exec`** deployment — `/dev` URLs may fail with HTTP 401 from Python
- Refresh the page clears the log and re-checks getprog login live
- Output files: **`data/{SheetName}.csv`**, **`logs/run.log`**

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `python` not found | Install Python from [python.org](https://www.python.org/downloads/) and enable “Add to PATH” |
| `pip install` fails | Run `python -m pip install -r requirements.txt` |
| Playwright browser missing | Run `playwright install chromium` inside `.venv` |
| PowerShell won’t activate venv | Use `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Port 8501 in use | Run `streamlit run app.py --server.port 8502` |

# Build a portable GetprogScraper package in dist\
#   .\build_exe.ps1
#
# Result (copy this whole folder):
#   dist\
#     GetprogScraper.exe
#     config\          <- search settings / Sheet URLs (user_settings.json after first Save)
#     data\            <- {SheetName}.csv after scrapes
#     logs\            <- run.log
#     README.txt
#
# Reads icon.png, converts to .ico, embeds it in the exe.
# Builds into %TEMP% first so Windows Defender does not lock icon embed.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\icon.png")) {
    throw "Missing icon.png in the project folder. Copy your icon there, then rebuild."
}

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Creating .venv..."
    python -m venv .venv
}

Write-Host "Installing build dependencies..."
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pyinstaller pefile pillow

Write-Host "Installing Playwright Chromium (needed for getprog login)..."
.\.venv\Scripts\python.exe -m playwright install chromium

Write-Host "Converting icon.png -> assets\icon.ico..."
.\.venv\Scripts\python.exe .\scripts\make_icon.py
if (-not (Test-Path ".\assets\icon.ico")) {
    throw "Failed to create assets\icon.ico from icon.png"
}

$tmp = Join-Path $env:TEMP "gprog_icon_build"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory -Force -Path "$tmp\dist", "$tmp\work" | Out-Null

Write-Host "Building single-file exe in TEMP..."
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean `
    --distpath "$tmp\dist" `
    --workpath "$tmp\work" `
    ".\getprog_scraper.spec"

$built = Join-Path $tmp "dist\GetprogScraper.exe"
if (-not (Test-Path $built)) {
    throw "Build failed - missing $built"
}

$sizeMb = [math]::Round((Get-Item $built).Length / 1MB, 1)
if ((Get-Item $built).Length -lt 50MB) {
    throw "Build looks corrupt (only $sizeMb MB)"
}

.\.venv\Scripts\python.exe .\scripts\verify_exe_icon.py $built
if ($LASTEXITCODE -ne 0) {
    throw "Exe built but icon.png was not embedded"
}

Write-Host "Preparing portable dist\ package..."
if (Test-Path ".\dist") { Remove-Item -Recurse -Force ".\dist" }
New-Item -ItemType Directory -Force -Path ".\dist\config", ".\dist\data", ".\dist\logs" | Out-Null
Copy-Item $built ".\dist\GetprogScraper.exe" -Force

if (Test-Path ".\config\role_aliases.yaml") {
    Copy-Item ".\config\role_aliases.yaml" ".\dist\config\role_aliases.yaml" -Force
}

$readme = @"
Getprog Scraper — portable package
==================================

Run:  GetprogScraper.exe

Everything is saved NEXT TO the exe (this folder). Copy the whole folder to move the app.

  config\user_settings.json   search filters, Sheet URL, Apps Script URL, login (after Save)
  config\role_aliases.yaml    Sheet tab names + similar job titles (edit anytime)
  data\{SheetName}.csv        scraped profiles (named after the Google Sheet)
  logs\run.log                scrape log
  storage_state.json          getprog login session (created after Login)

Edit config\role_aliases.yaml to add or rename tabs / similar titles, then run a new scrape
(restart the exe if it was already open so the file is reloaded).
"@
Set-Content -Path ".\dist\README.txt" -Value $readme -Encoding UTF8

Write-Host ""
Write-Host "Done. Copy this whole folder:"
Write-Host "  .\dist\"
Write-Host ""
Write-Host "Contents:"
Write-Host "  GetprogScraper.exe  ($sizeMb MB)"
Write-Host "  config\   data\   logs\   README.txt"
Write-Host ""
Write-Host "CSV + search settings are written inside this same folder when you run the exe."

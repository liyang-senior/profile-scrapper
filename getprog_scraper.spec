# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onefile â€” one shareable .exe, no source folder."""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# SPECPATH is injected by PyInstaller when this spec runs.
# Built from project-root icon.png by scripts/make_icon.py (called from build_exe.ps1).
ICON_FILE = str(Path(SPECPATH) / "assets" / "icon.ico")

block_cipher = None

streamlit_datas, streamlit_binaries, streamlit_hidden = collect_all("streamlit")
yaml_datas, yaml_binaries, yaml_hidden = collect_all("yaml")
httpx_datas, httpx_binaries, httpx_hidden = collect_all("httpx")
playwright_datas, playwright_binaries, playwright_hidden = collect_all("playwright")

# app.py is only extracted to a temp folder at runtime (not left beside the exe).
datas = []
datas += streamlit_datas
datas += yaml_datas
datas += httpx_datas
datas += playwright_datas
datas += collect_data_files("streamlit")
datas += [("app.py", ".")]
datas += [("config/role_aliases.yaml", "config")]

project_hidden = []
for pkg in ("auth", "extract", "parse", "sheets", "ui"):
    project_hidden += collect_submodules(pkg)

hiddenimports = list(
    set(
        streamlit_hidden
        + yaml_hidden
        + httpx_hidden
        + playwright_hidden
        + project_hidden
        + [
            "streamlit.web.cli",
            "streamlit.runtime.scriptrunner.magic_funcs",
            "pandas",
            "pyarrow",
            "certifi",
            "dotenv",
            "yaml",
            "httpx",
            "playwright",
            "playwright.sync_api",
            "pipeline",
            "settings",
            "dedupe",
            "scrape_getprog",
            "app",
        ]
    )
)

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=streamlit_binaries + yaml_binaries + httpx_binaries + playwright_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="GetprogScraper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Icon from icon.png (converted to assets/icon.ico before this spec runs).
    icon=ICON_FILE,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)


# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for Speks.

Produces a one-dir distribution that embeds the Python runtime,
all dependencies (MkDocs, MkDocs-Material, FastAPI, etc.) and
Speks' own assets.

Build:
    pyinstaller speks.spec

Output:
    dist/speks/           (directory with speks.exe + supporting files)
"""

import importlib
import os
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_entry_point,
    collect_submodules,
    copy_metadata,
)

block_cipher = None

# ---------------------------------------------------------------------------
# Collect hidden imports & data files for key dependencies
# ---------------------------------------------------------------------------

# MkDocs + Material theme — they discover plugins/themes via entry-points
# and load templates, CSS, JS at runtime.
mkdocs_datas = collect_data_files("mkdocs")
mkdocs_material_datas = collect_data_files("mkdocs_material") + collect_data_files("material")
pymdownx_datas = collect_data_files("pymdownx")

# MkDocs needs dist-info metadata to discover its entry-points (plugins, themes)
mkdocs_metadata = (
    copy_metadata("mkdocs")
    + copy_metadata("mkdocs-material")
    + copy_metadata("pymdown-extensions")
    + copy_metadata("speks")
)

# Speks own assets
speks_datas = collect_data_files("speks")

# Markdown extensions ship data files (html templates, etc.)
markdown_datas = collect_data_files("markdown")

# Collect all submodules so nothing is missed by lazy imports
hidden_imports = (
    collect_submodules("speks")
    + collect_submodules("mkdocs")
    + collect_submodules("mkdocs_material")
    + collect_submodules("material")
    + collect_submodules("pymdownx")
    + collect_submodules("markdown")
    + collect_submodules("uvicorn")
    + collect_submodules("fastapi")
    + collect_submodules("pydantic")
    + collect_submodules("typer")
    + collect_submodules("rich")
    + [
        "watchfiles",
        "watchfiles._rust_notify",
    ]
)

all_datas = (
    speks_datas
    + mkdocs_datas
    + mkdocs_material_datas
    + pymdownx_datas
    + mkdocs_metadata
    + markdown_datas
)

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

a = Analysis(
    ["speks/cli.py"],
    pathex=[],
    binaries=[],
    datas=all_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "test",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="speks",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="speks",
)

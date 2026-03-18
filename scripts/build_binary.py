#!/usr/bin/env python3
"""Build a standalone Speks binary distribution.

Usage
-----
    python scripts/build_binary.py          # build for the current platform
    python scripts/build_binary.py --clean  # clean previous build artifacts first

The resulting distribution is placed in ``dist/speks/``.
On Windows this contains ``speks.exe``; on Linux/macOS, ``speks``.

Prerequisites
-------------
    pip install -e ".[build]"

Cross-compilation
-----------------
PyInstaller cannot cross-compile. To produce a Windows ``.exe`` you must
run this script **on Windows** (or in a Windows CI runner).  A GitHub
Actions workflow is provided in ``.github/workflows/build-binary.yml``.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = ROOT / "speks.spec"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"


def clean() -> None:
    """Remove previous build artifacts."""
    for d in (DIST_DIR, BUILD_DIR):
        if d.exists():
            print(f"Removing {d} …")
            shutil.rmtree(d)


def build() -> None:
    """Run PyInstaller with the project spec file."""
    if not SPEC_FILE.exists():
        print(f"ERROR: spec file not found: {SPEC_FILE}", file=sys.stderr)
        sys.exit(1)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        str(SPEC_FILE),
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("ERROR: PyInstaller build failed.", file=sys.stderr)
        sys.exit(result.returncode)

    output = DIST_DIR / "speks"
    if output.exists():
        print(f"\nBuild successful!  Distribution in: {output}")
        exe = output / ("speks.exe" if sys.platform == "win32" else "speks")
        if exe.exists():
            print(f"Executable: {exe}")
    else:
        print("WARNING: expected output directory not found.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Speks standalone binary.")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove dist/ and build/ before building.",
    )
    args = parser.parse_args()

    if args.clean:
        clean()

    build()


if __name__ == "__main__":
    main()

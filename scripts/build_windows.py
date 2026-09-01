#!/usr/bin/env python3
"""Build reproducible local Windows GUI and CLI executables with PyInstaller."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
SPEC_DIR = BUILD_DIR / "spec"


def _require_windows() -> None:
    if os.name != "nt":
        raise SystemExit("This build script must run on Windows.")


def _pyinstaller_run(arguments: list[str]) -> None:
    try:
        import PyInstaller.__main__
    except ImportError as exc:
        raise SystemExit(
            "PyInstaller is not installed. Run: pip install -r requirements-dev.txt"
        ) from exc

    PyInstaller.__main__.run(arguments)


def _common_args(name: str) -> list[str]:
    qss = ROOT / "src" / "ui" / "styles.qss"
    if not qss.is_file():
        raise SystemExit(f"Required stylesheet is missing: {qss}")
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    return [
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        name,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR / name),
        "--specpath",
        str(SPEC_DIR),
        "--add-data",
        f"{qss}:src/ui",
        "--collect-submodules",
        "keyring.backends",
        "--copy-metadata",
        "keyring",
    ]


def build_gui() -> Path:
    """Build the canonical RuntimeMainWindow GUI executable."""
    name = "WingetUniversalDashboard"
    _pyinstaller_run(
        [
            *_common_args(name),
            "--windowed",
            str(ROOT / "launcher.py"),
        ]
    )
    return DIST_DIR / f"{name}.exe"


def build_cli() -> Path:
    """Build the console CLI executable."""
    name = "WingetUniversalDashboardCLI"
    _pyinstaller_run(
        [
            *_common_args(name),
            str(ROOT / "cli_launcher.py"),
        ]
    )
    return DIST_DIR / f"{name}.exe"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="remove existing build/dist directories before packaging",
    )
    args = parser.parse_args()

    _require_windows()
    if args.clean_output:
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
        shutil.rmtree(DIST_DIR, ignore_errors=True)

    artifacts = [build_gui(), build_cli()]
    missing = [str(path) for path in artifacts if not path.is_file()]
    if missing:
        raise SystemExit(
            "Build completed without expected artifact(s): " + ", ".join(missing)
        )

    print("Built artifacts:")
    for artifact in artifacts:
        print(f"  {artifact} ({artifact.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

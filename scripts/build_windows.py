#!/usr/bin/env python3
"""Build reproducible local Windows GUI and CLI executables with PyInstaller."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil

from release_common import (
    CLI_EXE,
    GUI_EXE,
    current_git_commit,
    read_version,
    require_x64_pe,
    worktree_is_dirty,
    write_build_identity,
)


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


def _version_file(name: str, description: str) -> Path:
    version, numeric = read_version()
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    destination = BUILD_DIR / f"pyinstaller-version-{name}.txt"
    numeric_tuple = repr(numeric)
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numeric_tuple},
    prodvers={numeric_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'CyberIncome'),
          StringStruct('FileDescription', '{description}'),
          StringStruct('FileVersion', '{version}'),
          StringStruct('InternalName', '{name}'),
          StringStruct('OriginalFilename', '{name}.exe'),
          StringStruct('ProductName', 'Winget Universal Dashboard'),
          StringStruct('ProductVersion', '{version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    destination.write_text(content, encoding="utf-8")
    return destination


def _common_args(name: str, version_file: Path) -> list[str]:
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
        "--version-file",
        str(version_file),
        "--add-data",
        f"{qss}:src/ui",
        "--collect-submodules",
        "keyring.backends",
        "--copy-metadata",
        "keyring",
    ]


def build_gui() -> Path:
    name = "WingetUniversalDashboard"
    version_file = _version_file(name, "Winget Universal Dashboard")
    _pyinstaller_run(
        [
            *_common_args(name, version_file),
            "--windowed",
            str(ROOT / "launcher.py"),
        ]
    )
    return GUI_EXE


def build_cli() -> Path:
    name = "WingetUniversalDashboardCLI"
    version_file = _version_file(name, "Winget Universal Dashboard CLI")
    _pyinstaller_run(
        [
            *_common_args(name, version_file),
            str(ROOT / "cli_launcher.py"),
        ]
    )
    return CLI_EXE


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="remove existing build/dist directories before packaging",
    )
    args = parser.parse_args()

    _require_windows()
    version, _numeric = read_version()
    commit = current_git_commit()
    dirty = worktree_is_dirty()

    if args.clean_output:
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
        shutil.rmtree(DIST_DIR, ignore_errors=True)

    artifacts = [build_gui(), build_cli()]
    require_x64_pe(artifacts)
    write_build_identity(version, commit, dirty=dirty)

    print("Built AMD64 artifacts:")
    for artifact in artifacts:
        print(f"  {artifact} ({artifact.stat().st_size:,} bytes)")
    print(f"Source identity: v{version} @ {commit} (dirty={dirty})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build the Windows x64 Inno Setup installer from packaged app artifacts."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess

from release_common import (
    BUILD_INFO_FILE,
    CLI_EXE,
    GUI_EXE,
    ROOT,
    SETUP_EXE,
    numeric_version_text,
    read_version,
    require_build_identity,
    require_clean_worktree,
    require_x64_pe,
)


INSTALLER_SCRIPT = ROOT / "installer" / "WingetUniversalDashboard.iss"


def find_iscc() -> Path:
    explicit = os.getenv("INNO_SETUP_COMPILER", "").strip()
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    for executable in ("ISCC.exe", "ISCC"):
        found = shutil.which(executable)
        if found:
            candidates.append(Path(found))
    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.getenv(env_name)
        if not base:
            continue
        base_path = Path(base)
        candidates.extend([
            base_path / "Inno Setup 7" / "ISCC.exe",
            base_path / "Programs" / "Inno Setup 7" / "ISCC.exe",
        ])
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Inno Setup compiler (ISCC.exe) was not found. Install current 64-bit "
        "Inno Setup 7 with: winget install --id JRSoftware.InnoSetup.7 -e "
        "-s winget -i, or set INNO_SETUP_COMPILER to ISCC.exe."
    )


def _require_inno_7(compiler: Path) -> None:
    completed = subprocess.run(
        [str(compiler), "/?"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors="replace", check=False, timeout=30,
    )
    banner = f"{completed.stdout}\n{completed.stderr}"
    if "Inno Setup 7" not in banner:
        raise RuntimeError(
            f"{compiler} does not appear to be Inno Setup 7. "
            "Install JRSoftware.InnoSetup.7 or set INNO_SETUP_COMPILER accordingly."
        )


def build_installer() -> Path:
    if os.name != "nt":
        raise SystemExit("Installer builds must run on Windows.")
    if not INSTALLER_SCRIPT.is_file():
        raise SystemExit(f"Installer script is missing: {INSTALLER_SCRIPT}")

    version, numeric = read_version()
    commit = require_clean_worktree()
    require_build_identity(version, commit)
    require_x64_pe([GUI_EXE, CLI_EXE])
    if not BUILD_INFO_FILE.is_file():
        raise SystemExit(f"Build identity file is missing: {BUILD_INFO_FILE}")

    compiler = find_iscc()
    _require_inno_7(compiler)
    command = [
        str(compiler),
        f"--define=AppVersion={version}",
        f"--define=AppVersionNumeric={numeric_version_text(numeric)}",
        str(INSTALLER_SCRIPT),
    ]
    print("$", subprocess.list2cmdline(command))
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"Inno Setup failed with exit code {completed.returncode}")
    if not SETUP_EXE.is_file():
        raise SystemExit(f"Installer compiler did not create: {SETUP_EXE}")
    require_x64_pe([SETUP_EXE])
    print(f"Built x64 installer: {SETUP_EXE} ({SETUP_EXE.stat().st_size:,} bytes)")
    return SETUP_EXE


def main() -> int:
    argparse.ArgumentParser().parse_args()
    build_installer()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

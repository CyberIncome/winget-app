#!/usr/bin/env python3
"""Build complete local Windows release assets, installer, and checksums."""

from __future__ import annotations

import argparse
import subprocess
import sys

from release_common import DIST_DIR, ROOT, read_version, write_sha256_manifest


GUI_EXE = DIST_DIR / "WingetUniversalDashboard.exe"
CLI_EXE = DIST_DIR / "WingetUniversalDashboardCLI.exe"
SETUP_EXE = DIST_DIR / "WingetUniversalDashboard-Setup-x64.exe"
CHECKSUMS = DIST_DIR / "SHA256SUMS.txt"


def _run(script: str, *arguments: str) -> None:
    command = [sys.executable, str(ROOT / "scripts" / script), *arguments]
    print("$", subprocess.list2cmdline(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-app-build",
        action="store_true",
        help="reuse existing dist GUI/CLI executables instead of rebuilding them",
    )
    parser.add_argument(
        "--sign",
        action="store_true",
        help="sign GUI/CLI before installer creation and sign installer afterward",
    )
    args = parser.parse_args()

    version, _numeric = read_version()
    print(f"Building Winget Universal Dashboard release v{version}")

    if not args.skip_app_build:
        _run("build_windows.py", "--clean-output")

    if args.sign:
        _run("sign_windows.py", str(GUI_EXE), str(CLI_EXE))

    _run("build_installer.py")

    if args.sign:
        _run("sign_windows.py", str(SETUP_EXE))

    artifacts = [SETUP_EXE, GUI_EXE, CLI_EXE]
    write_sha256_manifest(artifacts, CHECKSUMS)

    print("\nRelease assets:")
    for path in [*artifacts, CHECKSUMS]:
        print(f"  {path} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

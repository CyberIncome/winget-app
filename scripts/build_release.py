#!/usr/bin/env python3
"""Build complete local Windows release assets, installer, and checksums."""

from __future__ import annotations

import argparse
import subprocess
import sys

from release_common import (
    CHECKSUMS_FILE,
    CLI_EXE,
    GUI_EXE,
    HASHED_RELEASE_ASSETS,
    ROOT,
    SETUP_EXE,
    current_git_commit,
    read_version,
    require_build_identity,
    require_clean_worktree,
    require_x64_pe,
    verify_sha256_manifest,
    write_sha256_manifest,
)


def _run(script: str, *arguments: str) -> None:
    command = [sys.executable, str(ROOT / "scripts" / script), *arguments]
    print("$", subprocess.list2cmdline(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-app-build",
        action="store_true",
        help=(
            "reuse existing GUI/CLI only when BUILD_INFO.json proves they were "
            "built from the exact clean VERSION/commit being released"
        ),
    )
    parser.add_argument(
        "--sign",
        action="store_true",
        help="sign GUI/CLI before installer creation and sign installer afterward",
    )
    args = parser.parse_args()

    version, _numeric = read_version()
    commit = require_clean_worktree()
    print(f"Building Winget Universal Dashboard release v{version} @ {commit}")

    if args.skip_app_build:
        require_build_identity(version, commit)
        require_x64_pe([GUI_EXE, CLI_EXE])
    else:
        _run("build_windows.py", "--clean-output")
        if current_git_commit() != commit:
            raise RuntimeError("Source commit changed during the release build.")
        require_build_identity(version, commit)

    if args.sign:
        _run("sign_windows.py", str(GUI_EXE), str(CLI_EXE))

    _run("build_installer.py")

    if args.sign:
        _run("sign_windows.py", str(SETUP_EXE))

    require_x64_pe([SETUP_EXE, GUI_EXE, CLI_EXE])
    write_sha256_manifest(HASHED_RELEASE_ASSETS, CHECKSUMS_FILE)
    verify_sha256_manifest(HASHED_RELEASE_ASSETS, CHECKSUMS_FILE)

    print("\nRelease assets:")
    for path in [*HASHED_RELEASE_ASSETS, CHECKSUMS_FILE]:
        print(f"  {path} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

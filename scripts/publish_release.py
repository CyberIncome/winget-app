#!/usr/bin/env python3
"""Publish local release assets to GitHub using the authenticated gh CLI."""

from __future__ import annotations

import argparse
import shutil
import subprocess

from release_common import (
    DIST_DIR,
    ROOT,
    read_version,
    require_build_version,
    require_files,
)


REPOSITORY = "CyberIncome/winget-app"
ASSETS = [
    DIST_DIR / "WingetUniversalDashboard-Setup-x64.exe",
    DIST_DIR / "WingetUniversalDashboard.exe",
    DIST_DIR / "WingetUniversalDashboardCLI.exe",
    DIST_DIR / "SHA256SUMS.txt",
]


def _capture(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def _require_clean_master(allow_non_master: bool) -> str:
    status = _capture("git", "status", "--porcelain")
    if status:
        raise SystemExit("Refusing to publish from a dirty working tree.")
    branch = _capture("git", "branch", "--show-current")
    if branch != "master" and not allow_non_master:
        raise SystemExit(
            f"Refusing to publish from branch {branch!r}; merge to master first. "
            "Use --allow-non-master only for an intentional prerelease/test."
        )
    return _capture("git", "rev-parse", "HEAD")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--publish",
        action="store_true",
        help="publish publicly instead of creating a draft GitHub Release",
    )
    parser.add_argument(
        "--prerelease",
        action="store_true",
        help="mark the GitHub Release as a prerelease",
    )
    parser.add_argument(
        "--allow-non-master",
        action="store_true",
        help="allow creating a release whose target is not master",
    )
    args = parser.parse_args()

    gh = shutil.which("gh")
    if not gh:
        raise SystemExit(
            "GitHub CLI (gh) is required. Install it with: "
            "winget install --id GitHub.cli -e -s winget"
        )

    version, _numeric = read_version()
    tag = f"v{version}"
    head = _require_clean_master(args.allow_non_master)
    require_build_version(version)
    require_files(ASSETS)

    if subprocess.run([gh, "auth", "status"], cwd=ROOT, check=False).returncode != 0:
        raise SystemExit("GitHub CLI is not authenticated. Run: gh auth login")

    existing = subprocess.run(
        [gh, "release", "view", tag, "-R", REPOSITORY],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if existing.returncode == 0:
        raise SystemExit(f"Release {tag} already exists; refusing to overwrite it.")

    command = [
        gh,
        "release",
        "create",
        tag,
        *(str(path) for path in ASSETS),
        "-R",
        REPOSITORY,
        "--target",
        head,
        "--title",
        f"Winget Universal Dashboard {tag}",
        "--generate-notes",
    ]
    if not args.publish:
        command.append("--draft")
    if args.prerelease or "-" in version:
        command.append("--prerelease")

    print("$", subprocess.list2cmdline(command))
    subprocess.run(command, cwd=ROOT, check=True)
    print(f"Created {'published' if args.publish else 'draft'} GitHub Release {tag}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

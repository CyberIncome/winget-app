#!/usr/bin/env python3
"""Publish local release assets to GitHub using the authenticated gh CLI."""

from __future__ import annotations

import argparse
import shutil
import subprocess

from release_common import (
    CHECKSUMS_FILE,
    CLI_EXE,
    GUI_EXE,
    HASHED_RELEASE_ASSETS,
    ROOT,
    SETUP_EXE,
    UPLOAD_RELEASE_ASSETS,
    current_git_branch,
    is_prerelease,
    read_version,
    require_build_identity,
    require_clean_worktree,
    require_files,
    require_x64_pe,
    verify_sha256_manifest,
)


REPOSITORY = "CyberIncome/winget-app"


def _require_pushed_head(branch: str, head: str) -> None:
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise SystemExit(
            f"Could not verify origin/{branch}; push the release commit first."
        )
    remote_head = result.stdout.split()[0].lower()
    if remote_head != head.lower():
        raise SystemExit(
            f"Local {branch} ({head}) does not match origin/{branch} ({remote_head}). "
            "Push the exact release commit before publishing."
        )


def _require_publish_source(allow_non_master: bool) -> tuple[str, str]:
    head = require_clean_worktree()
    branch = current_git_branch()
    if not branch:
        raise SystemExit("Refusing to publish from detached HEAD.")
    if branch != "master" and not allow_non_master:
        raise SystemExit(
            f"Refusing to publish from branch {branch!r}; merge to master first. "
            "Use --allow-non-master only for an intentional prerelease/test."
        )
    _require_pushed_head(branch, head)
    return branch, head


def _require_unused_remote_tag(tag: str) -> None:
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--tags", "origin", f"refs/tags/{tag}"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        raise SystemExit(
            f"Remote tag {tag} already exists; refusing to create an ambiguous release."
        )
    if result.returncode not in (0, 2):
        raise SystemExit(f"Could not verify whether remote tag {tag} already exists.")


def _release_preamble() -> str:
    return (
        "## Download\n\n"
        "**Most users should download `WingetUniversalDashboard-Setup-x64.exe`.** "
        "It installs the app normally and includes the CLI.\n\n"
        "- `WingetUniversalDashboard-Portable-x64.exe` — portable GUI; no installation.\n"
        "- `WingetUniversalDashboard-CLI-x64.exe` — standalone command-line build.\n"
        "- `SHA256SUMS.txt` — checksums for release verification.\n\n"
    )


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
        help="allow creating a release from a pushed non-master branch",
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
    branch, head = _require_publish_source(args.allow_non_master)

    require_build_identity(version, head)
    require_files(UPLOAD_RELEASE_ASSETS)
    require_x64_pe([SETUP_EXE, GUI_EXE, CLI_EXE])
    verify_sha256_manifest(HASHED_RELEASE_ASSETS, CHECKSUMS_FILE)
    _require_unused_remote_tag(tag)

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
        *(str(path) for path in UPLOAD_RELEASE_ASSETS),
        "-R",
        REPOSITORY,
        "--target",
        head,
        "--title",
        f"Winget Universal Dashboard {tag}",
        "--generate-notes",
        "--notes",
        _release_preamble(),
    ]
    if not args.publish:
        command.append("--draft")
    if args.prerelease or is_prerelease(version) or branch != "master":
        command.append("--prerelease")

    print("$", subprocess.list2cmdline(command))
    subprocess.run(command, cwd=ROOT, check=True)
    print(f"Created {'published' if args.publish else 'draft'} GitHub Release {tag}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

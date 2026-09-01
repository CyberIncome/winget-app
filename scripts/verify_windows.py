#!/usr/bin/env python3
"""Run the release-relevant verification gate on a Windows workstation.

This is intentionally local/offline-first. It does not require GitHub Actions
and does not modify installed packages. Pass ``--live-winget`` to add a
read-only Winget update scan after the deterministic checks pass.
"""

from __future__ import annotations

import argparse
from importlib import metadata
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "NOT INSTALLED"


def _run(label: str, command: list[str], timeout: int) -> bool:
    print(f"\n== {label} ==")
    print("$", subprocess.list2cmdline(command))
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"FAIL: timed out after {timeout}s", file=sys.stderr)
        return False
    except OSError as exc:
        print(f"FAIL: could not start: {exc}", file=sys.stderr)
        return False

    if completed.returncode != 0:
        print(
            f"FAIL: exit code {completed.returncode}",
            file=sys.stderr,
        )
        return False
    print("PASS")
    return True


def _print_environment() -> None:
    print("Winget Universal Dashboard - local Windows verification")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Executable: {sys.executable}")
    for distribution in (
        "PySide6",
        "pywin32",
        "requests",
        "click",
        "keyring",
        "pytest",
        "pytest-qt",
        "ruff",
    ):
        print(f"{distribution}: {_version(distribution)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live-winget",
        action="store_true",
        help=(
            "also run read-only winget --version and CLI update-scan "
            "checks"
        ),
    )
    args = parser.parse_args()

    if os.name != "nt":
        print(
            "REFUSED: this acceptance gate must run on Windows.",
            file=sys.stderr,
        )
        return 2

    _print_environment()

    checks = [
        (
            "compile all Python sources",
            [
                sys.executable,
                "-m",
                "compileall",
                "-q",
                "src",
                "tests",
                "scripts",
            ],
            120,
        ),
        (
            "static correctness lint",
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--select",
                "E9,F63,F7,F82",
                "src",
                "tests",
                "scripts",
            ],
            120,
        ),
        (
            "native Windows lifecycle integration",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_windows_lifecycle.py",
                "tests/test_remote_versions.py",
            ],
            180,
        ),
        (
            "full pytest suite",
            [sys.executable, "-m", "pytest", "-q"],
            600,
        ),
        (
            "CLI import/command smoke",
            [sys.executable, "-m", "src.cli", "--help"],
            60,
        ),
        (
            "production GUI create/close smoke",
            [sys.executable, "scripts/smoke_gui.py"],
            60,
        ),
    ]

    if args.live_winget:
        checks.extend(
            [
                ("Winget executable", ["winget", "--version"], 60),
                (
                    "read-only Winget update scan",
                    [
                        sys.executable,
                        "-m",
                        "src.cli",
                        "--json-output",
                        "check",
                    ],
                    600,
                ),
            ]
        )

    failures = 0
    for label, command, timeout in checks:
        if not _run(label, command, timeout):
            failures += 1

    print("\n== verdict ==")
    if failures:
        print(f"FAILED: {failures} verification check(s) failed")
        return 1
    print("PASSED: all requested verification checks succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

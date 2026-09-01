#!/usr/bin/env python3
"""Silently install, smoke, and uninstall the Inno Setup release installer."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from release_common import SETUP_EXE


APP_NAME = "Winget Universal Dashboard"
DEFAULT_INSTALL_DIR = (
    Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    / "Programs"
    / "WingetUniversalDashboard"
)


def _find_existing_uninstall_entries() -> list[str]:
    if os.name != "nt":
        return []
    import winreg

    found: list[str] = []
    path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        return found
    with root:
        index = 0
        while True:
            try:
                name = winreg.EnumKey(root, index)
            except OSError:
                break
            index += 1
            try:
                with winreg.OpenKey(root, name) as subkey:
                    display_name, _kind = winreg.QueryValueEx(subkey, "DisplayName")
            except (FileNotFoundError, OSError):
                continue
            if str(display_name).strip() == APP_NAME:
                found.append(name)
    return found


def _require_no_existing_install() -> None:
    entries = _find_existing_uninstall_entries()
    if DEFAULT_INSTALL_DIR.exists() or entries:
        details = []
        if DEFAULT_INSTALL_DIR.exists():
            details.append(str(DEFAULT_INSTALL_DIR))
        if entries:
            details.append("HKCU uninstall entry: " + ", ".join(entries))
        raise SystemExit(
            "Installer smoke refuses to run while a normal installation exists: "
            + "; ".join(details)
        )


def _run(
    command: list[str], *, env: dict[str, str] | None = None, timeout: int = 180
) -> None:
    print("$", subprocess.list2cmdline(command))
    environment = os.environ.copy()
    if env:
        environment.update(env)
    completed = subprocess.run(
        command,
        check=False,
        env=environment,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}: "
            f"{subprocess.list2cmdline(command)}"
        )


def _wait_for_uninstall_complete(
    gui: Path,
    cli: Path,
    build_info: Path,
    *,
    timeout: float = 30.0,
) -> None:
    """Wait for Inno's detached cleanup process to finish removing app state."""
    deadline = time.monotonic() + timeout
    while True:
        remaining_files = [
            path for path in (gui, cli, build_info) if path.exists()
        ]
        uninstall_entries = _find_existing_uninstall_entries()
        if not remaining_files and not uninstall_entries:
            return
        if time.monotonic() >= deadline:
            details = [str(path) for path in remaining_files]
            details.extend(f"HKCU:{entry}" for entry in uninstall_entries)
            raise RuntimeError(
                "Silent uninstall did not finish cleanup within "
                f"{timeout:.0f}s: " + ", ".join(details)
            )
        time.sleep(0.2)


def _cleanup_temp_tree(root: Path, *, timeout: float = 30.0) -> None:
    """Remove the smoke directory, retrying transient Windows sharing violations.

    Inno Setup's uninstaller may return before its detached cleanup helper closes
    the /LOG file. A normal TemporaryDirectory context removes the directory
    immediately and can therefore fail with WinError 32 even though uninstall
    itself succeeded. Retry boundedly instead of ignoring cleanup failures.
    """
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while True:
        try:
            shutil.rmtree(root)
            return
        except FileNotFoundError:
            return
        except OSError as exc:
            last_error = exc
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Timed out waiting for installer-smoke temporary files to be "
                    f"released: {root}"
                ) from last_error
            time.sleep(0.25)


def smoke_installer(installer: Path) -> None:
    if os.name != "nt":
        raise SystemExit("Installer smoke must run on Windows.")
    if not installer.is_file():
        raise SystemExit(f"Installer is missing: {installer}")

    _require_no_existing_install()

    root = Path(tempfile.mkdtemp(prefix="wud-installer-smoke-"))
    try:
        install_dir = root / "app"
        setup_log = root / "setup.log"
        uninstall_log = root / "uninstall.log"

        _run(
            [
                str(installer),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                "/SP-",
                "/CURRENTUSER",
                "/NOICONS",
                f"/DIR={install_dir}",
                f"/LOG={setup_log}",
            ],
            timeout=300,
        )

        gui = install_dir / "WingetUniversalDashboard.exe"
        cli = install_dir / "WingetUniversalDashboardCLI.exe"
        build_info = install_dir / "BUILD_INFO.json"
        if not gui.is_file() or not cli.is_file() or not build_info.is_file():
            raise RuntimeError(
                "Installer completed but expected GUI/CLI/build identity files "
                "were not installed."
            )

        _run([str(cli), "--help"], timeout=60)
        _run([str(gui)], env={"WUD_PACKAGED_SMOKE": "1"}, timeout=90)

        uninstallers = sorted(install_dir.glob("unins*.exe"))
        if len(uninstallers) != 1:
            raise RuntimeError(
                f"Expected exactly one Inno uninstaller, found {len(uninstallers)}"
            )
        _run(
            [
                str(uninstallers[0]),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                f"/LOG={uninstall_log}",
            ],
            timeout=300,
        )

        _wait_for_uninstall_complete(gui, cli, build_info)
    finally:
        _cleanup_temp_tree(root)

    print("Installer install / launch / uninstall smoke: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--installer",
        type=Path,
        default=SETUP_EXE,
        help="installer executable to test",
    )
    args = parser.parse_args()
    smoke_installer(args.installer.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

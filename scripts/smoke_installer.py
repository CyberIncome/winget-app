#!/usr/bin/env python3
"""Silently install, smoke, and uninstall the Inno Setup release installer."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import time

from release_common import DIST_DIR


DEFAULT_INSTALLER = DIST_DIR / "WingetUniversalDashboard-Setup-x64.exe"


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


def smoke_installer(installer: Path) -> None:
    if os.name != "nt":
        raise SystemExit("Installer smoke must run on Windows.")
    if not installer.is_file():
        raise SystemExit(f"Installer is missing: {installer}")

    with tempfile.TemporaryDirectory(prefix="wud-installer-smoke-") as temp:
        root = Path(temp)
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
        if not gui.is_file() or not cli.is_file():
            raise RuntimeError(
                "Installer completed but expected GUI/CLI files were not installed."
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

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and (gui.exists() or cli.exists()):
            time.sleep(0.2)
        if gui.exists() or cli.exists():
            raise RuntimeError("Silent uninstall left application binaries behind.")

    print("Installer install / launch / uninstall smoke: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--installer",
        type=Path,
        default=DEFAULT_INSTALLER,
        help="installer executable to test",
    )
    args = parser.parse_args()
    smoke_installer(args.installer.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

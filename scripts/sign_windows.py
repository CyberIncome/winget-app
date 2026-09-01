#!/usr/bin/env python3
"""Optionally Authenticode-sign Windows release executables with signtool."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess


def find_signtool() -> Path:
    explicit = os.getenv("SIGNTOOL_EXE", "").strip()
    if explicit and Path(explicit).is_file():
        return Path(explicit)

    found = shutil.which("signtool.exe") or shutil.which("signtool")
    if found:
        return Path(found)

    base = Path(os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    kits = base / "Windows Kits" / "10" / "bin"
    if kits.is_dir():
        candidates = sorted(
            kits.glob("*/x64/signtool.exe"),
            key=lambda path: path.parent.parent.name,
            reverse=True,
        )
        if candidates:
            return candidates[0]

    raise FileNotFoundError(
        "signtool.exe was not found. Install a Windows SDK or set SIGNTOOL_EXE."
    )


def sign_files(paths: list[Path]) -> None:
    thumbprint = os.getenv("WUD_SIGN_CERT_SHA1", "").replace(" ", "").strip()
    if not thumbprint:
        raise SystemExit(
            "WUD_SIGN_CERT_SHA1 is required for --sign. Set it to the SHA-1 "
            "thumbprint of the Authenticode certificate."
        )

    timestamp_url = os.getenv(
        "WUD_TIMESTAMP_URL", "http://timestamp.digicert.com"
    ).strip()
    signtool = find_signtool()

    for path in paths:
        if not path.is_file():
            raise SystemExit(f"Cannot sign missing file: {path}")
        command = [
            str(signtool),
            "sign",
            "/fd",
            "SHA256",
            "/sha1",
            thumbprint,
            "/tr",
            timestamp_url,
            "/td",
            "SHA256",
            str(path),
        ]
        print("$", subprocess.list2cmdline(command))
        subprocess.run(command, check=True)

        verify = [str(signtool), "verify", "/pa", "/v", str(path)]
        print("$", subprocess.list2cmdline(verify))
        subprocess.run(verify, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    sign_files(args.files)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

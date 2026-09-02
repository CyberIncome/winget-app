"""Fast-path system inventory collection for the managed GUI worker.

Startup inventory is deliberately conservative: registry DisplayVersion values
are trusted when present, and shortcut targets are inspected directly. The old
implementation recursively walked install directories trying to guess missing
versions; on large Windows installations that could turn startup into a minute+
filesystem crawl and could still return the wrong executable/version.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time


_VERSION_FILES = ("VERSION", "version.txt", "config.ini", "manifest.json")
_MAX_SHORTCUTS = 10_000
_MAX_METADATA_BYTES = 4096


def collect_portable_apps() -> list[dict]:
    """Scan Windows shortcuts while reusing one COM shell for the whole pass."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut_locations = [
            os.path.join(
                os.environ.get("APPDATA", ""),
                r"Microsoft\Windows\Start Menu\Programs",
            ),
            os.path.join(
                os.environ.get("ProgramData", ""),
                r"Microsoft\Windows\Start Menu\Programs",
            ),
            os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),
        ]
        potential_apps = []
        seen_targets = set()
        inspected = 0
        for location in shortcut_locations:
            if not location or not os.path.exists(location):
                continue
            for root, _dirs, files in os.walk(location, followlinks=False):
                for filename in files:
                    if not filename.lower().endswith(".lnk"):
                        continue
                    inspected += 1
                    if inspected > _MAX_SHORTCUTS:
                        return potential_apps
                    shortcut_path = os.path.join(root, filename)
                    try:
                        target = shell.CreateShortCut(shortcut_path).Targetpath
                    except Exception:
                        continue
                    if not target or not target.lower().endswith(".exe"):
                        continue
                    target_key = os.path.normcase(os.path.abspath(target))
                    if target_key in seen_targets:
                        continue
                    seen_targets.add(target_key)
                    potential_apps.append(
                        {
                            "name": os.path.splitext(filename)[0],
                            "path": target,
                            "folder": os.path.dirname(target),
                        }
                    )
        return potential_apps
    finally:
        pythoncom.CoUninitialize()


def _extract_nearby_version(folder: str | None) -> str | None:
    """Inspect only known metadata files in one directory; never recurse."""
    if not folder or not os.path.isdir(folder):
        return None
    for filename in _VERSION_FILES:
        path = Path(folder) / filename
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()[:_MAX_METADATA_BYTES]
            text = raw.decode("utf-8", errors="ignore")
        except OSError:
            continue

        if filename.lower() == "manifest.json":
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                value = payload.get("version") or payload.get("Version")
                if value:
                    return str(value).strip()[:128]

        match = re.search(
            r"(?:version|versionNo|DisplayVersion)\s*[:=]\s*[\"']?([v\d][0-9A-Za-z.+_-]*)",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()[:128]
        raw_match = re.search(r"\b\d+(?:\.\d+){1,4}\b", text)
        if raw_match:
            return raw_match.group(0)
    return None


def collect_total_inventory(
    reg_data: list[dict],
    *,
    include_timings: bool = False,
):
    """Build inventory without recursive per-application filesystem discovery.

    Missing registry versions intentionally remain ``???``. Guessing them by
    recursively crawling arbitrary install directories was the dominant startup
    cost on large machines and is less authoritative than the registry value.
    Portable shortcuts point at a concrete executable, so reading that file's
    version resource remains a cheap and well-scoped fallback.
    """
    from src.logic.parser import get_file_version

    started = time.monotonic()
    shortcut_started = time.monotonic()
    portable_leads = collect_portable_apps()
    shortcut_seconds = time.monotonic() - shortcut_started

    assembly_started = time.monotonic()
    inventory = []
    seen_names = set()

    for entry in reg_data:
        name = str(entry.get("name") or "").strip()
        if not name or name.casefold() in seen_names:
            continue
        version = str(entry.get("version") or "???").strip() or "???"
        inventory.append(
            {
                "Name": name,
                "Id": entry.get("subkey") or "",
                "Version": version,
                "Available": "",
                "Type": "Installed",
                "Managed": "Windows",
                "URL": entry.get("url"),
                "Path": entry.get("path"),
            }
        )
        seen_names.add(name.casefold())

    portable_version_reads = 0
    portable_metadata_reads = 0
    for lead in portable_leads:
        name = str(lead.get("name") or "").strip()
        if not name or name.casefold() in seen_names:
            continue
        target = str(lead.get("path") or "")
        version = get_file_version(target)
        portable_version_reads += 1
        if not version:
            version = _extract_nearby_version(lead.get("folder"))
            portable_metadata_reads += 1
        inventory.append(
            {
                "Name": name,
                "Id": "Portable." + re.sub(r"\s+", "", name),
                "Version": version or "Unknown",
                "Available": "",
                "Type": "Portable",
                "Managed": "Local",
                "URL": None,
                "Path": target,
            }
        )
        seen_names.add(name.casefold())

    inventory.sort(key=lambda item: item["Name"].casefold())
    assembly_seconds = time.monotonic() - assembly_started
    timings = {
        "shortcut_scan_seconds": round(shortcut_seconds, 3),
        "assembly_seconds": round(assembly_seconds, 3),
        "total_seconds": round(time.monotonic() - started, 3),
        "portable_candidates": len(portable_leads),
        "portable_version_reads": portable_version_reads,
        "portable_metadata_reads": portable_metadata_reads,
    }
    if include_timings:
        return inventory, timings
    return inventory

"""Fast-path system inventory collection for the managed GUI worker."""

from __future__ import annotations

import os


def collect_portable_apps() -> list[dict]:
    """Scan Windows shortcuts while reusing one COM shell for the whole pass."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut_locations = [
            os.path.join(
                os.environ["APPDATA"],
                r"Microsoft\Windows\Start Menu\Programs",
            ),
            os.path.join(
                os.environ["ProgramData"],
                r"Microsoft\Windows\Start Menu\Programs",
            ),
            os.path.join(os.environ["USERPROFILE"], "Desktop"),
        ]
        potential_apps = []
        seen_targets = set()
        for location in shortcut_locations:
            if not os.path.exists(location):
                continue
            for root, _dirs, files in os.walk(location, followlinks=False):
                for filename in files:
                    if not filename.lower().endswith(".lnk"):
                        continue
                    shortcut_path = os.path.join(root, filename)
                    try:
                        target = shell.CreateShortCut(shortcut_path).Targetpath
                    except Exception:
                        continue
                    if not target or not target.lower().endswith(".exe"):
                        continue
                    target_key = os.path.normcase(target)
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


def collect_total_inventory(reg_data: list[dict]) -> list[dict]:
    """Build the same inventory surface with a cheaper portable-app scan."""
    from src.logic.parser import (
        find_best_exe,
        find_version_in_text_files,
        get_file_version,
    )

    portable_leads = collect_portable_apps()
    inventory = []
    seen_names = set()

    for entry in reg_data:
        name = entry["name"]
        if not name or name.lower() in seen_names:
            continue
        version = entry["version"]
        if (
            (version == "???" or version.lower() == "unknown")
            and entry["path"]
        ):
            version_text = find_version_in_text_files(entry["path"])
            if version_text:
                version = version_text
            else:
                executable = find_best_exe(entry["path"], name)
                if executable:
                    binary_version = get_file_version(executable)
                    if binary_version:
                        version = binary_version
        inventory.append(
            {
                "Name": name,
                "Id": entry["subkey"],
                "Version": version,
                "Available": "",
                "Type": "Installed",
                "Managed": "Windows",
                "URL": entry["url"],
                "Path": entry["path"],
            }
        )
        seen_names.add(name.lower())

    for lead in portable_leads:
        name = lead["name"]
        if name.lower() in seen_names:
            continue
        version = get_file_version(lead["path"])
        if not version:
            version = find_version_in_text_files(lead["folder"])
        inventory.append(
            {
                "Name": name,
                "Id": "Portable." + name.replace(" ", ""),
                "Version": version or "Unknown",
                "Available": "",
                "Type": "Portable",
                "Managed": "Local",
                "URL": None,
                "Path": lead["path"],
            }
        )
        seen_names.add(name.lower())

    inventory.sort(key=lambda item: item["Name"].lower())
    return inventory

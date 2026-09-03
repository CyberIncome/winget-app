"""Regression coverage for the bounded managed inventory scan."""

from __future__ import annotations

import sys
import types

from src.logic import inventory_scan


def test_portable_shortcut_scan_reuses_one_com_shell(monkeypatch):
    calls = {"dispatch": 0, "shortcut": 0, "init": 0, "uninit": 0}

    class Shortcut:
        def __init__(self, path):
            self.Targetpath = path.replace(".lnk", ".exe")

    class Shell:
        def CreateShortCut(self, path):
            calls["shortcut"] += 1
            return Shortcut(path)

    pythoncom = types.ModuleType("pythoncom")
    pythoncom.CoInitialize = lambda: calls.__setitem__("init", calls["init"] + 1)
    pythoncom.CoUninitialize = lambda: calls.__setitem__(
        "uninit", calls["uninit"] + 1
    )

    client = types.ModuleType("win32com.client")

    def dispatch(_name):
        calls["dispatch"] += 1
        return Shell()

    client.Dispatch = dispatch
    win32com = types.ModuleType("win32com")
    win32com.__path__ = []
    win32com.client = client

    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)
    monkeypatch.setitem(sys.modules, "win32com", win32com)
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    monkeypatch.setenv("APPDATA", "C:/User/AppData")
    monkeypatch.setenv("ProgramData", "C:/ProgramData")
    monkeypatch.setenv("USERPROFILE", "C:/User")
    monkeypatch.setattr(inventory_scan.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(
        inventory_scan.os,
        "walk",
        lambda location, followlinks=False: [
            (location, [], ["One.lnk", "Two.lnk"])
        ],
    )

    results = inventory_scan.collect_portable_apps()

    assert calls["dispatch"] == 1
    assert calls["shortcut"] == 6
    assert calls["init"] == 1
    assert calls["uninit"] == 1
    assert len(results) == 6


def test_registry_inventory_base_never_enters_shortcut_scan(monkeypatch):
    monkeypatch.setattr(
        inventory_scan,
        "collect_portable_apps",
        lambda: (_ for _ in ()).throw(
            AssertionError("fast registry base must not resolve shortcuts")
        ),
    )
    result = inventory_scan.collect_registry_inventory(
        [
            {
                "name": "Fast App",
                "subkey": "Fast.App",
                "version": "1.2.3",
                "path": "C:/Fast",
                "url": None,
            }
        ]
    )

    assert result == [
        {
            "Name": "Fast App",
            "Id": "Fast.App",
            "Version": "1.2.3",
            "Available": "",
            "Type": "Installed",
            "Managed": "Windows",
            "URL": None,
            "Path": "C:/Fast",
        }
    ]


def test_registry_unknown_version_is_not_recursively_guessed(monkeypatch):
    """Inventory must not crawl arbitrary install trees for missing versions."""
    import src.logic.parser as parser

    monkeypatch.setattr(inventory_scan, "collect_portable_apps", lambda: [])

    def forbidden_file_version(_path):
        raise AssertionError("registry unknown must not trigger binary probing")

    monkeypatch.setattr(parser, "get_file_version", forbidden_file_version)
    data = [
        {
            "name": "Large App",
            "subkey": "Large.App",
            "version": "???",
            "path": "C:/Huge/Install/Tree",
            "url": None,
        }
    ]

    result = inventory_scan.collect_total_inventory(data)

    assert result[0]["Version"] == "???"
    assert result[0]["Type"] == "Installed"


def test_portable_version_reads_only_the_concrete_shortcut_target(monkeypatch):
    import src.logic.parser as parser

    monkeypatch.setattr(
        inventory_scan,
        "collect_portable_apps",
        lambda: [
            {
                "name": "Portable Tool",
                "path": "C:/Tools/PortableTool.exe",
                "folder": "C:/Tools",
            }
        ],
    )
    calls = []
    monkeypatch.setattr(
        parser,
        "get_file_version",
        lambda path: calls.append(path) or "2.4.1",
    )
    monkeypatch.setattr(
        inventory_scan,
        "_extract_nearby_version",
        lambda _folder: (_ for _ in ()).throw(
            AssertionError("metadata fallback should not run when exe has a version")
        ),
    )

    result = inventory_scan.collect_total_inventory([])

    assert calls == ["C:/Tools/PortableTool.exe"]
    assert result[0]["Version"] == "2.4.1"
    assert result[0]["Managed"] == "Local"


def test_inventory_profile_exposes_stage_timings(monkeypatch):
    import src.logic.parser as parser

    monkeypatch.setattr(inventory_scan, "collect_portable_apps", lambda: [])
    monkeypatch.setattr(parser, "get_file_version", lambda _path: None)

    result, timings = inventory_scan.collect_total_inventory(
        [
            {
                "name": "App",
                "subkey": "App",
                "version": "1.0",
                "path": None,
                "url": None,
            }
        ],
        include_timings=True,
    )

    assert result[0]["Version"] == "1.0"
    assert timings["base_assembly_seconds"] >= 0
    assert timings["shortcut_scan_seconds"] >= 0
    assert timings["assembly_seconds"] >= 0
    assert timings["total_seconds"] >= 0
    assert timings["portable_candidates"] == 0

"""Regression coverage for the optimized managed inventory shortcut scan."""

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

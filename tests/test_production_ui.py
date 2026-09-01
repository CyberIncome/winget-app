from collections import deque

from PySide6.QtCore import QProcess, Qt

import src.ui.production_window as production_module
from src.ui.main_window import UpdateModel
from src.ui.production_window import (
    ProductionMainWindow,
    ProductionUpdateModel,
)


def _winget_row(
    name="Google Chrome",
    package_id="Google.Chrome",
    source="winget",
    available="121.0",
):
    return {
        "Name": name,
        "Id": package_id,
        "Version": "120.0",
        "Available": available,
        "Source": source,
    }


def test_winget_scan_rows_are_tagged_and_source_is_visible(qtbot):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.apply_winget_results([_winget_row()])

    model = window.proxy_model.sourceModel()
    assert model._data[0]["UpdateSource"] == "winget"
    assert model.headerData(5, Qt.Horizontal) == "Source"
    assert model.data(model.index(0, 5), Qt.DisplayRole) == "winget"


def test_update_all_excludes_detective_only_rows(qtbot, monkeypatch):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.apply_winget_results([_winget_row()])

    model = window.proxy_model.sourceModel()
    detective = {
        "Name": "Portable Tool",
        "Id": "Portable.Tool",
        "Version": "1.0",
        "Available": "2.0",
        "Source": "detective",
        "UpdateSource": "detective",
    }
    model._data.append(detective)
    model._selected[detective["Id"]] = False

    captured = []
    monkeypatch.setattr(
        window, "batch_update", lambda refs: captured.extend(refs)
    )
    window.update_all()

    assert captured == [
        {
            "value": "Google.Chrome",
            "match_by": "id",
            "source": "winget",
        }
    ]


def test_duplicate_ids_from_different_sources_remain_distinct(qtbot, monkeypatch):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.apply_winget_results(
        [
            _winget_row("Shared App", "Shared.App", "winget"),
            _winget_row("Shared App", "Shared.App", "private-feed"),
        ]
    )

    captured = []
    monkeypatch.setattr(
        window, "batch_update", lambda refs: captured.extend(refs)
    )
    window.update_all()

    assert captured == [
        {"value": "Shared.App", "match_by": "id", "source": "winget"},
        {
            "value": "Shared.App",
            "match_by": "id",
            "source": "private-feed",
        },
    ]


def test_inventory_registry_id_is_never_used_when_mapping_update(qtbot):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.apply_winget_results([_winget_row()])

    inventory_item = {
        "Name": "Google Chrome",
        # Syntactically valid as a Winget ID, but this is deliberately a
        # registry uninstall key and must not be trusted as package provenance.
        "Id": "Chrome.Registry.Entry",
        "Version": "120.0",
        "Available": "121.0",
    }
    assert window._winget_refs_for_inventory_items([inventory_item]) == [
        {
            "value": "Google.Chrome",
            "match_by": "id",
            "source": "winget",
        }
    ]


def test_ambiguous_inventory_name_is_not_executed(qtbot):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.apply_winget_results(
        [
            _winget_row("Shared Name", "Vendor.One"),
            _winget_row("Shared Name", "Vendor.Two"),
        ]
    )

    inventory_item = {
        "Name": "Shared Name",
        "Id": "Registry.Shared",
        "Version": "1.0",
        "Available": "2.0",
    }
    assert window._winget_refs_for_inventory_items([inventory_item]) == []


def test_detective_only_hit_is_tagged_informational(qtbot):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.apply_winget_results([])
    window.inventory_proxy.setSourceModel(
        UpdateModel(
            [
                {
                    "Name": "Portable Tool",
                    "Id": "Portable.Tool",
                    "Version": "1.0",
                    "Available": "",
                    "Type": "Portable",
                    "Managed": "Local",
                }
            ],
            is_inventory=True,
        )
    )

    window._detective_job_succeeded([(0, "2.0")])

    model = window.proxy_model.sourceModel()
    assert isinstance(model, ProductionUpdateModel)
    assert len(model._data) == 1
    assert model._data[0]["UpdateSource"] == "detective"
    assert model._data[0]["Source"] == "detective"
    assert model._data[0]["Available"] == "2.0"


def test_detective_does_not_override_official_winget_available(qtbot):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.apply_winget_results([_winget_row(available="121.0")])
    window.inventory_proxy.setSourceModel(
        UpdateModel(
            [
                {
                    "Name": "Google Chrome",
                    "Id": "Registry.Chrome",
                    "Version": "120.0",
                    "Available": "",
                    "Type": "Installed",
                    "Managed": "Windows",
                }
            ],
            is_inventory=True,
        )
    )

    window._detective_job_succeeded([(0, "999.0")])

    model = window.proxy_model.sourceModel()
    assert model._data[0]["Available"] == "121.0"
    assert model._data[0]["UpdateSource"] == "winget"


def test_rows_without_explicit_winget_provenance_are_not_executed(qtbot):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    model = ProductionUpdateModel([_winget_row()])
    window.proxy_model.setSourceModel(model)

    assert window._is_winget_update_item(model._data[0]) is False


def test_remove_package_matches_source_when_ids_collide(qtbot):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.apply_winget_results(
        [
            _winget_row("Shared App", "Shared.App", "winget"),
            _winget_row("Shared App", "Shared.App", "private-feed"),
        ]
    )

    window.remove_package_from_model(
        {
            "value": "Shared.App",
            "match_by": "id",
            "source": "private-feed",
        }
    )

    model = window.proxy_model.sourceModel()
    assert [item["Source"] for item in model._data] == ["winget"]


def test_failed_to_start_aborts_remaining_update_batch(qtbot):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.current_operation = "update"
    window.set_ui_busy("Updating apps...", True, "update")
    window.process_queue = deque(
        [
            {"value": "One.App", "match_by": "id", "silent": True},
            {"value": "Two.App", "match_by": "id", "silent": True},
        ]
    )

    window.handle_process_error(QProcess.FailedToStart)

    assert list(window.process_queue) == []
    assert window.current_operation is None
    assert "update" not in window._active_tasks


def test_crash_exit_is_not_retried_without_silent(qtbot):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.current_operation = "update"
    window.set_ui_busy("Updating apps...", True, "update")
    window.current_package_ref = {
        "value": "Perplexity.Comet",
        "match_by": "id",
        "source": "winget",
        "silent": True,
    }
    window.process_queue = deque()

    window.process_finished(-1, QProcess.CrashExit)

    assert list(window.process_queue) == []
    assert window.current_operation is None
    assert "update" not in window._active_tasks


def test_pending_pat_is_flushed_on_immediate_close(qtbot, monkeypatch):
    window = ProductionMainWindow()
    qtbot.addWidget(window)

    class FakeConfig:
        github_pat = ""

    fake_config = FakeConfig()
    monkeypatch.setattr(
        production_module, "ConfigManager", lambda: fake_config
    )
    window._pending_pat = "ghp_pending"
    window._pat_save_timer.start()

    window.close()

    assert fake_config.github_pat == "ghp_pending"

from PySide6.QtCore import Qt

from src.ui.main_window import UpdateModel
from src.ui.production_window import ProductionMainWindow


def _winget_row(name="Google Chrome", package_id="Google.Chrome"):
    return {
        "Name": name,
        "Id": package_id,
        "Version": "120.0",
        "Available": "121.0",
        "Source": "winget",
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

    assert captured == [{"value": "Google.Chrome", "match_by": "id"}]


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
        {"value": "Google.Chrome", "match_by": "id"}
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
    assert len(model._data) == 1
    assert model._data[0]["UpdateSource"] == "detective"
    assert model._data[0]["Available"] == "2.0"

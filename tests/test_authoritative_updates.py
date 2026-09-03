"""Regression coverage for stable authoritative update counts."""

from src.ui.authoritative_updates_window import AuthoritativeUpdatesMainWindow
from src.ui.main_window import UpdateModel


def _window(qtbot):
    window = AuthoritativeUpdatesMainWindow()
    qtbot.addWidget(window)
    return window


def _winget_row(name="Winget App", package_id="Vendor.Winget", available="2.0"):
    return {
        "Name": name,
        "Id": package_id,
        "Version": "1.0",
        "Available": available,
        "Source": "winget",
    }


def _detective_row(name="Portable Tool", package_id="Portable.Tool"):
    return {
        "Name": name,
        "Id": package_id,
        "Version": "1.0",
        "Available": "2.0",
        "Source": "detective",
        "UpdateSource": "detective",
    }


def _append_detective(model, item):
    model._data.append(dict(item))
    added = model._data[-1]
    model._selected[model.selection_key_for_item(added)] = False


def test_same_winget_refresh_preserves_detective_rows_without_changing_count(qtbot):
    window = _window(qtbot)
    winget = _winget_row()
    detective = _detective_row()

    window.apply_winget_results([winget])
    model = window.proxy_model.sourceModel()
    _append_detective(model, detective)
    # Simulate the old mixed-model statistic that caused the visible jump.
    window._stat_updates = len(model._data)

    window.apply_winget_results([winget])

    model = window.proxy_model.sourceModel()
    assert len(model._data) == 2
    assert [item["UpdateSource"] for item in model._data] == [
        "winget",
        "detective",
    ]
    assert window._stat_updates == 1
    assert window.stat_updates.value.text() == "1"


def test_fresh_winget_row_supersedes_matching_detective_row(qtbot):
    window = _window(qtbot)
    detective = _detective_row("Shared App", "Shared.App")

    window.apply_winget_results([])
    model = window.proxy_model.sourceModel()
    _append_detective(model, detective)

    window.apply_winget_results(
        [_winget_row("Shared App", "Shared.App", available="3.0")]
    )

    model = window.proxy_model.sourceModel()
    assert len(model._data) == 1
    assert model._data[0]["UpdateSource"] == "winget"
    assert model._data[0]["Available"] == "3.0"
    assert window._stat_updates == 1


def test_detective_enrichment_does_not_inflate_authoritative_count(qtbot):
    window = _window(qtbot)
    window.apply_winget_results([_winget_row()])
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
    assert len(model._data) == 2
    assert sum(
        1 for item in model._data if item.get("UpdateSource") == "winget"
    ) == 1
    assert window._stat_updates == 1


def test_successful_winget_row_removal_recounts_without_detective_rows(qtbot):
    window = _window(qtbot)
    window.apply_winget_results([_winget_row()])
    model = window.proxy_model.sourceModel()
    _append_detective(model, _detective_row())
    window._sync_authoritative_update_count()

    window.remove_package_from_model(
        {
            "value": "Vendor.Winget",
            "match_by": "id",
            "source": "winget",
        }
    )

    model = window.proxy_model.sourceModel()
    assert len(model._data) == 1
    assert model._data[0]["UpdateSource"] == "detective"
    assert window._stat_updates == 0
    assert window.stat_updates.value.text() == "0"

from src.ui.production_window import ProductionMainWindow


def _row(name, package_id, source="winget"):
    return {
        "Name": name,
        "Id": package_id,
        "Version": "1.0",
        "Available": "2.0",
        "Source": source,
    }


def test_inventory_mapping_ignores_registry_id_collision(qtbot):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.apply_winget_results(
        [
            _row("Wrong App", "Spoofed.Id"),
            _row("Inventory App", "Correct.Id"),
        ]
    )

    inventory_item = {
        "Name": "Inventory App",
        # This local uninstall-key string deliberately collides with a
        # different Winget package and must never select it.
        "Id": "Spoofed.Id",
        "Version": "1.0",
        "Available": "2.0",
    }

    assert window._winget_refs_for_inventory_items([inventory_item]) == [
        {
            "value": "Correct.Id",
            "match_by": "id",
            "source": "winget",
        }
    ]


def test_inventory_mapping_fails_closed_on_duplicate_names(qtbot):
    window = ProductionMainWindow()
    qtbot.addWidget(window)
    window.apply_winget_results(
        [
            _row("Shared Name", "Vendor.One", "winget"),
            _row("Shared Name", "Vendor.Two", "private-feed"),
        ]
    )

    inventory_item = {
        "Name": "Shared Name",
        "Id": "Vendor.One",
        "Version": "1.0",
        "Available": "2.0",
    }

    assert window._winget_refs_for_inventory_items([inventory_item]) == []

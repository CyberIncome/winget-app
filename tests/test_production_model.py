from PySide6.QtCore import Qt

from src.ui.production_window import ProductionUpdateModel


def _model():
    return ProductionUpdateModel(
        [
            {
                "Name": "Shared App",
                "Id": "Shared.App",
                "Version": "1.0",
                "Available": "2.0",
                "Source": "winget",
                "UpdateSource": "winget",
            },
            {
                "Name": "Shared App",
                "Id": "Shared.App",
                "Version": "1.0",
                "Available": "2.0",
                "Source": "private-feed",
                "UpdateSource": "winget",
            },
        ]
    )


def test_same_package_id_from_two_sources_has_independent_checkbox_state():
    model = _model()

    model.setData(model.index(0, 0), Qt.Checked, Qt.CheckStateRole)

    assert model.data(model.index(0, 0), Qt.CheckStateRole) == Qt.Checked
    assert model.data(model.index(1, 0), Qt.CheckStateRole) == Qt.Unchecked


def test_stale_row_index_returns_none_instead_of_raising():
    model = _model()
    stale = model.createIndex(99, 5)

    assert stale.isValid()
    assert model.data(stale, Qt.DisplayRole) is None


def test_stale_column_index_returns_none_instead_of_raising():
    model = _model()
    stale = model.createIndex(0, 99)

    assert stale.isValid()
    assert model.data(stale, Qt.DisplayRole) is None

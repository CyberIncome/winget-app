import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "src" / "ui" / "legacy_window.py"
HARDENED = ROOT / "src" / "ui" / "hardened_window.py"
PRODUCTION = ROOT / "src" / "ui" / "production_window.py"


def _class_methods(path, class_name):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {item.name: item for item in node.body if isinstance(item, ast.FunctionDef)}
    raise AssertionError(f"{class_name} not found in {path}")


def _contains_thread_launch(method):
    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if (
            isinstance(function, ast.Attribute)
            and function.attr == "Thread"
            and isinstance(function.value, ast.Name)
            and function.value.id == "threading"
        ):
            return True
    return False


def test_every_legacy_thread_launch_method_is_overridden_in_production_chain():
    legacy_methods = _class_methods(LEGACY, "MainWindow")
    legacy_thread_methods = {
        name
        for name, method in legacy_methods.items()
        if _contains_thread_launch(method)
    }
    assert legacy_thread_methods

    hardened_methods = set(_class_methods(HARDENED, "HardenedMainWindow"))
    production_methods = set(_class_methods(PRODUCTION, "ProductionMainWindow"))
    overridden = hardened_methods | production_methods

    assert legacy_thread_methods <= overridden

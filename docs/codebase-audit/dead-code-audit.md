# Dead Code Audit Report

Updated: 2026-05-06 06:58:23

## Summary

- **Total Potentially Unused**: 7
- **CSS Selectors Scanned**: 0
- **JS Functions Scanned**: 10
- **PHP Functions Scanned**: 0

## Breakdown

- 🎨 Unused CSS: 0
- ⚡ Unused JS: 7
- 🐘 Unused PHP: 0
- 💬 Commented Blocks: 0

## ⚡ Potentially Unused JS Functions

| Function | Defined In | Line |
| --- | --- | ---: |
| `renderSmoothedLine()` | `venv\Lib\site-packages\PySide6\qml\QtQuick\VirtualKeyboard\Styles\TraceUtils.js` | 6 |
| `log_register_test()` | `venv\Lib\site-packages\PySide6\qml\QtTest\testlogger.js` | 20 |
| `log_optional_test()` | `venv\Lib\site-packages\PySide6\qml\QtTest\testlogger.js` | 28 |
| `log_mandatory_test()` | `venv\Lib\site-packages\PySide6\qml\QtTest\testlogger.js` | 36 |
| `log_can_start_test()` | `venv\Lib\site-packages\PySide6\qml\QtTest\testlogger.js` | 44 |
| `log_start_test()` | `venv\Lib\site-packages\PySide6\qml\QtTest\testlogger.js` | 49 |
| `log_complete_test()` | `venv\Lib\site-packages\PySide6\qml\QtTest\testlogger.js` | 58 |

## Recommendations

1. **Review before deleting** — Some items may be used dynamically
2. **Check generated classes** — JS may add classes at runtime
3. **Remove commented code** — Use version control instead
4. **Run again after cleanup** — May reveal more dead code

## Notes

- This analysis is static and may have false positives
- Dynamic class names (e.g., `class="btn-" + type`) won't be detected
- Functions called via `call_user_func()` may be flagged incorrectly

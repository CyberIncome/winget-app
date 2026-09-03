"""Visible, truthful progress for foreground Winget update operations.

Winget exposes useful stage and download information, but installers do not
always report a percentage (especially in silent mode). This layer therefore
shows real percentages/byte progress when present and explicitly labels opaque
installer work instead of inventing an overall percentage.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget


_PERCENT_RE = re.compile(r"(?<!\d)(100|[1-9]?\d)%")
_BYTES_RE = re.compile(
    r"(?P<done>\d+(?:\.\d+)?)\s*(?P<done_unit>B|KB|MB|GB|TB)\s*/\s*"
    r"(?P<total>\d+(?:\.\d+)?)\s*(?P<total_unit>B|KB|MB|GB|TB)",
    re.IGNORECASE,
)
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

_UNIT_SCALE = {
    "B": 1,
    "KB": 1024,
    "MB": 1024**2,
    "GB": 1024**3,
    "TB": 1024**4,
}


@dataclass(frozen=True)
class UpdateProgressObservation:
    stage: str
    detail: str
    percent: Optional[int] = None


def _clean_output(raw: str) -> str:
    text = _ANSI_RE.sub("", raw or "")
    return text.replace("\r", "\n")


def _byte_percent(text: str) -> tuple[Optional[int], Optional[str]]:
    matches = list(_BYTES_RE.finditer(text))
    if not matches:
        return None, None
    match = matches[-1]
    done = float(match.group("done")) * _UNIT_SCALE[match.group("done_unit").upper()]
    total = float(match.group("total")) * _UNIT_SCALE[match.group("total_unit").upper()]
    if total <= 0:
        return None, None
    percent = max(0, min(100, round(done * 100 / total)))
    detail = (
        f"{match.group('done')} {match.group('done_unit').upper()} / "
        f"{match.group('total')} {match.group('total_unit').upper()}"
    )
    return percent, detail


def observe_winget_update_output(raw: str) -> Optional[UpdateProgressObservation]:
    """Extract the latest truthful update stage/progress from one output chunk."""
    text = _clean_output(raw)
    lowered = text.lower()

    percent, byte_detail = _byte_percent(text)
    if percent is not None:
        return UpdateProgressObservation(
            "Downloading", byte_detail or "Downloading", percent
        )

    percent_matches = list(_PERCENT_RE.finditer(text))
    if percent_matches:
        value = int(percent_matches[-1].group(1))
        stage = "Installing" if "install" in lowered else "Downloading"
        return UpdateProgressObservation(stage, f"{stage} {value}%", value)

    # Check the most meaningful lifecycle phrases from most-specific to broad.
    if "successfully installed" in lowered or "successfully upgraded" in lowered:
        return UpdateProgressObservation(
            "Finishing", "Package installation completed", 100
        )
    if "no applicable upgrade found" in lowered:
        return UpdateProgressObservation(
            "Finishing", "No applicable upgrade was found"
        )
    if "starting package install" in lowered or "starting package upgrade" in lowered:
        return UpdateProgressObservation(
            "Installing",
            "Installer is running; no percentage has been reported",
        )
    if "successfully verified installer hash" in lowered:
        return UpdateProgressObservation(
            "Verifying", "Downloaded installer verified"
        )
    if "installer hash" in lowered and (
        "verified" in lowered or "verification" in lowered
    ):
        return UpdateProgressObservation(
            "Verifying", "Verifying downloaded installer"
        )
    if "downloading" in lowered or "download" in lowered:
        return UpdateProgressObservation(
            "Downloading", "Downloading installer/package"
        )
    if "failed" in lowered or "error" in lowered:
        return UpdateProgressObservation(
            "Problem", "Winget reported an update problem"
        )
    if "found " in lowered or "version" in lowered:
        return UpdateProgressObservation(
            "Resolving", "Resolving package and target version"
        )
    return None


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _display_name_for_ref(window, ref: dict) -> str:
    value = str(ref.get("value") or "").strip()
    model = window.proxy_model.sourceModel()
    if model is not None:
        match_by = ref.get("match_by")
        for item in getattr(model, "_data", []):
            candidate = (
                item.get("Id") if match_by == "id" else item.get("Name")
            )
            if str(candidate or "").strip().casefold() == value.casefold():
                return str(item.get("Name") or value or "Package")
    return value or "Package"


def _install_progress_ui(window) -> None:
    banner = QWidget(window.update_tab)
    banner.setObjectName("updateProgressBanner")
    banner.setStyleSheet(
        "QWidget#updateProgressBanner {"
        " background-color: rgba(18, 20, 31, 0.90);"
        " border: 1px solid rgba(122, 162, 247, 0.48);"
        " border-radius: 8px;"
        "}"
        "QLabel#updateProgressTitle { color: #f4f7ff; font-weight: 700; }"
        "QLabel#updateProgressMeta { color: #9dbdff; font-weight: 650; }"
        "QLabel#updateProgressDetail { color: #a9b3cb; }"
        "QProgressBar#updateOperationProgress {"
        " background-color: #24283b; color: #f4f7ff;"
        " border: 1px solid #414868; border-radius: 5px;"
        " text-align: center; min-height: 16px; max-height: 16px;"
        " font-size: 8pt; font-weight: 700;"
        "}"
        "QProgressBar#updateOperationProgress::chunk {"
        " background-color: #7aa2f7; border-radius: 4px;"
        "}"
    )
    outer = QVBoxLayout(banner)
    outer.setContentsMargins(12, 8, 12, 8)
    outer.setSpacing(5)

    top = QHBoxLayout()
    top.setContentsMargins(0, 0, 0, 0)
    title = QLabel("Update progress")
    title.setObjectName("updateProgressTitle")
    meta = QLabel("")
    meta.setObjectName("updateProgressMeta")
    top.addWidget(title)
    top.addStretch()
    top.addWidget(meta)
    outer.addLayout(top)

    detail = QLabel("")
    detail.setObjectName("updateProgressDetail")
    outer.addWidget(detail)

    progress = QProgressBar()
    progress.setObjectName("updateOperationProgress")
    progress.setTextVisible(True)
    progress.setMinimumHeight(18)
    progress.setMaximumHeight(18)
    progress.setRange(0, 0)
    outer.addWidget(progress)

    layout = window.update_tab.layout()
    if layout is not None:
        # Layout/context polish install the updates toolbar at index 0.
        layout.insertWidget(1, banner)
    banner.setVisible(False)

    window.update_progress_banner = banner
    window.update_progress_title = title
    window.update_progress_meta = meta
    window.update_progress_detail = detail
    window.update_operation_progress = progress


def _set_bar(window, percent: Optional[int]) -> None:
    bar = window.update_operation_progress
    if percent is None:
        bar.setRange(0, 0)
        bar.setFormat("")
        return
    bar.setRange(0, 100)
    bar.setValue(max(0, min(100, int(percent))))
    bar.setFormat("%p%")


def _refresh_elapsed(window) -> None:
    started = getattr(window, "_visible_update_started_at", None)
    if started is None or window.current_operation != "update":
        return
    elapsed = _format_elapsed(time.monotonic() - started)
    base = getattr(window, "_visible_update_detail_base", "Working")
    window.update_progress_detail.setText(
        f"{base}  •  elapsed {elapsed}"
    )


def _start_package_ui(window) -> None:
    ref = getattr(window, "current_package_ref", None)
    if not isinstance(ref, dict):
        return
    total = max(1, int(getattr(window, "_queue_total", 1) or 1))
    remaining = len(getattr(window, "process_queue", ()))
    index = max(1, min(total, total - remaining))
    name = _display_name_for_ref(window, ref)

    window._visible_update_started_at = time.monotonic()
    window._visible_update_detail_base = "Starting Winget update"
    window.update_progress_title.setText(f"Updating {name}")
    window.update_progress_meta.setText(f"Package {index} of {total}")
    window.update_progress_banner.setVisible(True)
    _set_bar(window, None)
    _refresh_elapsed(window)
    window._update_progress_timer.start()


def _observe_output(window, raw: str) -> None:
    if window.current_operation != "update":
        return
    observation = observe_winget_update_output(raw)
    if observation is None:
        return
    window._visible_update_detail_base = observation.detail
    _set_bar(window, observation.percent)
    _refresh_elapsed(window)


def _finish_update_ui(window, code: int) -> None:
    if not hasattr(window, "update_progress_banner"):
        return
    ref = getattr(window, "current_package_ref", {})
    name = (
        _display_name_for_ref(window, ref)
        if isinstance(ref, dict)
        else "Package"
    )
    if code == 0:
        window._visible_update_detail_base = "Completed successfully"
        _set_bar(window, 100)
    else:
        window._visible_update_detail_base = f"Winget exited with code {code}"
        _set_bar(window, None)
    _refresh_elapsed(window)
    window.update_progress_title.setText(f"{name} update")


def _hide_banner_if_idle(window) -> None:
    if getattr(window, "current_operation", None) != "update":
        window.update_progress_banner.setVisible(False)


def apply_update_progress(window) -> None:
    """Install live update progress without changing update authority/safety."""
    if getattr(window, "_update_progress_polished", False):
        return
    window._update_progress_polished = True
    _install_progress_ui(window)

    timer = QTimer(window)
    timer.setInterval(500)
    timer.timeout.connect(lambda: _refresh_elapsed(window))
    window._update_progress_timer = timer
    window._visible_update_started_at = None
    window._visible_update_detail_base = "Starting Winget update"

    # Preserve the final hardened methods exactly and decorate only their UI
    # side-effects. No command construction, target selection, retry, watchdog,
    # or completion authority is reimplemented here.
    original_run_next = window.run_next_update
    original_output = window._handle_process_output
    original_finished = window.process_finished

    def run_next_with_progress():
        original_run_next()
        if (
            window.current_operation == "update"
            and getattr(window, "current_package_ref", None)
        ):
            _start_package_ui(window)

    def output_with_progress(stream_name, raw):
        original_output(stream_name, raw)
        _observe_output(window, raw)

    def finished_with_progress(code, status):
        was_update = window.current_operation == "update"
        if was_update:
            _finish_update_ui(window, int(code))
        original_finished(code, status)
        if was_update and window.current_operation != "update":
            timer.stop()
            QTimer.singleShot(3500, lambda: _hide_banner_if_idle(window))

    window.run_next_update = run_next_with_progress
    window._handle_process_output = output_with_progress
    window.process_finished = finished_with_progress

    # QProcess.finished was connected to the bound method during construction;
    # reconnect it so the wrapper above is the active completion handler.
    try:
        window.process.finished.disconnect()
    except (RuntimeError, TypeError):
        pass
    window.process.finished.connect(window.process_finished)

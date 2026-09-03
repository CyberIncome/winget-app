"""Read-only Steam game update detection with launcher handoff.

Steam owns installation and patching for normal client libraries. This provider
therefore discovers local app manifests and uses Valve's public
``ISteamApps/UpToDateCheck`` endpoint for update detection, but intentionally
hands execution back to the Steam client rather than invoking SteamCMD against
client-managed libraries.
"""

from __future__ import annotations

from pathlib import Path
import os
import re
from typing import Callable

from src.logic.http_safety import safe_get
from src.providers.base import (
    ActionKind,
    ProviderAction,
    ProviderCapability,
    ProviderCategory,
    ProviderMode,
    ProviderScanResult,
    ProviderStatus,
    ProviderUpdate,
)


STEAM_UPDATE_CHECK_URL = (
    "https://api.steampowered.com/ISteamApps/UpToDateCheck/v1/"
)
_STEAM_DOWNLOADS_URI = "steam://open/downloads"
_QUOTED_PAIR_RE = re.compile(r'^\s*"([^\"]+)"\s+"([^\"]*)"\s*$', re.MULTILINE)
_MANIFEST_RE = re.compile(r"^appmanifest_(\d+)\.acf$", re.IGNORECASE)


def _decode_vdf_value(value: str) -> str:
    """Decode the limited escaping used in Steam VDF path/string values."""
    return value.replace(r"\\", "\\").replace(r'\"', '"')


def _quoted_pairs(text: str) -> list[tuple[str, str]]:
    return [
        (key, _decode_vdf_value(value))
        for key, value in _QUOTED_PAIR_RE.findall(text)
    ]


def parse_app_manifest(text: str) -> dict[str, str] | None:
    """Parse the scalar fields needed from a Steam appmanifest ACF file."""
    values = {key.casefold(): value for key, value in _quoted_pairs(text)}
    app_id = str(values.get("appid") or "").strip()
    build_id = str(values.get("buildid") or "").strip()
    name = str(values.get("name") or "").strip()
    if not app_id.isdigit() or not build_id.isdigit() or not name:
        return None
    return {
        "appid": app_id,
        "buildid": build_id,
        "name": name,
        "installdir": str(values.get("installdir") or "").strip(),
    }


def parse_library_folders(text: str) -> tuple[Path, ...]:
    """Return library roots declared by Steam's libraryfolders.vdf."""
    roots = []
    seen = set()
    for key, value in _quoted_pairs(text):
        if key.casefold() != "path":
            continue
        path = Path(value).expanduser()
        normalized = os.path.normcase(os.path.abspath(str(path)))
        if normalized in seen:
            continue
        roots.append(path)
        seen.add(normalized)
    return tuple(roots)


def _default_steam_roots() -> tuple[Path, ...]:
    """Discover likely Steam roots without requiring Steam to be running."""
    candidates: list[Path] = []
    if os.name == "nt":
        try:
            import winreg

            probes = (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                (
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\WOW6432Node\Valve\Steam",
                    "InstallPath",
                ),
            )
            for hive, key_path, value_name in probes:
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        value, _kind = winreg.QueryValueEx(key, value_name)
                    if value:
                        candidates.append(Path(str(value)))
                except OSError:
                    continue
        except (ImportError, OSError):
            pass

        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        if program_files_x86:
            candidates.append(Path(program_files_x86) / "Steam")
    else:
        candidates.extend(
            [
                Path.home() / ".steam" / "steam",
                Path.home() / ".local" / "share" / "Steam",
            ]
        )

    roots = []
    seen = set()
    for candidate in candidates:
        try:
            normalized = os.path.normcase(os.path.abspath(str(candidate)))
        except OSError:
            continue
        if normalized in seen or not (candidate / "steamapps").is_dir():
            continue
        seen.add(normalized)
        roots.append(candidate)
    return tuple(roots)


class SteamProvider:
    """Detect Steam client-game updates and hand execution back to Steam."""

    provider_id = "steam"

    def __init__(
        self,
        roots: tuple[Path, ...] | None = None,
        *,
        getter: Callable = safe_get,
    ):
        self._configured_roots = roots
        self._getter = getter

    def _steam_roots(self) -> tuple[Path, ...]:
        if self._configured_roots is not None:
            return tuple(Path(root) for root in self._configured_roots)
        return _default_steam_roots()

    def _library_roots(self) -> tuple[Path, ...]:
        roots = []
        seen = set()
        for steam_root in self._steam_roots():
            candidates = [steam_root]
            library_file = steam_root / "steamapps" / "libraryfolders.vdf"
            try:
                text = library_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            if text:
                candidates.extend(parse_library_folders(text))

            for candidate in candidates:
                steamapps = candidate / "steamapps"
                if not steamapps.is_dir():
                    continue
                normalized = os.path.normcase(os.path.abspath(str(candidate)))
                if normalized in seen:
                    continue
                seen.add(normalized)
                roots.append(candidate)
        return tuple(roots)

    def probe(self) -> ProviderStatus:
        roots = self._steam_roots()
        executable = None
        for root in roots:
            candidate = root / ("steam.exe" if os.name == "nt" else "steam")
            if candidate.exists():
                executable = str(candidate)
                break
        return ProviderStatus(
            provider_id=self.provider_id,
            display_name="Steam",
            mode=ProviderMode.HANDOFF,
            category=ProviderCategory.GAME,
            available=bool(roots),
            capabilities=(
                ProviderCapability.DETECT,
                ProviderCapability.HANDOFF,
            ),
            reason=None if roots else "Steam installation was not discovered",
            executable=executable,
        )

    def _installed_apps(self) -> tuple[dict[str, str], ...]:
        apps: dict[str, dict[str, str]] = {}
        for library_root in self._library_roots():
            steamapps = library_root / "steamapps"
            try:
                manifests = sorted(steamapps.glob("appmanifest_*.acf"))
            except OSError:
                continue
            for manifest_path in manifests:
                match = _MANIFEST_RE.match(manifest_path.name)
                if not match:
                    continue
                try:
                    text = manifest_path.read_text(
                        encoding="utf-8", errors="replace"
                    )
                except OSError:
                    continue
                item = parse_app_manifest(text)
                if item is None or item["appid"] != match.group(1):
                    continue
                item = dict(item)
                item["library_root"] = str(library_root)
                item["manifest_path"] = str(manifest_path)
                apps.setdefault(item["appid"], item)
        return tuple(apps.values())

    def _check_app(self, app: dict[str, str]) -> tuple[ProviderUpdate | None, str | None]:
        try:
            response = self._getter(
                STEAM_UPDATE_CHECK_URL,
                params={
                    "appid": int(app["appid"]),
                    "version": int(app["buildid"]),
                },
                timeout=5,
                max_bytes=256 * 1024,
            )
        except Exception as exc:
            return None, f"{app['name']}: update check failed: {exc}"

        if response.status_code != 200:
            return None, (
                f"{app['name']}: Steam update check returned HTTP "
                f"{response.status_code}"
            )
        try:
            payload = response.json()
        except Exception as exc:
            return None, f"{app['name']}: invalid Steam response: {exc}"
        result = payload.get("response", payload)
        if not isinstance(result, dict):
            return None, f"{app['name']}: malformed Steam update response"
        if result.get("success") is not True:
            message = str(
                result.get("message") or "Steam did not confirm a successful update check"
            )
            return None, f"{app['name']}: {message}"
        up_to_date = result.get("up_to_date")
        if not isinstance(up_to_date, bool):
            return None, (
                f"{app['name']}: Steam response did not include a valid "
                "up_to_date state"
            )
        if up_to_date:
            return None, None

        required = str(result.get("required_version") or "").strip()
        available = required if required.isdigit() and required != "0" else "newer-build"
        return (
            ProviderUpdate(
                provider_id=self.provider_id,
                item_id=app["appid"],
                name=app["name"],
                installed_version=app["buildid"],
                available_version=available,
                category=ProviderCategory.GAME,
                mode=ProviderMode.HANDOFF,
                can_update=False,
                source="steam",
                blocked_reason="Steam client owns game patch execution",
                metadata={
                    "app_id": app["appid"],
                    "install_dir": app.get("installdir", ""),
                    "library_root": app.get("library_root", ""),
                    "manifest_path": app.get("manifest_path", ""),
                    "version_is_listable": result.get("version_is_listable"),
                },
            ),
            None,
        )

    def scan_updates(self) -> ProviderScanResult:
        status = self.probe()
        if not status.available:
            return ProviderScanResult(status=status)

        updates = []
        warnings = []
        for app in self._installed_apps():
            update, warning = self._check_app(app)
            if update is not None:
                updates.append(update)
            if warning:
                warnings.append(warning)
        return ProviderScanResult(
            status=status,
            updates=tuple(updates),
            warnings=tuple(warnings),
        )

    def plan_update(self, update: ProviderUpdate) -> ProviderAction:
        if update.provider_id != self.provider_id:
            raise ValueError("Steam provider cannot execute another provider's update")
        return ProviderAction(
            provider_id=self.provider_id,
            item_id=update.item_id,
            kind=ActionKind.HANDOFF,
            uri=_STEAM_DOWNLOADS_URI,
            description="Open Steam Downloads; Steam remains patch authority",
        )

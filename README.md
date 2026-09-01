# Winget Universal Dashboard

A Windows desktop/CLI interface for inspecting installed applications and managing authoritative Winget updates with hardened process lifecycle, package-source provenance, bounded output handling, and local release verification.

## Windows x64 install

GitHub Releases are the distribution surface. For normal users, download `WingetUniversalDashboard-Setup-x64.exe` from the latest repository Release and run it.

The installer is per-user and installs under `%LOCALAPPDATA%\Programs\WingetUniversalDashboard`, so normal installation does not require administrator elevation.

Portable release assets are also provided:

- `WingetUniversalDashboard.exe` — GUI
- `WingetUniversalDashboardCLI.exe` — CLI
- `SHA256SUMS.txt` — release hashes

## Run from source

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m src.main
```

CLI:

```powershell
python -m src.cli --help
```

## Development verification

```powershell
pip install -r requirements-dev.txt
python scripts\verify_windows.py --live-winget
```

## Build a Windows release

Install Inno Setup 7 if needed:

```powershell
winget install --id JRSoftware.InnoSetup.7 -e -s winget -i
```

Build the complete release bundle:

```powershell
python scripts\build_release.py
```

Run the full release/installer acceptance gate:

```powershell
python scripts\verify_windows.py --live-winget --installer
```

See [`docs/RELEASE.md`](docs/RELEASE.md) for versioning, installer behavior, optional Authenticode signing, checksums, and publishing a GitHub Release with `gh`.

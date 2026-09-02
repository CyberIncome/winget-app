# Winget Universal Dashboard

Windows GUI and CLI for inspecting installed applications, checking Winget updates, and performing controlled package updates.

## Downloads

For a normal Windows installation, download:

**`WingetUniversalDashboard-Setup-x64.exe`**

The installer is the recommended choice for almost everyone. It installs the dashboard per-user, includes the CLI, creates normal Windows uninstall metadata, and can create Start Menu/Desktop shortcuts.

Other release assets are intentionally named by use case:

- `WingetUniversalDashboard-Portable-x64.exe` — portable GUI; run it directly without installing.
- `WingetUniversalDashboard-CLI-x64.exe` — standalone command-line build.
- `BUILD_INFO.json` — exact source commit/version provenance for the release artifacts.
- `SHA256SUMS.txt` — SHA-256 checksums for integrity verification.

If you are unsure which file to choose, use **Setup-x64**.

## Development

Create a virtual environment and install the development requirements:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

Run the Windows verification gate:

```powershell
python scripts\verify_windows.py --live-winget
```

## Windows x64 release

Release versioning is controlled by the root `VERSION` file. A complete release is built locally with:

```powershell
python scripts\build_release.py
```

The installer pipeline requires current **Inno Setup 7**:

```powershell
winget install --id JRSoftware.InnoSetup.7 -e -s winget -i
```

A successful release build creates:

- `dist\WingetUniversalDashboard-Setup-x64.exe`
- `dist\WingetUniversalDashboard-Portable-x64.exe`
- `dist\WingetUniversalDashboard-CLI-x64.exe`
- `dist\BUILD_INFO.json`
- `dist\SHA256SUMS.txt`

The setup executable is a true AMD64/x64 Inno Setup 7 installer. It installs per-user under `%LOCALAPPDATA%\Programs\WingetUniversalDashboard`, includes the CLI, registers normal Windows uninstall metadata, and offers an optional desktop shortcut. Inside the install directory the executable names stay clean (`WingetUniversalDashboard.exe` and `WingetUniversalDashboardCLI.exe`) even though the public release assets are more explicit.

The portable one-file executables embed both `VERSION` and `BUILD_INFO.json`, so About/diagnostics can report the exact version and source identity even when a portable executable is copied away from the repository.

Release artifacts are bound to the exact clean Git commit recorded in `BUILD_INFO.json`; the SHA-256 manifest covers the installer, portable executables, and build identity. Stale, dirty, wrong-commit, wrong-version, or non-x64 artifacts are refused by the release/publish pipeline.

Run the complete installer acceptance gate with:

```powershell
python scripts\verify_windows.py --live-winget --installer
```

See [`docs/RELEASE.md`](docs/RELEASE.md) for versioning, installer acceptance, optional Authenticode signing, and GitHub Release publishing.

## GitHub Releases

After merging a release commit to `master`, pulling that exact pushed commit, and building/accepting the release from a clean tree, create a draft GitHub Release locally with:

```powershell
python scripts\publish_release.py
```

The publisher verifies source identity, checksums, AMD64 architecture, the pushed branch head, and an unused version tag before creating the release. It prepends a download guide to generated GitHub release notes so new users are explicitly directed to the Setup-x64 installer. GitHub Actions are not required.

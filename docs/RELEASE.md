# Windows x64 Release Guide

Winget Universal Dashboard uses a fully local release pipeline. GitHub Actions is not required.

## Release artifacts

A complete release produces:

- `dist\WingetUniversalDashboard-Setup-x64.exe` — recommended Windows installer;
- `dist\WingetUniversalDashboard.exe` — portable GUI executable;
- `dist\WingetUniversalDashboardCLI.exe` — portable CLI executable;
- `dist\SHA256SUMS.txt` — SHA-256 hashes for all three executables.

The installer is built with Inno Setup and installs per-user to:

`%LOCALAPPDATA%\Programs\WingetUniversalDashboard`

It creates a Start Menu shortcut, offers an optional desktop shortcut, includes the CLI executable, supports upgrade-over-existing-version behavior through a stable `AppId`, and registers a normal Windows uninstaller. User configuration under `%APPDATA%\WingetUniversalDashboard` and credentials stored by Windows keyring are outside the install directory and survive application upgrades/uninstall.

## Prerequisites

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

Install 64-bit Inno Setup 7:

```powershell
winget install --id JRSoftware.InnoSetup.7 -e -s winget -i
```

The build script also accepts an explicit compiler path:

```powershell
$env:INNO_SETUP_COMPILER = 'C:\Program Files\Inno Setup 7\ISCC.exe'
```

## Versioning

`VERSION` is the single release version source. The initial release is `1.0.0`.

Use semantic versions such as `1.1.0`, `1.1.1`, or `2.0.0`. Change `VERSION`, commit it, then build and verify before publishing.

## Build a complete release

```powershell
python scripts\build_release.py
```

This rebuilds the PyInstaller GUI/CLI executables, verifies they are AMD64/x64 PE files, compiles the Inno installer, and writes `SHA256SUMS.txt`.

To reuse already-built GUI/CLI files:

```powershell
python scripts\build_release.py --skip-app-build
```

## Installer acceptance

The installer smoke uses a temporary install directory and does not overwrite a normal user installation:

```powershell
python scripts\smoke_installer.py
```

For the full acceptance gate including a fresh release build and temporary install/uninstall:

```powershell
python scripts\verify_windows.py --live-winget --installer
```

`--installer` supersedes `--build`: it builds the complete release bundle, smokes the portable artifacts, then silently installs, launches, and uninstalls the setup executable.

## Optional Authenticode signing

Unsigned builds work, but Windows may display Unknown Publisher or SmartScreen reputation warnings.

If a suitable Authenticode certificate is installed in the Windows certificate store:

```powershell
$env:WUD_SIGN_CERT_SHA1 = 'YOUR_CERTIFICATE_THUMBPRINT'
```

Optional overrides:

```powershell
$env:SIGNTOOL_EXE = 'C:\Program Files (x86)\Windows Kits\10\bin\<version>\x64\signtool.exe'
$env:WUD_TIMESTAMP_URL = 'http://timestamp.digicert.com'
```

Then:

```powershell
python scripts\build_release.py --sign
```

The GUI and CLI are signed before installer creation; the completed installer is signed afterward. Each signature is verified with `signtool verify /pa`.

Never commit private keys, PFX passwords, certificate exports, or signing secrets.

## GitHub Release publishing

Publishing is local and uses GitHub CLI rather than Actions.

Authenticate once if needed:

```powershell
gh auth login
```

The publisher refuses a dirty worktree and refuses non-`master` branches by default.

Create a **draft** GitHub Release:

```powershell
python scripts\publish_release.py
```

After inspecting the draft/assets, publish it in GitHub's UI or create a public release directly:

```powershell
python scripts\publish_release.py --publish
```

The script reads `VERSION`, creates `v<VERSION>` targeting the exact current commit, uploads the setup executable, portable GUI/CLI executables, and checksums, and uses GitHub-generated release notes.

Do not publish from the hardening branch. Merge the accepted PR into `master`, pull `master`, run the full installer acceptance gate, and then publish.

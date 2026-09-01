import winreg
import re
import logging
import os
import ctypes
from ctypes import wintypes
import win32com.client
import pythoncom
import requests

from src.logic.config import ConfigManager

# Set up logging for this module
logger = logging.getLogger(__name__)

# --- Safety constants ---
MAX_REGISTRY_VALUE_LEN = 512
MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB
ALLOWED_URL_SCHEMES = ('https://',)

# Removed hardcoded URL_FALLBACKS; it's now in ConfigManager
# To get it: ConfigManager().url_fallbacks

# EXEs to never trust for application versioning
EXE_BLACKLIST = [
    "unins", "uninstall", "setup", "install", "helper",
    "crash", "update", "vcredist", "dxwebsetup", "patch",
    "report", "downloader", "checker"
]


def get_file_version(filepath):
    """Deep inspection of .exe metadata using Windows API
    with multiple string fallbacks."""
    if not filepath or not os.path.exists(filepath):
        return None
    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(
            filepath, None
        )
        if size <= 0:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(
            filepath, None, size, buffer
        ):
            return None

        # Strategy 1: Fixed File Info (Fastest/Reliable)
        fixed_info_ptr = ctypes.c_void_p()
        fixed_info_size = wintypes.UINT()
        if ctypes.windll.version.VerQueryValueW(
            buffer, "\\",
            ctypes.byref(fixed_info_ptr),
            ctypes.byref(fixed_info_size)
        ):
            class VS_FIXEDFILEINFO(ctypes.Structure):
                _fields_ = [
                    ("dwSignature", wintypes.DWORD),
                    ("dwStrucVersion", wintypes.DWORD),
                    ("dwFileVersionMS", wintypes.DWORD),
                    ("dwFileVersionLS", wintypes.DWORD),
                    ("dwProductVersionMS", wintypes.DWORD),
                    ("dwProductVersionLS", wintypes.DWORD),
                    ("dwFileFlagsMask", wintypes.DWORD),
                    ("dwFileFlags", wintypes.DWORD),
                    ("dwFileOS", wintypes.DWORD),
                    ("dwFileType", wintypes.DWORD),
                    ("dwFileSubtype", wintypes.DWORD),
                    ("dwFileDateMS", wintypes.DWORD),
                    ("dwFileDateLS", wintypes.DWORD),
                ]
            info = VS_FIXEDFILEINFO.from_address(
                fixed_info_ptr.value
            )
            version = "{}.{}.{}.{}".format(
                info.dwFileVersionMS >> 16,
                info.dwFileVersionMS & 0xFFFF,
                info.dwFileVersionLS >> 16,
                info.dwFileVersionLS & 0xFFFF,
            )
            if version and version != "0.0.0.0":
                return version

        # Strategy 2: String Table
        trans_ptr = ctypes.c_void_p()
        trans_size = wintypes.UINT()
        if ctypes.windll.version.VerQueryValueW(
            buffer, r"\VarFileInfo\Translation",
            ctypes.byref(trans_ptr),
            ctypes.byref(trans_size)
        ):
            if trans_size.value >= 4:
                trans_array = ctypes.cast(
                    trans_ptr,
                    ctypes.POINTER(wintypes.DWORD),
                )
                lang_cp = "{:04x}{:04x}".format(
                    trans_array[0] & 0xFFFF,
                    trans_array[0] >> 16,
                )
                for key in ["FileVersion", "ProductVersion"]:
                    query = (
                        "\\StringFileInfo\\"
                        + lang_cp + "\\" + key
                    )
                    val_ptr = ctypes.c_void_p()
                    val_size = wintypes.UINT()
                    if ctypes.windll.version.VerQueryValueW(
                        buffer, query,
                        ctypes.byref(val_ptr),
                        ctypes.byref(val_size),
                    ):
                        val = ctypes.wstring_at(
                            val_ptr.value
                        )
                        if val:
                            extracted = (
                                extract_version_from_text(val)
                            )
                            if extracted:
                                return extracted
    except Exception as e:
        logger.debug(
            f"Parser: Error reading file version "
            f"for {filepath}: {e}"
        )
    return None


def find_version_in_text_files(path):
    """Searches for common version-containing files."""
    if not path or not os.path.isdir(path):
        return None
    version_filenames = [
        "VERSION", "version.txt", "config.ini",
        "manifest.json",
    ]
    try:
        for root, dirs, files in os.walk(
            path, followlinks=False
        ):
            depth = (
                root.count(os.sep) - path.count(os.sep)
            )
            if depth > 2:
                dirs[:] = []
                continue
            for file in files:
                if file.upper() in [
                    f.upper() for f in version_filenames
                ]:
                    filepath = os.path.join(root, file)
                    try:
                        with open(
                            filepath, 'r', errors='ignore'
                        ) as f:
                            content = f.read(1024)
                            v_match = re.search(
                                r'(?:version|versionNo'
                                r'|DisplayVersion)'
                                r'\s*[:=]\s*([v\d\.]+)',
                                content, re.I,
                            )
                            if v_match:
                                return (
                                    v_match.group(1).strip()
                                )
                            v_raw = (
                                extract_version_from_text(
                                    content
                                )
                            )
                            if v_raw:
                                return v_raw
                    except Exception as e:
                        logger.debug(
                            f"Error reading {filepath}: {e}"
                        )
    except Exception as e:
        logger.debug(f"Error walking {path}: {e}")
    return None


def find_best_exe(path, app_name):
    """Finds the most likely main executable."""
    if not path or not os.path.isdir(path):
        return None
    best_exe, best_score = None, -1
    app_name_norm = normalize(app_name)
    app_words = set(re.findall(r'\w+', app_name_norm))
    try:
        for root, dirs, files in os.walk(
            path, followlinks=False
        ):
            depth = (
                root.count(os.sep) - path.count(os.sep)
            )
            if depth > 2:
                dirs[:] = []
                continue
            for file in files:
                if not file.lower().endswith(".exe"):
                    continue
                if any(
                    word in file.lower()
                    for word in EXE_BLACKLIST
                ):
                    continue
                fname_no_ext = (
                    os.path.splitext(file)[0].lower()
                )
                score = 0
                if (
                    fname_no_ext == app_name_norm
                    or fname_no_ext
                    == app_name.split()[0].lower()
                ):
                    score += 100
                if (
                    fname_no_ext in app_name_norm
                    or app_name_norm in fname_no_ext
                ):
                    score += 50
                f_words = set(
                    re.findall(r'\w+', fname_no_ext)
                )
                common = app_words.intersection(f_words)
                score += len(common) * 10
                try:
                    score += (
                        os.path.getsize(
                            os.path.join(root, file)
                        )
                        / (1024 * 1024 * 100)
                    )
                except OSError:
                    pass
                if score > best_score:
                    best_score = score
                    best_exe = os.path.join(root, file)
    except Exception as e:
        logger.debug(
            f"Error searching for exe in {path}: {e}"
        )
    return best_exe


def normalize(text):
    """Clean text for comparison."""
    if not text:
        return ""
    text = re.sub(r'\b\d+(\.\d+){2,}\b', '', text)
    text = re.sub(r'\(.*\)', '', text)
    return " ".join(text.lower().split()).strip()


def extract_version_from_text(text):
    """Regex fallback for versions in strings."""
    if not text:
        return None
    match = re.search(r'\b\d+(\.\d+){1,}\b', text)
    return match.group(0) if match else None


def get_registry_data():
    """Thorough crawl of Uninstall and AppModel keys."""
    logger.info("Parser: Starting registry crawl...")
    paths = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion"
         r"\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows"
         r"\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion"
         r"\Uninstall"),
    ]
    data = []
    for root, path in paths:
        try:
            with winreg.OpenKey(
                root, path, 0, winreg.KEY_READ
            ) as key:
                for i in range(
                    winreg.QueryInfoKey(key)[0]
                ):
                    try:
                        sk_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(
                            key, sk_name, 0,
                            winreg.KEY_READ,
                        ) as sk:
                            try:
                                name, _ = (
                                    winreg.QueryValueEx(
                                        sk, "DisplayName"
                                    )
                                )
                                name = str(name).strip()[
                                    :MAX_REGISTRY_VALUE_LEN
                                ]
                            except FileNotFoundError:
                                continue

                            version = None
                            for vk in [
                                "DisplayVersion", "Version"
                            ]:
                                try:
                                    v, _ = (
                                        winreg.QueryValueEx(
                                            sk, vk
                                        )
                                    )
                                    if v:
                                        version = (
                                            str(v).strip()[
                                                :MAX_REGISTRY_VALUE_LEN
                                            ]
                                        )
                                        break
                                except FileNotFoundError:
                                    pass

                            loc = None
                            for lk in [
                                "InstallLocation",
                                "UninstallString",
                            ]:
                                try:
                                    l, _ = (
                                        winreg.QueryValueEx(
                                            sk, lk
                                        )
                                    )
                                    if l:
                                        loc = (
                                            str(l).strip()
                                            .strip('"')
                                        )
                                        if (
                                            lk
                                            == "UninstallString"
                                        ):
                                            if loc.lower().endswith(".exe"):
                                                loc = os.path.dirname(loc)
                                            elif " /" in loc:
                                                loc = os.path.dirname(
                                                    loc.split(" /")[0]
                                                )
                                        if os.path.isdir(loc):
                                            break
                                        else:
                                            loc = None
                                except FileNotFoundError:
                                    pass

                            url = None
                            for uk in [
                                "HelpLink", "URLInfoAbout"
                            ]:
                                try:
                                    u, _ = (
                                        winreg.QueryValueEx(
                                            sk, uk
                                        )
                                    )
                                    if u:
                                        url = (
                                            str(u).strip()[
                                                :MAX_REGISTRY_VALUE_LEN
                                            ]
                                        )
                                        break
                                except FileNotFoundError:
                                    pass

                            data.append({
                                "subkey": sk_name,
                                "name": name,
                                "version": version or "???",
                                "path": loc,
                                "url": url,
                            })
                    except OSError:
                        continue
        except OSError:
            continue
    logger.info(
        f"Parser: Registry crawl finished. "
        f"Found {len(data)} items."
    )
    return data


def resolve_shortcut(lnk_path):
    """Resolves a Windows shortcut (.lnk) to its target."""
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(lnk_path)
        return shortcut.Targetpath
    except Exception as e:
        logger.debug(
            f"Failed to resolve shortcut {lnk_path}: {e}"
        )
        return None


def get_portable_apps():
    """Shortcut Detective: Finds apps by scanning shortcuts.
    (COM safe)"""
    logger.info("Parser: Shortcut Detective scanning...")
    pythoncom.CoInitialize()
    try:
        shortcut_locations = [
            os.path.join(
                os.environ["APPDATA"],
                r"Microsoft\Windows\Start Menu\Programs",
            ),
            os.path.join(
                os.environ["ProgramData"],
                r"Microsoft\Windows\Start Menu\Programs",
            ),
            os.path.join(
                os.environ["USERPROFILE"], "Desktop"
            ),
        ]
        potential_apps = []
        seen_targets = set()
        for loc in shortcut_locations:
            if not os.path.exists(loc):
                continue
            for root, dirs, files in os.walk(
                loc, followlinks=False
            ):
                for file in files:
                    if file.lower().endswith(".lnk"):
                        target = resolve_shortcut(
                            os.path.join(root, file)
                        )
                        if (
                            target
                            and target.lower().endswith(
                                ".exe"
                            )
                            and target not in seen_targets
                        ):
                            seen_targets.add(target)
                            potential_apps.append({
                                "name": os.path.splitext(
                                    file
                                )[0],
                                "path": target,
                                "folder": os.path.dirname(
                                    target
                                ),
                            })
        logger.info(
            f"Parser: Shortcut Detective found "
            f"{len(potential_apps)} candidates."
        )
        return potential_apps
    finally:
        pythoncom.CoUninitialize()


def find_version_in_registry(
    winget_name, winget_id, registry_data,
    allow_fuzzy=True,
):
    """Scored heuristic matching with binary fallback."""
    w_name_norm = normalize(winget_name)
    w_id_low = winget_id.lower().replace('.', ' ')
    w_words = set(re.findall(r'\w+', w_name_norm))
    for entry in registry_data:
        r_sk_low = entry["subkey"].lower().replace(
            '.', ' '
        )
        if (
            r_sk_low == w_id_low
            or (len(r_sk_low) > 5 and r_sk_low in w_id_low)
            or normalize(entry["name"]) == w_name_norm
        ):
            if entry["version"] != "???":
                return entry["version"]
            elif entry["path"]:
                v_text = find_version_in_text_files(
                    entry["path"]
                )
                if v_text:
                    return v_text
                exe = find_best_exe(
                    entry["path"], entry["name"]
                )
                if exe:
                    v = get_file_version(exe)
                    if v:
                        return v
    for entry in registry_data:
        r_words = set(
            re.findall(r'\w+', normalize(entry["name"]))
        )
        if not r_words:
            continue
        intersection = w_words.intersection(r_words)
        coverage = len(intersection) / len(r_words)
        if allow_fuzzy and coverage >= 0.9 and (
            len(intersection) >= 2
            or (
                len(intersection) == 1
                and len(list(intersection)[0]) > 7
            )
        ):
            if entry["version"] != "???":
                return entry["version"]
            elif entry["path"]:
                exe = find_best_exe(
                    entry["path"], entry["name"]
                )
                if exe:
                    v = get_file_version(exe)
                    if v:
                        return v
    return None


def parse_winget_upgrade(output, reg_data=None):
    """Parses winget upgrade output."""
    if not output or "No applicable update found" in output:
        return []
    lines = [
        line.strip()
        for line in output.splitlines()
        if line.strip()
    ]
    header_line = ""
    separator_index = -1
    for i, line in enumerate(lines):
        if (
            "Name" in line
            and "Id" in line
            and "Version" in line
        ):
            header_line = line
            if (
                i + 1 < len(lines)
                and lines[i + 1].startswith("---")
            ):
                separator_index = i + 1
                break
    if separator_index == -1:
        return []
    indices = [
        header_line.find(col)
        for col in [
            "Name", "Id", "Version", "Available", "Source"
        ]
    ]
    indices.append(1000)

    if reg_data is None:
        reg_data = get_registry_data()

    results = []
    for line in lines[separator_index + 1:]:
        row = {
            "Name": line[
                indices[0]:indices[1]
            ].strip(),
            "Id": line[indices[1]:indices[2]].strip(),
            "Version": line[
                indices[2]:indices[3]
            ].strip(),
            "Available": line[
                indices[3]:indices[4]
            ].strip(),
        }
        if row["Name"] and row["Id"]:
            logger.debug(f"Winget parsed row: {row}")
            reported_version = row["Version"]
            if reported_version.lower() == "unknown":
                v = find_version_in_registry(
                    row["Name"],
                    row["Id"],
                    reg_data,
                    allow_fuzzy=False,
                )
                if v:
                    row["Version"] = v

            if (
                _should_compare_winget_versions(
                    reported_version, row["Version"]
                )
                and row["Available"]
            ):
                if not is_version_newer(
                    row["Available"], row["Version"]
                ):
                    logger.warning(
                        f"Skipping Winget update for "
                        f"{row['Name']}: "
                        f"{row['Available']} is not newer "
                        f"than {row['Version']}"
                    )
                    continue

            results.append(row)
    results.sort(
        key=lambda x: (
            x["Version"].lower() != "unknown",
            x["Name"].lower(),
        )
    )
    return results


def get_total_inventory(reg_data=None):
    """Builds complete list of apps."""
    logger.info(
        "Parser: Starting system inventory collection..."
    )
    if reg_data is None:
        reg_data = get_registry_data()
    portable_leads = get_portable_apps()
    inventory = []
    seen_names = set()

    for entry in reg_data:
        name = entry["name"]
        if not name or name.lower() in seen_names:
            continue
        version = entry["version"]
        if (
            (version == "???" or version.lower() == "unknown")
            and entry["path"]
        ):
            v_text = find_version_in_text_files(
                entry["path"]
            )
            if v_text:
                version = v_text
            else:
                exe = find_best_exe(entry["path"], name)
                if exe:
                    v_bin = get_file_version(exe)
                    if v_bin:
                        version = v_bin
        inventory.append({
            "Name": name,
            "Id": entry["subkey"],
            "Version": version,
            "Available": "",
            "Type": "Installed",
            "Managed": "Windows",
            "URL": entry["url"],
            "Path": entry["path"],
        })
        seen_names.add(name.lower())

    for lead in portable_leads:
        name = lead["name"]
        if name.lower() in seen_names:
            continue
        ver = get_file_version(lead["path"])
        if not ver:
            ver = find_version_in_text_files(lead["folder"])
        inventory.append({
            "Name": name,
            "Id": "Portable." + name.replace(" ", ""),
            "Version": ver or "Unknown",
            "Available": "",
            "Type": "Portable",
            "Managed": "Local",
            "URL": None,
            "Path": lead["path"],
        })
        seen_names.add(name.lower())

    inventory.sort(key=lambda x: x["Name"].lower())
    logger.info(
        f"Parser: Total System Inventory complete. "
        f"Count: {len(inventory)}"
    )
    return inventory


def parse_version_tuple(version_str):
    """Parse a version string into a tuple of integers, ignoring noise."""
    if not version_str:
        return None
    # Extract only the sequence of numbers and dots
    match = re.search(r'(\d+(?:\.\d+)+|\d+)', str(version_str))
    if not match:
        return None
    try:
        parts = [int(p) for p in match.group(1).split('.')]
        return tuple(parts)
    except (ValueError, AttributeError):
        return None


def is_version_newer(remote_v, installed_v):
    """Compare two version strings.

    Returns True if remote is newer than installed.
    """
    remote = parse_version_tuple(remote_v)
    installed = parse_version_tuple(installed_v)

    if not remote or not installed:
        logger.debug(
            f"Version comparison failed to parse: "
            f"remote='{remote_v}' -> {remote}, "
            f"installed='{installed_v}' -> {installed}"
        )
        return False

    max_len = max(len(remote), len(installed))
    remote_padded = remote + (0,) * (
        max_len - len(remote)
    )
    installed_padded = installed + (0,) * (
        max_len - len(installed)
    )

    is_newer = remote_padded > installed_padded
    if is_newer:
        logger.debug(
            f"Version comparison: {remote_v} "
            f"({remote_padded}) > {installed_v} "
            f"({installed_padded}) [NEWER]"
        )
    else:
        logger.debug(
            f"Version comparison: {remote_v} "
            f"({remote_padded}) <= {installed_v} "
            f"({installed_padded}) [NOT NEWER]"
        )
    return is_newer


def _is_uncertain_version(version_str):
    """Return whether a version string is approximate or unknown."""
    if not version_str:
        return True
    version_text = str(version_str).strip().lower()
    if version_text in {"unknown", "???"}:
        return True
    return any(token in version_text for token in ("<", ">", "~"))


def _should_compare_winget_versions(
    reported_version, displayed_version
):
    """Return whether local filtering is safe for a winget row."""
    if _is_uncertain_version(reported_version):
        return False
    return parse_version_tuple(displayed_version) is not None


# --- HTTP safety helpers (C2 fix) ---

def is_valid_version(v: str) -> bool:
    """Check if a string looks like a valid version number."""
    if not v or len(v) > 20: return False
    if not any(c.isdigit() for c in v): return False
    # Avoid strings that are just dates or long integers without separators
    if v.count('.') == 0 and len(v) > 4: return False
    parts = v.split('.')
    if len(parts) > 4: return False
    # Avoid thousands-separated numbers (e.g., 2.345 stars) in generic text
    # Heuristic: segments > 9999 are rarely version numbers unless it's a date/build 
    # but even then, multiple such segments or huge minor jumps are red flags.
    for p in parts:
        if p.isdigit() and int(p) > 9999: return False
    return True


def _is_safe_url(url):
    """Validate URL scheme is HTTPS-only."""
    return bool(
        url and any(
            url.lower().startswith(s)
            for s in ALLOWED_URL_SCHEMES
        )
    )


def _safe_get(url, timeout=5, **kwargs):
    """HTTP GET with response size cap to prevent OOM."""
    kwargs.setdefault('timeout', timeout)
    resp = requests.get(url, stream=True, **kwargs)
    cl = resp.headers.get('Content-Length')
    if cl and int(cl) > MAX_RESPONSE_BYTES:
        resp.close()
        logger.warning(
            f"Skipping {url}: Content-Length {cl} "
            f"exceeds {MAX_RESPONSE_BYTES} byte limit"
        )
        return None
    chunks = []
    bytes_read = 0
    for chunk in resp.iter_content(chunk_size=8192):
        chunks.append(chunk)
        bytes_read += len(chunk)
        if bytes_read > MAX_RESPONSE_BYTES:
            logger.warning(
                f"Truncating response from {url}"
            )
            break
    resp._content = b''.join(chunks)
    resp.close()
    return resp


def check_remote_version(url, installed_version=None):
    """Smart scraper to find the latest version number.

    Applies HTTPS-only URL validation (C2) and handles
    GitHub API rate limiting (C3).
    """
    logger.debug(
        f"Checking remote version for URL: {url} "
        f"(Installed: {installed_version})"
    )
    if not _is_safe_url(url):
        logger.warning(f"Rejecting non-HTTPS URL: {url}")
        return None
    try:
        if "github.com" in url:
            match = re.search(
                r'github\.com/([^/]+)/([^/]+)', url
            )
            if match:
                owner, repo = match.groups()
                repo = repo.split('?')[0].rstrip('/')

                # Try GitHub API first (most reliable)
                api_url = (
                    f"https://api.github.com/repos/"
                    f"{owner}/{repo}/releases/latest"
                )
                try:
                    logger.debug(
                        f"Trying GitHub API: {api_url}"
                    )
                    headers = {
                        'Accept': 'application/vnd.github.v3+json'
                    }
                    
                    # Attach PAT if available
                    pat = ConfigManager().github_pat
                    if pat:
                        headers['Authorization'] = f"Bearer {pat}"

                    api_resp = _safe_get(api_url, headers=headers)
                    if api_resp is None:
                        pass  # Size limit hit
                    elif api_resp.status_code == 403:
                        remaining = (
                            api_resp.headers.get(
                                'X-RateLimit-Remaining',
                                '?',
                            )
                        )
                        logger.warning(
                            f"GitHub API rate limited "
                            f"(remaining: {remaining}). "
                            f"Missing or invalid PAT? "
                            f"Skipping API checks."
                        )
                    elif api_resp.status_code == 200:
                        data = api_resp.json()
                        tag = data.get('tag_name', '')
                        version = tag.lstrip('vV')
                        logger.debug(
                            f"GitHub API tag: {tag} "
                            f"-> {version}"
                        )
                        if (
                            version
                            and is_valid_version(version)
                        ):
                            if (
                                installed_version is None
                                or is_version_newer(
                                    version,
                                    installed_version,
                                )
                            ):
                                logger.info(
                                    f"Version from GitHub "
                                    f"API: {version}"
                                )
                                return version
                            else:
                                logger.debug(
                                    f"GitHub API version "
                                    f"{version} not newer "
                                    f"than "
                                    f"{installed_version}"
                                )
                                return None # Up to date
                except Exception as e:
                    logger.debug(
                        f"GitHub API failed: {e}"
                    )

                # Fallback: releases/latest redirect
                releases_url = (
                    f"https://github.com/{owner}/"
                    f"{repo}/releases/latest"
                )
                logger.debug(
                    f"Trying GitHub redirect: "
                    f"{releases_url}"
                )
                response = _safe_get(
                    releases_url, allow_redirects=True
                )
                if (
                    response
                    and response.status_code == 200
                ):
                    if '/tag/' in response.url:
                        tag = response.url.split(
                            '/tag/'
                        )[-1]
                        version = tag.lstrip('vV')
                        if is_valid_version(version):
                            if (
                                installed_version is None
                                or is_version_newer(
                                    version,
                                    installed_version,
                                )
                            ):
                                logger.info(
                                    f"Version from GitHub "
                                    f"URL tag: {version}"
                                )
                                return version
                            logger.debug(
                                f"GitHub tag {version} "
                                f"not newer than "
                                f"{installed_version}"
                            )
                            return None

                    logger.debug(
                        "GitHub latest-release URL did not resolve "
                        "to a tag. Skipping page text scraping."
                    )
                return None

        # For non-GitHub URLs
        logger.debug(f"Scraping generic URL: {url}")
        response = _safe_get(url)
        if response and response.status_code == 200:
            versions = re.findall(
                r'[vV]?(\d+\.\d+(?:\.\d+){0,2})\b',
                response.text,
            )
            logger.debug(
                f"Found {len(versions)} potential "
                f"version candidates."
            )
            for v in versions:
                if is_valid_version(v):
                    if (
                        installed_version is None
                        or is_version_newer(
                            v, installed_version
                        )
                    ):
                        logger.info(
                            f"Accepted version: {v}"
                        )
                        return v
            logger.debug(
                "No valid newer versions found."
            )
    except Exception as e:
        logger.debug(
            f"Error checking remote version: {e}"
        )
    return None


def detect_remote_versions_batch(data, url_fallbacks):
    """Return remote version hits for inventory items."""
    results = []
    for i, item in enumerate(data):
        url = item.get("URL")
        if not url:
            item_name = str(item.get("Name", "")).lower()
            for key, fallback in url_fallbacks.items():
                if key in item_name:
                    url = fallback
                    break
        if url and (
            "github.com" in url
            or "release" in url.lower()
        ):
            remote_version = check_remote_version(
                url, item.get("Version")
            )
            if remote_version:
                results.append((i, remote_version))
    return results


def detective_scan_worker(data, url_fallbacks, result_queue):
    """Run remote version checks in an isolated process."""
    try:
        result_queue.put({
            "results": detect_remote_versions_batch(
                data, url_fallbacks
            )
        })
    except Exception as exc:
        result_queue.put({"error": str(exc)})


def parse_winget_show_version(output):
    """Extracts installed version from show command."""
    if not output:
        return None
    match = re.search(
        r"(?:Installed|Installed Version):"
        r"\s*([v\d\.]+)",
        output, re.IGNORECASE,
    )
    return match.group(1).strip() if match else None

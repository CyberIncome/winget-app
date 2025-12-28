import winreg
import re
import logging
import os
import ctypes
from ctypes import wintypes
import win32com.client
import requests

logger = logging.getLogger(__name__)

# EXEs to never trust for application versioning
EXE_BLACKLIST = ["unins", "uninstall", "setup", "install", "helper", "crash", "update", "vcredist", "dxwebsetup", "patch", "report", "downloader", "checker"]

def get_file_version(filepath):
    """Deep inspection of .exe metadata using Windows API with multiple string fallbacks."""
    if not filepath or not os.path.exists(filepath):
        return None
    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(filepath, None)
        if size <= 0: return None
        buffer = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(filepath, None, size, buffer):
            return None
            
        # Strategy 1: Fixed File Info (Fastest/Reliable)
        fixed_info_ptr = ctypes.c_void_p()
        fixed_info_size = wintypes.UINT()
        if ctypes.windll.version.VerQueryValueW(buffer, "\\", ctypes.byref(fixed_info_ptr), ctypes.byref(fixed_info_size)):
            class VS_FIXEDFILEINFO(ctypes.Structure):
                _fields_ = [("dwSignature", wintypes.DWORD), ("dwStrucVersion", wintypes.DWORD),
                            ("dwFileVersionMS", wintypes.DWORD), ("dwFileVersionLS", wintypes.DWORD),
                            ("dwProductVersionMS", wintypes.DWORD), ("dwProductVersionLS", wintypes.DWORD),
                            ("dwFileFlagsMask", wintypes.DWORD), ("dwFileFlags", wintypes.DWORD),
                            ("dwFileOS", wintypes.DWORD), ("dwFileType", wintypes.DWORD),
                            ("dwFileSubtype", wintypes.DWORD), ("dwFileDateMS", wintypes.DWORD),
                            ("dwFileDateLS", wintypes.DWORD)]
            info = VS_FIXEDFILEINFO.from_address(fixed_info_ptr.value)
            version = "{}.{}.{}.{}".format(info.dwFileVersionMS >> 16, info.dwFileVersionMS & 0xFFFF,
                                         info.dwFileVersionLS >> 16, info.dwFileVersionLS & 0xFFFF)
            if version and version != "0.0.0.0":
                return version

        # Strategy 2: String Table
        trans_ptr = ctypes.c_void_p()
        trans_size = wintypes.UINT()
        if ctypes.windll.version.VerQueryValueW(buffer, r"\VarFileInfo\Translation", ctypes.byref(trans_ptr), ctypes.byref(trans_size)):
            if trans_size.value >= 4:
                trans_array = ctypes.cast(trans_ptr, ctypes.POINTER(wintypes.DWORD))
                lang_cp = "{:04x}{:04x}".format(trans_array[0] & 0xFFFF, trans_array[0] >> 16)
                
                for key in ["FileVersion", "ProductVersion"]:
                    query = f"\\StringFileInfo\\{lang_cp}\\{key}"
                    val_ptr = ctypes.c_void_p()
                    val_size = wintypes.UINT()
                    if ctypes.windll.version.VerQueryValueW(buffer, query, ctypes.byref(val_ptr), ctypes.byref(val_size)):
                        val = ctypes.wstring_at(val_ptr.value)
                        if val:
                            extracted = extract_version_from_text(val)
                            if extracted: return extracted
    except Exception: pass
    return None

def find_version_in_text_files(path):
    """Searches for common version-containing files like VERSION, config.ini, etc."""
    if not path or not os.path.isdir(path): return None
    
    version_filenames = ["VERSION", "version.txt", "config.ini", "manifest.json"]
    
    try:
        # Shallow search up to 2 levels
        for root, dirs, files in os.walk(path):
            depth = root.count(os.sep) - path.count(os.sep)
            if depth > 2:
                dirs[:] = []
                continue
                
            for file in files:
                if file.upper() in [f.upper() for f in version_filenames]:
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', errors='ignore') as f:
                            content = f.read(1024) # Read first KB
                            v_match = re.search(r'(?:version|versionNo|DisplayVersion)\s*[:=]\s*([v\d\.]+)', content, re.I)
                            if v_match:
                                return v_match.group(1).strip()
                            v_raw = extract_version_from_text(content)
                            if v_raw: return v_raw
                    except Exception: continue
    except Exception: pass
    return None

def find_best_exe(path, app_name):
    """Finds the most likely main executable, searching recursively and scoring based on name match."""
    if not path or not os.path.isdir(path): return None
    
    best_exe = None
    best_score = -1
    
    app_name_norm = normalize(app_name)
    app_words = set(re.findall(r'\w+', app_name_norm))

    try:
        for root, dirs, files in os.walk(path):
            depth = root.count(os.sep) - path.count(os.sep)
            if depth > 2:
                dirs[:] = []
                continue

            for file in files:
                if not file.lower().endswith(".exe"): continue
                if any(word in file.lower() for word in EXE_BLACKLIST): continue
                    
                fname_no_ext = os.path.splitext(file)[0].lower()
                score = 0
                if fname_no_ext == app_name_norm or fname_no_ext == app_name.split()[0].lower():
                    score += 100
                if fname_no_ext in app_name_norm or app_name_norm in fname_no_ext:
                    score += 50
                f_words = set(re.findall(r'\w+', fname_no_ext))
                common = app_words.intersection(f_words)
                score += len(common) * 10
                try:
                    score += os.path.getsize(os.path.join(root, file)) / (1024 * 1024 * 100)
                except OSError: pass

                if score > best_score:
                    best_score = score
                    best_exe = os.path.join(root, file)
    except Exception: pass
    return best_exe

def normalize(text):
    """Clean text for comparison."""
    if not text: return ""
    text = re.sub(r'\b\d+(\.\d+){2,}\b', '', text) 
    text = re.sub(r'\(.*\)', '', text)
    return " ".join(text.lower().split()).strip()

def extract_version_from_text(text):
    """Regex fallback for versions in strings."""
    if not text: return None
    match = re.search(r'\b\d+(\.\d+){1,}\b', text)
    return match.group(0) if match else None

def get_registry_data():
    """Thorough crawl of Uninstall and AppModel keys."""
    logger.info("Deep Scan: Starting thorough Registry crawl...")
    paths = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")]
    
    data = []
    for root, path in paths:
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        sk_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, sk_name, 0, winreg.KEY_READ) as sk:
                            try:
                                name, _ = winreg.QueryValueEx(sk, "DisplayName")
                                name = str(name).strip()
                            except FileNotFoundError: continue

                            version = None
                            for vk in ["DisplayVersion", "Version"]:
                                try:
                                    v, _ = winreg.QueryValueEx(sk, vk)
                                    if v: version = str(v).strip(); break
                                except FileNotFoundError: pass

                            loc = None
                            for lk in ["InstallLocation", "UninstallString"]:
                                try:
                                    l, _ = winreg.QueryValueEx(sk, lk)
                                    if l: 
                                        loc = str(l).strip().strip('"')
                                        if lk == "UninstallString": 
                                            if loc.lower().endswith(".exe"):
                                                loc = os.path.dirname(loc)
                                            elif " /" in loc:
                                                loc = os.path.dirname(loc.split(" /")[0])
                                        if os.path.isdir(loc): break
                                        else: loc = None
                                except FileNotFoundError: pass

                            data.append({"subkey": sk_name, "name": name, "version": version or "???", "path": loc})
                    except OSError: continue
        except OSError: continue

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages", 0, winreg.KEY_READ) as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sk = winreg.EnumKey(key, i)
                    parts = sk.split('_')
                    if len(parts) >= 2: data.append({"subkey": sk, "name": parts[0], "version": parts[1], "path": None})
                except Exception: continue
    except OSError: pass
    return data

def resolve_shortcut(lnk_path):
    """Resolves a Windows shortcut (.lnk) to its target path."""
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(lnk_path)
        return shortcut.Targetpath
    except Exception:
        return None

def get_portable_apps():
    """
    Shortcut Detective: Finds apps that aren't in the registry by scanning shortcuts.
    """
    logger.info("Shortcut Detective: Scanning for potential portable apps...")
    shortcut_locations = [
        os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ["ProgramData"], r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ["USERPROFILE"], "Desktop")
    ]
    
    potential_apps = []
    seen_targets = set()
    
    for loc in shortcut_locations:
        if not os.path.exists(loc): continue
        for root, dirs, files in os.walk(loc):
            for file in files:
                if file.lower().endswith(".lnk"):
                    target = resolve_shortcut(os.path.join(root, file))
                    if target and target.lower().endswith(".exe") and target not in seen_targets:
                        seen_targets.add(target)
                        # Check if it's in a common location or not in Program Files (standard apps)
                        # We'll filter these against the registry later.
                        potential_apps.append({
                            "name": os.path.splitext(file)[0],
                            "path": target,
                            "folder": os.path.dirname(target)
                        })
                        
    return potential_apps

def find_version_in_registry(winget_name, winget_id, registry_data):
    """Scored heuristic matching with binary fallback."""
    w_name_norm = normalize(winget_name)
    w_id_low = winget_id.lower().replace('.', ' ')
    w_words = set(re.findall(r'\w+', w_name_norm))
    
    # 1. High-Confidence Matches
    for entry in registry_data:
        r_sk_low = entry["subkey"].lower().replace('.', ' ')
        if r_sk_low == w_id_low or (len(r_sk_low) > 5 and r_sk_low in w_id_low) or normalize(entry["name"]) == w_name_norm:
            if entry["version"] != "???":
                logger.info(f"  [HIT] Registry Match: '{winget_name}' ({entry['version']})")
                return entry["version"]
            elif entry["path"]:
                logger.info(f"  [INFO] Found Registry match for '{winget_name}' but version is missing. Checking binaries in {entry['path']}...")
                
                v_text = find_version_in_text_files(entry["path"])
                if v_text: return v_text
                
                exe = find_best_exe(entry["path"], entry["name"])
                if exe:
                    v = get_file_version(exe)
                    if v:
                        logger.info(f"  [HIT] Binary Success: Found {v} in '{os.path.basename(exe)}'")
                        return v

    # 2. Refined Scored Match
    for entry in registry_data:
        r_words = set(re.findall(r'\w+', normalize(entry["name"])))
        if not r_words: continue
        intersection = w_words.intersection(r_words)
        coverage = len(intersection) / len(r_words)
        if coverage >= 0.9 and (len(intersection) >= 2 or (len(intersection) == 1 and len(list(intersection)[0]) > 7)):
            if entry["version"] != "???":
                logger.info(f"  [HIT] Scored Match ({coverage:.0%}): '{winget_name}' -> '{entry['name']}' ({entry['version']})")
                return entry["version"]
            elif entry["path"]:
                exe = find_best_exe(entry["path"], entry["name"])
                if exe:
                    v = get_file_version(exe)
                    if v: return v
    return None

def parse_winget_upgrade(output):
    """Full parsing pipeline."""
    if not output or "No applicable update found" in output: return []
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    header_line = ""
    separator_index = -1
    for i, line in enumerate(lines):
        if "Name" in line and "Id" in line and "Version" in line:
            header_line = line
            if i + 1 < len(lines) and lines[i+1].startswith("---"):
                separator_index = i + 1
                break
    if separator_index == -1: return []
    
    indices = [header_line.find(col) for col in ["Name", "Id", "Version", "Available", "Source"]]
    indices.append(1000)
    
    reg_data = get_registry_data()
    results = []
    
    for line in lines[separator_index + 1:]:
        row = {"Name": line[indices[0]:indices[1]].strip(), "Id": line[indices[1]:indices[2]].strip(),
               "Version": line[indices[2]:indices[3]].strip(), "Available": line[indices[3]:indices[4]].strip()}
        
        if row["Name"] and row["Id"]:
            if row["Version"].lower() == "unknown":
                logger.info(f"Investigating 'Unknown' app: {row['Name']}...")
                v = find_version_in_registry(row["Name"], row["Id"], reg_data)
                if not v: v = extract_version_from_text(row["Name"])
                if v: row["Version"] = v
                else: logger.warning(f"  [FAIL] Investigation failed for '{row['Name']}'.")
            results.append(row)
            
    results.sort(key=lambda x: (x["Version"].lower() != "unknown", x["Name"].lower()))
    return results

def get_total_inventory():
    """
    Builds a complete list of all apps: Winget, Registry, and Portable.
    """
    reg_data = get_registry_data()
    portable_leads = get_portable_apps()
    
    inventory = []
    seen_names = set()
    
    # 1. Add Registry Apps
    for entry in reg_data:
        name = entry["name"]
        if name.lower() not in seen_names:
            inventory.append({
                "Name": name,
                "Id": entry["subkey"],
                "Version": entry["version"],
                "Type": "Installed",
                "Managed": "Windows"
            })
            seen_names.add(name.lower())
            
    # 2. Add Portable Apps (Filtered)
    for lead in portable_leads:
        name = lead["name"]
        if name.lower() not in seen_names:
            # Deep Scan the portable EXE
            ver = get_file_version(lead["path"])
            if not ver:
                ver = find_version_in_text_files(lead["folder"])
            
            inventory.append({
                "Name": name,
                "Id": "Portable." + name.replace(" ", "") ,
                "Version": ver or "Unknown",
                "Type": "Portable",
                "Managed": "Local"
            })
            seen_names.add(name.lower())
            
    return inventory

def check_remote_version(url):
    """
    Simple scraper to find a version number on a webpage (e.g. GitHub Releases).
    No API key required.
    """
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            # Look for common version patterns in the HTML
            # e.g. v1.2.3 or 1.2.3
            versions = re.findall(r'[vV]?(\d+\.\d+(?:\.\d+)*)', response.text)
            if versions:
                # Return the most frequent one or the first one found
                return versions[0]
    except Exception:
        pass
    return None

def parse_winget_show_version(output):
    """Extracts installed version from show command."""
    if not output: return None
    match = re.search(r"(?:Installed|Installed Version):\s*([v\d\.]+)", output, re.IGNORECASE)
    return match.group(1).strip() if match else None
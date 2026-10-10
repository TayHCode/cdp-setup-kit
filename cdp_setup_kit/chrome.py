import re
from typing import Any, Dict, List, Optional, Tuple

from .constants import LOOPBACK
from .errors import KitError
from .paths import path_key, path_module
from .system import System

CHROME_NOT_FOUND_HINT = "install Google Chrome, or pass --chrome PATH. For Chrome for Testing, see README.md#install-chrome-on-linux for the exact download/extract/chmod commands"

VERSION = r"\d+\.\d+\.\d+\.\d+"


def safe_characters(system: System, path: str) -> None:
    banned = '\"`$%' + ("\\" if system.platform != "windows" else "")
    if any(ord(char) < 32 or ord(char) == 127 or char in banned for char in path):
        raise KitError(8, "refused unsafe characters in path")


def find_chrome(system: System, data: Dict[str, Any], explicit: Optional[str] = None) -> Optional[str]:
    path = path_module(system)
    candidates = [explicit, data.get("chrome_path"), system.env.get("CDP_SETUP_KIT_CHROME")]
    if system.platform == "windows":
        key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
        candidates += [system.registry_value(root, key) for root in ("HKEY_LOCAL_MACHINE", "HKEY_CURRENT_USER")]
        candidates += [path.join(system.env[key], "Google", "Chrome", "Application", "chrome.exe") for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA") if system.env.get(key)]
    elif system.platform == "linux":
        candidates += [system.which("google-chrome-stable"), system.which("google-chrome"), "/opt/google/chrome/chrome"]
    elif system.platform == "macos":
        candidates += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    for candidate in candidates:
        if candidate:
            safe_characters(system, candidate)
            if system.is_file(candidate):
                resolved = system.resolve_path(candidate)
                safe_characters(system, resolved)
                return resolved
    return None


def identity(system: System, chrome: str) -> Tuple[Optional[str], bool]:
    if system.platform == "windows":
        path = path_module(system)
        try:
            versions = [name for name in system.list_dir(path.dirname(chrome)) if re.fullmatch(VERSION, name) and system.is_dir(path.join(path.dirname(chrome), name))]
        except OSError:
            versions = []
        version = max(versions, key=lambda value: tuple(int(part) for part in value.split("."))) if versions else None
        return version, path.normcase(chrome).endswith(r"\google\chrome\application\chrome.exe")
    try:
        code, output, _ = system.run([chrome, "--version"], timeout=5)
    except (OSError, TimeoutError):
        return None, False
    match = re.search(VERSION, output)
    return (match.group() if code == 0 and match else None), code == 0 and output.startswith("Google Chrome")


def build_chrome_argv(chrome_path: str, profile_dir: str, port: int) -> List[str]:
    return [chrome_path, "--user-data-dir=" + profile_dir, "--remote-debugging-port=" + str(port),
            "--remote-debugging-address=" + LOOPBACK, "--no-first-run", "--no-default-browser-check"]


def check_profile_dir(system: System, folder: str, data: Dict[str, Any], name: str = "") -> str:
    path = path_module(system)
    safe_characters(system, folder)
    resolved = system.resolve_path(folder)
    safe_characters(system, resolved)
    normalized = path_key(system, resolved)
    user = system.resolve_path(system.user_dir())
    if system.platform == "windows":
        bases = [path.join(user, "AppData", "Local")] + ([system.env["LOCALAPPDATA"]] if system.env.get("LOCALAPPDATA") else [])
        blocked = [path.join(base, *parts) for base in bases for parts in [("Google", "Chrome", "User Data"), ("Google", "Chrome Beta", "User Data"), ("Google", "Chrome SxS", "User Data"), ("Chromium", "User Data"), ("Microsoft", "Edge", "User Data")]]
    elif system.platform == "macos":
        base = path.join(user, "Library", "Application Support")
        blocked = [path.join(base, item) for item in ("Google/Chrome", "Google/Chrome Beta", "Google/Chrome Canary", "Chromium", "Microsoft Edge")]
    else:
        bases = [path.join(user, ".config")] + ([system.env["XDG_CONFIG_HOME"]] if system.env.get("XDG_CONFIG_HOME") else [])
        blocked = [path.join(base, item) for base in bases for item in ("google-chrome", "google-chrome-beta", "google-chrome-unstable", "chromium")]
        blocked += [path.join(user, item) for item in ("snap/chromium", ".var/app/com.google.Chrome", "Library/Application Support/Google/Chrome", "Library/Application Support/Chromium")]
    if normalized == path_key(system, user) or path.dirname(normalized) == normalized:
        raise KitError(8, "refused: use a dedicated profile folder")
    for root in blocked:
        root = path_key(system, root)
        if normalized == root or normalized.startswith(root + path.sep) or root.startswith(normalized.rstrip(path.sep) + path.sep):
            raise KitError(8, "refused: use a dedicated profile folder outside everyday browser data")
    ancestor = resolved
    while ancestor:
        if system.exists(path.join(ancestor, ".git")):
            raise KitError(8, "refused: profile data cannot be inside a source checkout")
        parent = path.dirname(ancestor)
        if parent == ancestor:
            break
        ancestor = parent
    for other_name, profile in data["profiles"].items():
        if other_name != name and path_key(system, profile["profile_dir"]) == normalized:
            raise KitError(8, "profile folder already used by " + other_name)
    return resolved

import re
from typing import List

from .constants import APP_NAME, LINUX_MARKER
from .paths import Locations, path_module
from .system import System


def entry_path(system: System, paths: Locations, name: str) -> str:
    return path_module(system).join(paths.startup, APP_NAME + "-" + name + ".desktop")


SAFE_ARGUMENT = re.compile(r"[A-Za-z0-9_@+=:,./-]+")


def quote_argument(arg: str) -> str:
    # Desktop Entry rule: any argument with a reserved character is wrapped in double quotes.
    # Quote, backtick, dollar, backslash and percent never reach here (check_profile_dir refuses them).
    return arg if SAFE_ARGUMENT.fullmatch(arg) else '"' + arg + '"'


def desktop_text(name: str, argv: List[str]) -> str:
    command = " ".join(quote_argument(arg) for arg in argv)
    return "\n".join(["[Desktop Entry]", "Type=Application", "Name=" + APP_NAME + ": " + name,
                      "Comment=Opens the " + name + " Chrome window with its debugging port. Managed by " + APP_NAME + ".",
                      "Exec=" + command, "Terminal=false", "X-GNOME-Autostart-enabled=true", LINUX_MARKER,
                      "X-Cdp-Setup-Kit-Profile=" + name, ""])


def status(system: System, path: str, expected: str) -> str:
    if not (system.exists(path) or system.is_link(path)):
        return "disabled"
    try:
        actual = system.read_text(path)
    except (OSError, UnicodeError):
        return "foreign"
    if LINUX_MARKER not in actual.splitlines():
        return "foreign"
    return "enabled" if actual == expected else "stale"

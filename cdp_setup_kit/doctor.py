from dataclasses import asdict
from typing import Any, Dict, Optional

from . import chrome, config, endpoint, startup, startup_windows
from .errors import KitError
from .paths import Locations, path_module
from .profiles import get_profile
from .system import System


def diagnose(system: System, paths: Locations, data: Dict[str, Any], name: Optional[str] = None) -> Dict[str, Any]:
    report = {"locations": asdict(paths), "checks": []}
    checks = report["checks"]

    def row(level: str, check: str, message: str) -> None:
        checks.append({"level": level, "check": check, "message": message})

    supported = system.platform in {"linux", "windows", "macos"}
    row("PASS" if supported else "FAIL", "platform", system.platform if supported else "use a Windows, Linux or macOS desktop")
    try:
        config.validate(data, system)
    except KitError as exc:
        row("FAIL", "config", str(exc) + "; repair the config before continuing")
        return report
    row("PASS", "config", "profile names, ports and folders are valid and unique")
    for key in config.unknown_keys(data):
        row("WARN", "config", key + ": unknown key, ignored; remove it if unintended")
    binary = chrome.find_chrome(system, data)
    row("PASS" if binary else "FAIL", "Chrome found", binary or chrome.CHROME_NOT_FOUND_HINT)
    if binary:
        version, known = chrome.identity(system, binary)
        row("PASS" if known and version else "WARN", "Chrome identity and version", "Google Chrome " + version if known and version else "unknown version or browser identity; check that this is Google Chrome")
    row("INFO", "dedicated browser data", "Chrome debugging requires a separate data folder; keep using the dedicated folder recorded for each profile")
    if name:
        get_profile(data, name)
    if system.platform == "windows":
        report["locations"]["startup"] = "Task Scheduler (" + ", ".join(startup_windows.task_name(value) for value in ([name] if name else sorted(data["profiles"]))) + ")" if data["profiles"] else "Task Scheduler (no profiles)"
    for profile_name in ([name] if name else sorted(data["profiles"])):
        profile = data["profiles"][profile_name]
        folder = profile["profile_dir"]
        try:
            chrome.check_profile_dir(system, folder, data, profile_name)
        except KitError as exc:
            row("FAIL", profile_name + " folder", str(exc) + "; choose a dedicated folder")
            continue
        if not system.is_dir(path_module(system).dirname(folder)):
            row("FAIL", profile_name + " folder", "parent folder is missing; restore it or add a new profile")
        elif not system.exists(folder):
            row("INFO", profile_name + " folder", "not created yet; open the profile to create it")
        elif not system.is_dir(folder):
            row("FAIL", profile_name + " folder", "the path is not a folder; repair the profile path")
        elif system.platform in {"linux", "macos"} and system.file_mode(folder) & 0o044:
            row("WARN", profile_name + " folder", "group or others can read the folder; restrict access to your account")
        else:
            row("PASS", profile_name + " folder", "dedicated profile folder exists")
        health = endpoint.status(system, profile)
        state = health["status"]
        levels = {"stopped": "INFO", "running": "PASS", "running-unconfirmed": "WARN", "conflict": "FAIL"}
        fixes = {"stopped": "; run open " + profile_name, "running": "", "running-unconfirmed": "; endpoint answers, but the profile folder marker cannot be read; check folder permissions", "conflict": "; the listener is not a valid CDP endpoint or the profile folder marker differs; inspect the listener and dedicated folder before using this port"}
        row(levels[state], profile_name + " endpoint", ("running (endpoint answers)" if state == "running" else state) + fixes[state])
        if health.get("folder_marker") == "absent":
            row("INFO", profile_name + " folder marker", "Fixed-port/headless Chrome can omit DevToolsActivePort. The endpoint answers; this does not prove which profile it uses (README Status).")
        if state in {"running", "running-unconfirmed"}:
            for check in endpoint.exposure(system, profile["port"], health["ws_endpoint"]):
                row(check["level"], profile_name + " " + check["check"], check["message"])
        current = startup.status(system, paths, data, profile_name)
        entry_levels = {"disabled": "INFO", "enabled": "PASS", "stale": "WARN", "foreign": "FAIL", "unsupported": "INFO"}
        entry_fixes = {"disabled": "; preview startup enable " + profile_name, "enabled": "", "stale": "; run startup enable " + profile_name + " --apply", "foreign": "; inspect the existing entry manually; this tool will leave it alone", "unsupported": "; use a supported desktop"}
        row(entry_levels[current], profile_name + " startup", current + entry_fixes[current])
        if current in {"enabled", "stale"} and state == "stopped":
            row("WARN", profile_name + " sign-in", "The sign-in entry is on but the endpoint is not answering. Look at the window: if Chrome is asking a question (for example about remote debugging, or about restoring pages), answer it. If there is no window, run: cdp-setup-kit open " + profile_name)
    if system.platform == "linux":
        row("INFO", "desktop session", "desktop variables present" if system.env.get("DISPLAY") or system.env.get("WAYLAND_DISPLAY") else "no desktop variables; use open NAME --headless, or open from a desktop terminal")
    return report


def report_text(report: Dict[str, Any]) -> str:
    return "\n".join([key + ": " + value for key, value in report["locations"].items()] + ["{} {}: {}".format(row["level"], row["check"], row["message"]) for row in report["checks"]])

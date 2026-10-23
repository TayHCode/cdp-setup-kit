import re
import ipaddress
from typing import Any, Dict, List
from urllib.parse import urlsplit

from .constants import LOOPBACK
from .errors import KitError
from .paths import path_module
from .system import System
from .textout import clean_text


def http_endpoint(port: int) -> str:
    return "http://{}:{}".format(LOOPBACK, port)


def parse_http_endpoint(value: str):
    try:
        if any(ord(char) < 33 or ord(char) == 127 for char in value):
            raise ValueError()
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port if parts.port is not None else 80
        if (parts.scheme != "http" or not host or parts.username is not None
                or parts.password is not None or parts.path not in {"", "/"}
                or "?" in value or "#" in value or parts.netloc.endswith(":")
                or "%" in host or not 1 <= port <= 65535):
            raise ValueError()
        if ":" in host:
            ipaddress.IPv6Address(host)
            authority = "[" + host + "]"
        else:
            if not re.fullmatch(r"[a-zA-Z0-9.-]+", host):
                raise ValueError()
            authority = host
        return "http://{}:{}".format(authority, port), host, port
    except ValueError:
        raise KitError(2, "--endpoint must be an HTTP origin such as http://localhost:9333",
                       "paths, credentials, query strings, fragments and other schemes are not supported") from None


def status(system: System, profile: Dict[str, Any], check: bool = True) -> Dict[str, Any]:
    result = {"status": "not-checked", "browser": None, "ws_endpoint": None, "folder_marker": None}
    if not check:
        return result
    probe = system.cdp_version(profile["port"])
    if probe["kind"] != "valid":
        result["status"] = "stopped" if probe["kind"] == "refused" else "conflict"
        return result
    result.update(browser=clean_text(probe["data"]["Browser"]), ws_endpoint=probe["data"]["webSocketDebuggerUrl"])
    try:
        lines = system.read_text(path_module(system).join(profile["profile_dir"], "DevToolsActivePort")).splitlines()
    except FileNotFoundError:
        result.update(status="running", folder_marker="absent")
        return result
    except (OSError, UnicodeError):
        result.update(status="running-unconfirmed", folder_marker="unreadable")
        return result
    try:
        matches = len(lines) >= 2 and lines[0] == str(profile["port"]) and lines[1] == urlsplit(result["ws_endpoint"]).path
    except ValueError:
        matches = False
    result["folder_marker"] = "matched" if matches else "mismatch"
    result["status"] = "running" if matches else "conflict"
    return result


def looks_open(system: System, profile: Dict[str, Any]) -> bool:
    path = path_module(system)
    try:
        if system.platform == "windows":
            return system.exists(path.join(profile["profile_dir"], "lockfile"))
        if system.platform == "macos":
            # No /proc on macOS. Even a stale lock is reason to keep profile data.
            lock = path.join(profile["profile_dir"], "SingletonLock")
            return system.is_link(lock) or system.exists(lock)
        target = system.read_link(path.join(profile["profile_dir"], "SingletonLock"))
        match = re.search(r"-(\d+)$", target)
        return bool(match and system.exists("/proc/" + match.group(1)))
    except OSError:
        return False


def exposure(system: System, port: int, ws_endpoint: str) -> List[Dict[str, str]]:
    addresses = system.non_loopback_addresses()
    rows = []
    if not addresses:
        rows.append({"level": "INFO", "check": "exposure", "message": "not checked: no non-loopback addresses found"})
    elif any(system.tcp_connect(address, port, 0.3) for address in addresses):
        rows.append({"level": "WARN", "check": "exposure", "message": "port {} is reachable on a non-loopback address of this machine. Something (a port forward or proxy) is exposing it. Make sure that is intended and restricted to machines you trust.".format(port)})
    else:
        rows.append({"level": "PASS", "check": "exposure", "message": "no reachable non-loopback address found"})
    try:
        host = urlsplit(ws_endpoint).hostname
    except ValueError:
        host = None
    if host not in {LOOPBACK, "localhost"}:
        rows.append({"level": "WARN", "check": "WebSocket host", "message": "the debugging address is not loopback; inspect any forward or proxy"})
    return rows

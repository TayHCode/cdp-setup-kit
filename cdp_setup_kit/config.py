import json
import re
from typing import Any, Dict, List

from .constants import PORT_MAX, PORT_MIN
from .errors import KitError
from .paths import path_key, path_module
from .system import System


def validate_name(name: str) -> None:
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", name) or name.endswith("-"):
        raise KitError(3, "invalid profile name", "use lowercase letters, digits and interior hyphens; start with a letter")


def validate_port(port: int, code: int = 2) -> None:
    if type(port) is not int or not PORT_MIN <= port <= PORT_MAX:
        raise KitError(code, "port must be an integer from 1024 to 65535")


def validate(data: Dict[str, Any], system: System) -> None:
    if not isinstance(data, dict) or type(data.get("schema")) is not int:
        raise KitError(3, "invalid config schema")
    if data["schema"] > 1:
        raise KitError(3, "this config was written by a newer version")
    if data["schema"] != 1 or not isinstance(data.get("profiles"), dict) or not (data.get("chrome_path") is None or isinstance(data["chrome_path"], str)):
        raise KitError(3, "invalid config structure")
    from .share import validate_shares
    validate_shares(data)
    ports, folders = set(), set()
    path = path_module(system)
    for name, profile in data["profiles"].items():
        validate_name(name)
        if not isinstance(profile, dict):
            raise KitError(3, "invalid profile: " + name)
        validate_port(profile.get("port"), 3)
        folder = profile.get("profile_dir")
        if not isinstance(folder, str) or not path.isabs(folder) or type(profile.get("created_by_kit")) is not bool or not isinstance(profile.get("created"), str):
            raise KitError(3, "invalid profile fields: " + name)
        normalized = path_key(system, folder)
        if profile["port"] in ports or normalized in folders:
            raise KitError(3, "duplicate port or profile folder: " + name)
        ports.add(profile["port"])
        folders.add(normalized)


def load(system: System, path: str, check: bool = True) -> Dict[str, Any]:
    if not system.exists(path):
        return {"schema": 1, "chrome_path": None, "profiles": {}}
    try:
        data = json.loads(system.read_text(path))
    except (OSError, ValueError):
        raise KitError(3, "cannot read config JSON", "repair the config; it has not been overwritten") from None
    if isinstance(data, dict) and type(data.get("schema")) is int and data["schema"] > 1:
        raise KitError(3, "this config was written by a newer version")
    if check:
        validate(data, system)
    return data


def save(system: System, path: str, data: Dict[str, Any]) -> None:
    validate(data, system)
    if system.exists(path):
        load(system, path)
        system.write_text(path + ".bak", system.read_text(path))
    system.write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def unknown_keys(data: Dict[str, Any]) -> List[str]:
    result = sorted(set(data) - {"schema", "chrome_path", "profiles", "shares"})
    for name, profile in data["profiles"].items():
        result += [name + ":" + key for key in sorted(set(profile) - {"port", "profile_dir", "created_by_kit", "created"})]
    return result

from dataclasses import dataclass
import ntpath
import posixpath
from typing import Any, Optional

from .constants import APP_NAME
from .system import System


def path_module(system: System) -> Any:
    return ntpath if system.platform == "windows" else posixpath


def path_key(system: System, value: str) -> str:
    normalized = path_module(system).normcase(system.resolve_path(value))
    # Conservatively protect case variants on Macs with case-insensitive filesystems.
    return normalized.casefold() if system.platform == "macos" else normalized


@dataclass(frozen=True)
class Locations:
    config: str
    profiles: str
    state: str
    startup: str


def locations(system: System, kit_dir: Optional[str] = None) -> Locations:
    path = path_module(system)
    user = system.user_dir()
    env = system.env
    if system.platform == "windows":
        config_base = env.get("APPDATA") or path.join(user, "AppData", "Roaming")
        data_base = env.get("LOCALAPPDATA") or path.join(user, "AppData", "Local")
        config = path.join(config_base, APP_NAME, "config.json")
        profiles = path.join(data_base, APP_NAME, "profiles")
        state = path.join(data_base, APP_NAME, "state")
        startup = "Task Scheduler (cdp-setup-kit-NAME)"
    elif system.platform == "macos":
        base = path.join(user, "Library", "Application Support", APP_NAME)
        config = path.join(base, "config.json")
        profiles = path.join(base, "profiles")
        state = path.join(base, "state")
        startup = path.join(user, "Library", "LaunchAgents")
    else:
        config_base = env.get("XDG_CONFIG_HOME") or path.join(user, ".config")
        data_base = env.get("XDG_DATA_HOME") or path.join(user, ".local", "share")
        state_base = env.get("XDG_STATE_HOME") or path.join(user, ".local", "state")
        config = path.join(config_base, APP_NAME, "config.json")
        profiles = path.join(data_base, APP_NAME, "profiles")
        state = path.join(state_base, APP_NAME)
        startup = path.join(config_base, "autostart")
    override = kit_dir or env.get("CDP_SETUP_KIT_DIR")
    if override:
        root = system.resolve_path(override)
        config, profiles, state = (path.join(root, part) for part in ("config.json", "profiles", "state"))
    return Locations(config, profiles, state, startup)

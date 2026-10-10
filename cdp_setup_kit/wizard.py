import json
import contextlib
import io
from typing import Any, Dict, Optional

from . import chrome, config, connect, endpoint, ports, profiles
from .constants import SECURITY_NOTICE
from .errors import KitError
from .paths import Locations
from .system import System


def initialize(system: System, paths: Locations, data: Dict[str, Any], yes: bool = False, name: Optional[str] = None, port: Optional[int] = None, chrome_path: Optional[str] = None, no_open: bool = False, notice: bool = False, quiet: bool = False) -> None:
    if quiet and not yes:
        raise KitError(2, "--quiet requires --yes to accept the security notice without displaying it")
    if not yes and not system.interactive():
        raise KitError(2, "init needs an interactive terminal", "for SSH/non-interactive setup use init --yes --no-open --name NAME --port PORT, then open NAME (Linux: add --headless; Windows: use the interactive startup task)")
    existing = data["profiles"]
    if existing and name is None and not yes:
        name = system.ask("New profile name (empty leaves setup unchanged): ").strip()
    if (name in existing) or (existing and not name):
        print("already set up; nothing changed" + (": " + endpoint.http_endpoint(existing[name]["port"]) if name in existing else ""))
        if notice and not quiet:
            print(SECURITY_NOTICE)
        return
    binary = chrome.find_chrome(system, data, chrome_path)
    if not binary:
        raise KitError(5, "Google Chrome was not found", chrome.CHROME_NOT_FOUND_HINT)
    version, _ = chrome.identity(system, binary)
    if not yes:
        print("Chrome: " + binary + "\nVersion: " + (version or "unknown"))
        print(SECURITY_NOTICE)
    if not yes and system.ask("Continue? [y/N] ").strip().lower() not in {"y", "yes"}:
        print("No changes made.")
        return
    existing = data["profiles"]
    if existing and not yes:
        print("Existing profiles will not be changed:")
        for current, profile in sorted(existing.items()):
            print("  {}: {}".format(current, profile["port"]))
    if name is None:
        default = "" if existing else "main"
        name = default if yes else system.ask("New profile name [{}]: ".format(default)).strip() or default
    if not name:
        print("No profile added. Use connect NAME or preview startup enable NAME for an existing profile.")
        return
    staged = json.loads(json.dumps(data))
    new_profile = name not in existing
    if not new_profile:
        print("already set up; nothing changed: " + endpoint.http_endpoint(existing[name]["port"]))
        return
    else:
        if port is None:
            proposed, _ = ports.choose_port(system, data)
            answer = "" if yes else system.ask("Port [{}]: ".format(proposed)).strip()
            try:
                port = int(answer) if answer else proposed
            except ValueError:
                raise KitError(2, "port must be an integer from 1024 to 65535") from None
    should_open = not no_open and (yes or system.ask("Open the window now? [Y/n] ").strip().lower() not in {"n", "no"})
    if should_open:
        profiles.require_launch_session(system, name, port=port if new_profile else existing[name]["port"])
    details = io.StringIO()
    try:
        with contextlib.redirect_stdout(details):
            if new_profile:
                profiles.add(system, paths, staged, name, port, chrome_path=chrome_path, persist=False)
            profile = staged["profiles"][name]
            if should_open:
                profiles.open_profile(system, paths, staged, name)
    except Exception:
        if name in staged["profiles"]:
            print('Profile "' + name + '" was not recorded. Retained profile folder (may contain browser data): ' + staged["profiles"][name]["profile_dir"])
        raise
    if new_profile:
        config.save(system, paths.config, staged)
        data.update(staged)
    print('Profile "' + name + '" recorded; ' + ("Chrome is open" if should_open else "Chrome was not opened") + ": " + endpoint.http_endpoint(profile["port"]))
    if quiet:
        return
    if yes:
        print(SECURITY_NOTICE)
        print("Chrome: " + binary + "\nVersion: " + (version or "unknown"))
    print(details.getvalue(), end="")
    print('Recorded profile "{}".\n  port:         {}\n  profile data: {}'.format(name, profile["port"], profile["profile_dir"]))
    print("Profile data: " + profile["profile_dir"] + "\nEndpoint: " + endpoint.http_endpoint(profile["port"]))
    if should_open:
        print("Sign in to your accounts in that window yourself.")
    else:
        print("Profile recorded; Chrome was not opened.")
    print("Reopen: cdp-setup-kit open " + name + "\nPreview the sign-in entry: cdp-setup-kit startup enable " + name)
    print(connect.instructions(name, profile["port"]))

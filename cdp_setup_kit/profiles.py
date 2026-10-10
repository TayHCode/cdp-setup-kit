from typing import Any, Dict, Optional

from . import chrome, config, endpoint, ports
from .constants import APP_NAME
from .errors import KitError
from .paths import Locations, path_key, path_module
from .system import System


CONFLICT_RETRIES = 8


def desktop_warning(system: System) -> str:
    if system.platform == "linux":
        return "This machine has no desktop session: a visible window cannot open here; use headless mode / run at the desktop."
    return "This shell has no desktop session (it is a remote/SSH or service session): a visible window cannot open from here"


def get_profile(data: Dict[str, Any], name: str) -> Dict[str, Any]:
    if name not in data["profiles"]:
        raise KitError(3, "unknown profile: " + name, "run " + APP_NAME + " list")
    return data["profiles"][name]


def add(system: System, paths: Locations, data: Dict[str, Any], name: str, port: Optional[int] = None, profile_dir: Optional[str] = None, chrome_path: Optional[str] = None, persist: bool = True) -> None:
    config.validate_name(name)
    if name in data["profiles"]:
        existing = data["profiles"][name]
        if (port is not None and port != existing["port"]) or (profile_dir is not None and path_key(system, profile_dir) != path_key(system, existing["profile_dir"])):
            raise KitError(3, "profile already has different settings", "use " + APP_NAME + " set-port " + name + " NEWPORT; remove and add to change the folder")
        print("already set up, unchanged: " + endpoint.http_endpoint(existing["port"]))
        return
    folder = chrome.check_profile_dir(system, profile_dir or path_module(system).join(paths.profiles, name), data, name)
    selected, warning = ports.choose_port(system, data, port, name)
    binary = chrome.find_chrome(system, data, chrome_path)
    if chrome_path and not system.is_file(chrome_path):
        raise KitError(5, "Chrome path does not exist", "pass --chrome PATH for an installed Google Chrome")
    created = not system.exists(folder)
    if not created and not system.is_dir(folder):
        raise KitError(8, "profile path is not a folder")
    if created:
        system.make_profile_dir(folder)
    data["profiles"][name] = {"port": selected, "profile_dir": folder, "created_by_kit": created and profile_dir is None, "created": system.now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")}
    if chrome_path:
        data["chrome_path"] = system.resolve_path(chrome_path)
    if not persist:
        if warning:
            print(warning)
        return
    config.save(system, paths.config, data)
    print('Added profile "{}".\n  port:         {}\n  endpoint:     {}\n  profile data: {}\nNext: {} open {}'.format(name, selected, endpoint.http_endpoint(selected), folder, APP_NAME, name))
    if warning:
        print(warning)
    if not binary:
        print("warning: Google Chrome was not found; " + chrome.CHROME_NOT_FOUND_HINT)


def require_launch_session(system: System, name: str, headless: bool = False, port: Optional[int] = None) -> None:
    if headless:
        if system.platform != "linux":
            raise KitError(2, "--headless is supported on Linux only")
        return
    if system.has_desktop_session():
        return
    command = ["py" if system.platform == "windows" else "python3", "-m", "cdp_setup_kit"]
    kit_dir = system.env.get("CDP_SETUP_KIT_DIR")
    if kit_dir:
        command += ["--kit-dir", kit_dir]
    # Names are validated before this point; quote paths for the target shell.
    if system.platform == "windows":
        prefix = system.join_windows_args(command)
    else:
        prefix = " ".join("'" + "'\"'\"'".join(value.split("'")) + "'" for value in command)
    record = prefix + " init --yes --no-open --name " + name + (" --port " + str(port) if port is not None else " --port PORT")
    if system.platform == "windows":
        route = ("record without opening: " + record + "\n" + prefix + " startup enable " + name +
                 " --apply --force-no-desktop\n" + prefix + " startup run " + name + " --apply" +
                 "\nThis interactive task needs that account signed in to a desktop.")
    elif system.platform == "linux":
        route = "run at the desktop, or record with " + record + "; then " + prefix + " open " + name + " --headless"
    else:
        route = "sign in to the Mac graphical desktop with this account, then run " + prefix + " open " + name + " from its terminal"
    raise KitError(5, desktop_warning(system) + "; Chrome was not started", route)


def open_profile(system: System, paths: Locations, data: Dict[str, Any], name: str, wait: float = 20, no_wait: bool = False, headless: bool = False) -> None:
    profile = get_profile(data, name)
    require_launch_session(system, name, headless, profile["port"])
    binary = chrome.find_chrome(system, data)
    if not binary:
        raise KitError(5, "Google Chrome was not found", chrome.CHROME_NOT_FOUND_HINT)
    chrome.check_profile_dir(system, profile["profile_dir"], data, name)
    health = endpoint.status(system, profile)
    address = endpoint.http_endpoint(profile["port"])
    if health["status"] == "running":
        print("already open: " + address)
        return
    if health["status"] == "running-unconfirmed":
        print("something that looks like Chrome already answers on port {}; not starting another window\n{}".format(profile["port"], address))
        return
    if health["status"] == "conflict" or not system.can_bind(profile["port"]):
        raise KitError(4, "port is busy with " + (health["browser"] or "something that is not a Chrome debugging endpoint") + "; the tool will not stop it", "check for a live listener on port " + str(profile["port"]) + "; close only your own listener and retry open " + name + ". TIME-WAIT connections do not require changing ports.")
    if not system.is_dir(profile["profile_dir"]):
        system.make_profile_dir(profile["profile_dir"])
    try:
        argv = chrome.build_chrome_argv(binary, profile["profile_dir"], profile["port"])
        if headless:
            argv.append("--headless=new")
        process = system.spawn_detached(argv)
    except OSError:
        raise KitError(5, "Chrome could not start", "check the Chrome path and file permissions") from None
    if no_wait:
        print(("Headless Chrome" if headless else "Chrome") + " launch requested; endpoint not checked: " + address)
        return
    started = system.now_utc()
    conflicts = 0
    while True:
        health = endpoint.status(system, profile)
        if health["status"] in {"running", "running-unconfirmed"}:
            message = "Headless Chrome is ready; no visible window. Interactive sign-in requires a desktop." if headless else "The window is open. Sign in to your accounts there yourself."
            print(address + "\n" + health["browser"] + "\n" + message)
            return
        if health["status"] == "conflict":
            # Our own Chrome can answer before it rewrites a stale DevToolsActivePort; re-probe briefly.
            conflicts += 1
            if conflicts >= CONFLICT_RETRIES:
                raise KitError(4, "another endpoint answered during startup; the tool will not stop it")
        else:
            conflicts = 0
        if (system.now_utc() - started).total_seconds() >= wait:
            break
        system.sleep(min(0.25, wait - (system.now_utc() - started).total_seconds()))
    diagnosis = ""
    if process.poll() == 0 or endpoint.looks_open(system, profile):
        diagnosis = "This profile is already open in a Chrome that was started without the debugging port. Close every window of that profile, then run open again. "
    if headless:
        raise KitError(5, "the headless endpoint did not answer", "check Chrome executable permissions, shared-library dependencies and sandbox support; try --wait 60. Run Chrome as a regular user, not root.")
    raise KitError(5, "the endpoint did not answer", diagnosis + "Look at the window. If Chrome is asking a question, answer it. A managed-device policy may turn remote debugging off. Slow start: try --wait 60.")


def set_port(system: System, paths: Locations, data: Dict[str, Any], name: str, port: int, apply: bool = False) -> None:
    from . import startup
    profile = get_profile(data, name)
    selected, warning = ports.choose_port(system, data, port, name)
    if selected == profile["port"]:
        print('"{}" already uses port {}; unchanged.'.format(name, selected))
        return
    if name in data.get("shares", {}):
        raise KitError(8, "unshare this profile before changing its port")
    has_entry = startup.status(system, paths, data, name) not in {"disabled", "unsupported"}
    print(('Changing' if apply else 'PREVIEW: nothing has been changed. Would change') + ' port for "{}": {} -> {}'.format(name, profile["port"], selected))
    if warning:
        print(warning)
    if apply and selected != profile["port"]:
        profile["port"] = selected
        config.save(system, paths.config, data)
    print("Takes effect the next time the window is opened. Close the window, then run open.")
    if has_entry:
        print("The sign-in entry still has the old port. Update it with: " + APP_NAME + " startup enable " + name + " --apply")


def remove_profile(system: System, paths: Locations, data: Dict[str, Any], name: str, delete_data: bool = False, apply: bool = False) -> None:
    from . import startup
    profile = get_profile(data, name)
    folder = profile["profile_dir"]
    if name in data.get("shares", {}):
        raise KitError(8, "unshare this profile before removing it")
    if delete_data:
        path = path_module(system)
        if not profile["created_by_kit"] or system.is_link(folder) or path_key(system, path.dirname(system.resolve_path(folder))) != path_key(system, paths.profiles):
            raise KitError(8, "refused: data deletion needs a direct folder created by this kit")
        chrome.check_profile_dir(system, folder, data, name)
        if endpoint.status(system, profile)["status"] != "stopped" or endpoint.looks_open(system, profile) or not system.can_bind(profile["port"]):
            raise KitError(8, "close the window first")
    plan = startup.build_plan(system, paths, data, name, "disable")
    print(('Removing' if apply else 'PREVIEW: nothing has been changed. Would remove') + ' config entry "{}".'.format(name))
    print(("Delete profile data: " if delete_data else "Keep profile data: ") + folder)
    if startup.status(system, paths, data, name) == "disabled":
        print("No sign-in entry exists for this profile.")
    elif not apply:
        print(startup.preview(system, plan))
    if apply:
        startup.apply_plan(system, plan, quiet_absent=True)
        if delete_data and system.exists(folder):
            system.remove_tree(folder)
        del data["profiles"][name]
        config.save(system, paths.config, data)

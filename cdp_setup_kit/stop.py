"""Preview and gracefully close only a verified kit browser."""
from . import chrome, endpoint
from .errors import KitError
from .profiles import get_profile


def stop(system, data, name, apply=False):
    profile = get_profile(data, name)
    port = profile["port"]
    health = system.cdp_version(port)
    if health["kind"] == "refused" and system.can_bind(port):
        print(name + ": stopped (no endpoint answers).")
        return
    binary = chrome.find_chrome(system, data)
    chrome.check_profile_dir(system, profile["profile_dir"], data, name)
    if health["kind"] != "valid" or not binary or not system.listener_owns_profile(port, binary, profile["profile_dir"]):
        raise KitError(8, "refused: the listener at the recorded port could not be verified as this profile; nothing was closed", "close this profile from its desktop if needed; other profiles are left alone")
    if not apply:
        print('PREVIEW: nothing has been changed. Would ask Chrome for profile "' + name + '" to close through Browser.close at ' + endpoint.http_endpoint(port) + '.')
        print("Verified listener user-data-dir: " + profile["profile_dir"])
        print("This closes every window/tab in this dedicated profile. To do it: cdp-setup-kit stop " + name + " --apply")
        return
    error = None
    try:
        system.close_browser(health["data"]["webSocketDebuggerUrl"], port, binary, profile["profile_dir"])
    except (OSError, ValueError, TimeoutError) as exc:
        error = str(exc)
    # Browser.close can drop the connection before replying. Only a gone endpoint
    # and a free port confirm completion; never infer it from a successful send.
    started = system.now_utc()
    while True:
        probe = system.cdp_version(port)
        if probe["kind"] == "refused" and system.can_bind(port):
            print(name + ": stopped (endpoint no longer answers).")
            return
        if (system.now_utc() - started).total_seconds() >= 10:
            detail = "CDP still answers" if probe["kind"] == "valid" else "a listener remains at the recorded port"
            raise KitError(5, name + ": " + detail + "; stop was not confirmed" + ("; " + error if error else ""), "inspect only this profile at its desktop; the tool never forces a process to exit")
        system.sleep(0.25)

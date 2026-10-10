from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from . import chrome, startup_linux, startup_macos, startup_windows
from .constants import APP_NAME
from .errors import KitError
from .paths import Locations, path_module
from .profiles import get_profile
from .system import System


@dataclass
class StartupPlan:
    name: str
    action: str
    files: List[Tuple[str, str, str, int]] = field(default_factory=list)
    deletes: List[str] = field(default_factory=list)
    commands: List[List[str]] = field(default_factory=list)
    effect: str = ""
    unchanged: str = ""
    windows: bool = False
    expected: List[str] = field(default_factory=list)
    stale_command: List[str] = field(default_factory=list)
    macos_entry: str = ""
    entry_text: str = ""
    no_desktop: bool = False


def expected_argv(system: System, data: Dict[str, Any], name: str, required: bool = True) -> List[str]:
    profile = get_profile(data, name)
    binary = chrome.find_chrome(system, data)
    if not binary and required:
        raise KitError(5, "Google Chrome was not found", chrome.CHROME_NOT_FOUND_HINT)
    if required:
        chrome.check_profile_dir(system, profile["profile_dir"], data, name)
    if not binary:
        defaults = {"linux": "/opt/google/chrome/chrome", "macos": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "windows": path_module(system).join(system.env.get("ProgramFiles", r"C:\Program Files"), "Google", "Chrome", "Application", "chrome.exe")}
        binary = data.get("chrome_path") or system.env.get("CDP_SETUP_KIT_CHROME") or defaults[system.platform]
        chrome.safe_characters(system, binary)
    return chrome.build_chrome_argv(binary, profile["profile_dir"], profile["port"])


def status(system: System, paths: Locations, data: Dict[str, Any], name: str) -> str:
    if system.platform == "macos":
        target = startup_macos.entry_path(system, paths, name)
        if not (system.exists(target) or system.is_link(target)):
            return "disabled"
        try:
            expected = startup_macos.plist_text(name, expected_argv(system, data, name, False))
        except KitError:
            expected = ""
        return startup_macos.status(system, target, expected, name)
    if system.platform == "linux":
        target = startup_linux.entry_path(system, paths, name)
        if not (system.exists(target) or system.is_link(target)):
            return "disabled"
        try:
            expected = startup_linux.desktop_text(name, expected_argv(system, data, name, False))
        except KitError:
            expected = ""
        return startup_linux.status(system, target, expected)
    if system.platform == "windows":
        try:
            expected = expected_argv(system, data, name, False)
        except KitError:
            expected = None
        return startup_windows.status(system, name, expected)
    return "unsupported"


def build_plan(system: System, paths: Locations, data: Dict[str, Any], name: str, action: str, require_chrome: bool = True) -> StartupPlan:
    profile = get_profile(data, name)
    if action == "enable":
        chrome.check_profile_dir(system, profile["profile_dir"], data, name)
    if system.platform == "windows":
        plan = StartupPlan(name, action, windows=True)
        plan.effect = 'the "{}" Chrome window {} each time you sign in.'.format(name, "opens" if action == "enable" else "will no longer open")
        target = path_module(system).join(paths.state, "startup", APP_NAME + "-" + name + ".xml")
        if action == "enable":
            plan.expected = expected_argv(system, data, name, require_chrome)
            plan.files = [(target, startup_windows.task_xml(system, name, plan.expected), "utf_16", 0o600)]
            plan.commands = [startup_windows.query_argv(name), startup_windows.create_argv(name, target)]
            plan.stale_command = startup_windows.create_argv(name, target, True)
        else:
            plan.commands = [startup_windows.query_argv(name), startup_windows.delete_argv(name)]
            plan.deletes = [target]
        return plan
    if system.platform not in {"linux", "macos"}:
        raise KitError(9, "startup is not supported on this platform yet")
    backend = startup_macos if system.platform == "macos" else startup_linux
    target = backend.entry_path(system, paths, name)
    current = status(system, paths, data, name)
    if current == "foreign":
        raise KitError(6, "an entry with our name exists that the tool did not create; unchanged")
    plan = StartupPlan(name, action)
    plan.effect = 'the "{}" Chrome window {} each time you sign in.'.format(name, "opens" if action == "enable" else "will no longer open")
    if system.platform == "macos":
        plan.macos_entry = target
        plan.effect += " Takes effect at the next graphical sign-in; existing windows stay open."
    if action == "enable":
        argv = expected_argv(system, data, name, require_chrome)
        text = startup_macos.plist_text(name, argv) if system.platform == "macos" else startup_linux.desktop_text(name, argv)
        plan.entry_text = text
        if current == "enabled":
            plan.unchanged = "already enabled, unchanged"
        else:
            plan.files.append((target, text, "utf-8", 0o600 if system.platform == "macos" else 0o644))
    elif current == "disabled":
        plan.unchanged = "nothing to remove"
    else:
        plan.deletes.append(target)
    return plan


def preview(system: System, plan: StartupPlan) -> str:
    lines = ["PREVIEW: nothing has been changed."]
    if plan.unchanged:
        lines.append(plan.unchanged)
    if plan.windows:
        lines += ["Apply first queries the task and refuses foreign entries.",
                  "An entry already matching this plan is unchanged. A missing entry needs no removal."]
    for path, text, _, _ in plan.files:
        lines.extend(["Would write this file:", "  " + path, "---- file contents ----", text.rstrip("\n"), "---- end ----"])
    for path in plan.deletes:
        lines.extend(["Would delete this file:", "  " + path])
    for command in plan.commands:
        lines.extend(["Would then run this command:", "  " + system.join_windows_args(command)])
    if plan.stale_command:
        lines.extend(["For an existing marked entry that differs, use this command instead:", "  " + system.join_windows_args(plan.stale_command)])
    if not plan.unchanged:
        lines += [("Effect at a future graphical sign-in only: " if plan.no_desktop else "Effect: ") + plan.effect, "To do it:   {} startup {} {} --apply{}".format(APP_NAME, plan.action, plan.name, " --force-no-desktop" if plan.no_desktop else ""),
                  "To undo it: {} startup {} {} --apply".format(APP_NAME, "disable" if plan.action == "enable" else "enable", plan.name)]
    return "\n".join(lines)


def apply_plan(system: System, plan: StartupPlan, quiet_absent: bool = False) -> None:
    try:
        commands = plan.commands
        if plan.macos_entry:
            current = startup_macos.status(system, plan.macos_entry, plan.entry_text, plan.name)
            if current == "foreign":
                raise KitError(6, "an entry with our name exists that the tool did not create; unchanged")
            if (plan.action == "enable" and current == "enabled") or (plan.action == "disable" and current == "disabled"):
                if plan.action == "enable" or not quiet_absent:
                    print("already enabled, unchanged" if plan.action == "enable" else "nothing to remove")
                return
            if plan.unchanged:
                raise KitError(6, "the sign-in entry changed after this plan was built", "preview the startup command again")
        if plan.windows:
            code, out, _ = system.run(plan.commands[0])
            current = "disabled" if code else startup_windows.inspect_xml(out, plan.expected or None, system)
            if current == "foreign":
                raise KitError(6, "an entry with our name exists that the tool did not create; unchanged")
            if plan.action == "enable" and current == "enabled":
                print("already enabled, unchanged")
                return
            if plan.action == "disable" and current == "disabled":
                if not quiet_absent:
                    print("nothing to remove")
                return
            commands = [plan.stale_command if plan.action == "enable" and current == "stale" else plan.commands[1]]
        for path, text, encoding, mode in plan.files:
            system.write_text(path, text, encoding, mode)
        for command in commands:
            code, out, err = system.run(command)
            if code:
                raise KitError(6, out + err, "Windows refused to register the task for this account. You can run the same command once from an administrator terminal: " + system.join_windows_args(command) + ". See the manual alternative in docs/startup.md")
        for path in plan.deletes:
            if system.exists(path):
                system.remove_file(path)
    except OSError:
        hint = "check permissions for " + plan.macos_entry + "; see docs/startup.md" if plan.macos_entry else "check permissions for the displayed path"
        raise KitError(6, "could not change the sign-in entry", hint) from None
    if not (quiet_absent and plan.unchanged):
        print(plan.unchanged or plan.effect)


def change(system: System, paths: Locations, data: Dict[str, Any], name: str, action: str, apply: bool = False, force_no_desktop: bool = False) -> None:
    no_desktop = action == "enable" and not system.has_desktop_session()
    if no_desktop:
        from .profiles import desktop_warning
        warning = desktop_warning(system)
        print("WARNING: " + warning)
        if system.platform == "windows":
            print("Run at the desktop, or prepare the shipped interactive task with startup enable " + name + " --apply --force-no-desktop, then startup run " + name + " --apply; this account must be signed in at the desktop.")
        if apply and not force_no_desktop:
            route = ("run at the desktop, or use startup enable " + name + " --apply --force-no-desktop then startup run " + name + " --apply (the shipped interactive task requires this account signed in at the desktop)" if system.platform == "windows" else "run at the desktop, or add --force-no-desktop only to prepare an entry for a future graphical sign-in (Linux headless: open NAME --headless)")
            raise KitError(5, warning + "; sign-in entry was not changed", route)
    plan = build_plan(system, paths, data, name, action, require_chrome=apply)
    if action == "enable" and not apply and not chrome.find_chrome(system, data):
        print("Preview only: Chrome is not installed at the shown path. Install Chrome or use a new profile with add NAME --chrome PATH before applying.")
    if apply:
        apply_plan(system, plan)
    else:
        plan.no_desktop = no_desktop
        print(preview(system, plan))


def run_task(system: System, paths: Locations, data: Dict[str, Any], name: str, apply: bool = False) -> None:
    get_profile(data, name)
    if system.platform != "windows":
        raise KitError(9, "startup run is supported on Windows only; use open " + name)
    if status(system, paths, data, name) != "enabled":
        raise KitError(6, "refused: sign-in task is absent, foreign or differs from this profile", "preview startup enable " + name + " first")
    if not apply:
        print('PREVIEW: nothing has been changed. Would run the owned interactive task for "' + name + '". To do it: cdp-setup-kit startup run ' + name + ' --apply')
        return
    task = startup_windows.task_name(name)
    argv = expected_argv(system, data, name)
    def quote(value):
        return "'" + "''".join(value.split("'")) + "'"
    script = ("$ErrorActionPreference='Stop'; $task=Get-ScheduledTask -TaskName '" + task + "' -TaskPath '\\'; "
              "[xml]$xml=Export-ScheduledTask -InputObject $task; "
              "if ($xml.Task.RegistrationInfo.Source -ne " + quote(APP_NAME) + " -or $xml.Task.Actions.Exec.Command -ne " + quote(argv[0]) +
              " -or $xml.Task.Actions.Exec.Arguments -ne " + quote(system.join_windows_args(argv[1:])) + ") { throw 'Refused changed or foreign task' }; "
              "if ($task.State -eq 'Running') { 'already running' } else { Start-ScheduledTask -InputObject $task; 'start requested' }")
    code, output, error = system.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], timeout=30)
    if code:
        raise KitError(6, "interactive task could not start: " + (error or output).strip())
    print(name + ": " + output.strip() + ". The task uses IgnoreNew; stop " + name + " --apply before restarting it. Check connect " + name + " for endpoint readiness.")

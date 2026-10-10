import argparse
import json
import math
import sys
from typing import Optional, Sequence

from . import __version__
from .constants import APP_NAME
from .errors import KitError
from . import config, endpoint
from .paths import locations
from .system import RealSystem
from .textout import list_table


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog=APP_NAME)
    result.add_argument("--version", action="version", version=APP_NAME + " " + __version__)
    result.add_argument("--kit-dir")
    commands = result.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("init", help="guided profile setup")
    setup.add_argument("--yes", action="store_true")
    setup.add_argument("--name")
    setup.add_argument("--port", type=int)
    setup.add_argument("--chrome")
    setup.add_argument("--no-open", action="store_true")
    setup.add_argument("--notice", action="store_true", help="show the security notice again for an existing setup")
    setup.add_argument("--quiet", action="store_true", help="print only the result (use --yes for scripted consent)")
    add = commands.add_parser("add", help="record a profile")
    add.add_argument("name")
    add.add_argument("--port", type=int)
    add.add_argument("--profile-dir")
    add.add_argument("--chrome")
    launch = commands.add_parser("open", help="open a visible Chrome window")
    launch.add_argument("name")
    launch.add_argument("--wait", type=float, default=20)
    launch.add_argument("--no-wait", action="store_true")
    launch.add_argument("--headless", action="store_true", help="Linux: start Chrome without a visible window")
    stop = commands.add_parser("stop", help="preview gracefully closing this kit browser")
    stop.add_argument("name")
    stop.add_argument("--apply", action="store_true")
    listing = commands.add_parser("list", help="list endpoints")
    listing.add_argument("--json", action="store_true")
    listing.add_argument("--no-check", action="store_true")
    doctor = commands.add_parser("doctor", help="diagnose the setup")
    doctor.add_argument("name", nargs="?")
    doctor.add_argument("--json", action="store_true")
    startup = commands.add_parser("startup", help="preview sign-in entries")
    startup_commands = startup.add_subparsers(dest="action", required=True)
    for action in ["status", "enable", "disable"]:
        item = startup_commands.add_parser(action)
        item.add_argument("name", **({"nargs": "?"} if action == "status" else {}))
        item.add_argument("--json" if action == "status" else "--apply", action="store_true")
        if action == "enable":
            item.add_argument("--force-no-desktop", action="store_true", help="apply a visible sign-in entry despite no detected desktop session")
    start = startup_commands.add_parser("run", help="Windows: run the owned interactive sign-in task")
    start.add_argument("name")
    start.add_argument("--apply", action="store_true")
    attach = commands.add_parser("connect", help="show agent attach instructions")
    attach.add_argument("name")
    attach.add_argument("--client", choices=["all", "playwright", "playwright-python", "playwright-mcp", "chrome-devtools-mcp", "curl"], default="all")
    attach.add_argument("--ws", action="store_true")
    attach.add_argument("--json", action="store_true")
    port = commands.add_parser("set-port", help="preview a port change")
    port.add_argument("name")
    port.add_argument("port", type=int)
    port.add_argument("--apply", action="store_true")
    remove = commands.add_parser("remove", help="preview profile removal")
    remove.add_argument("name")
    remove.add_argument("--delete-data", action="store_true")
    remove.add_argument("--apply", action="store_true")
    sharing = commands.add_parser("share", help="preview explicit access for named peers")
    sharing.add_argument("name")
    sharing.add_argument("--to", action="append", required=True)
    sharing.add_argument("--address")
    sharing.add_argument("--apply", action="store_true")
    sharing.add_argument("--show-script", action="store_true", help="Windows: print the full saved PowerShell script")
    sharing.add_argument("--i-understand-this-exposes-signed-in-browsers", action="store_true")
    unsharing = commands.add_parser("unshare", help="preview removal of owned sharing entries")
    unsharing.add_argument("name")
    unsharing.add_argument("--apply", action="store_true")
    unsharing.add_argument("--show-script", action="store_true")
    commands.add_parser("share-status", help="inspect sharing and endpoint reachability")
    brief = commands.add_parser("agent-brief", help="print ready-to-paste agent instructions")
    brief.add_argument("name")
    brief.add_argument("--address")
    brief.add_argument("--write")
    return result


def main(argv: Optional[Sequence[str]] = None, system: object = None) -> int:
    tree = parser()
    try:
        args = tree.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    system = system or RealSystem(args.kit_dir)
    try:
        if system.platform not in {"windows", "linux", "macos"}:
            raise KitError(9, "This platform is not supported. Use a Windows, Linux or macOS desktop.")
        if args.command == "open" and (not math.isfinite(args.wait) or args.wait < 0):
            raise KitError(2, "--wait must be a finite nonnegative number")
        paths = locations(system, args.kit_dir)
        data = config.load(system, paths.config, check=args.command != "doctor")
        if args.command == "doctor":
            from .doctor import diagnose, report_text
            report = diagnose(system, paths, data, args.name)
            print(json.dumps(report) if args.json else report_text(report))
            return 7 if any(row["level"] == "FAIL" for row in report["checks"]) else 0
        from . import startup
        if args.command == "list":
            rows = []
            for name, profile in sorted(data["profiles"].items()):
                health = endpoint.status(system, profile, not args.no_check)
                rows.append({"name": name, "port": profile["port"], "profile_dir": profile["profile_dir"], "http_endpoint": endpoint.http_endpoint(profile["port"]), "status": health["status"], "browser": health["browser"], "startup": startup.status(system, paths, data, name)})
            print(json.dumps({"profiles": rows}) if args.json else list_table(rows) if rows else "No profiles yet. Run: " + ("py" if system.platform == "windows" else "python3") + " -m cdp_setup_kit" + (" --kit-dir " + system.join_windows_args([args.kit_dir]) if args.kit_dir else "") + " init")
            return 0
        from . import profiles
        if args.command in {"share", "unshare", "share-status", "agent-brief"}:
            from . import share
            if args.command == "share":
                share.change(system, paths, data, args.name, args.to, args.address, args.apply, args.i_understand_this_exposes_signed_in_browsers, args.show_script)
            elif args.command == "unshare":
                share.unshare(system, paths, data, args.name, args.apply, args.show_script)
            elif args.command == "share-status":
                share.status(system, paths, data)
            else:
                share.agent_brief(system, data, args.name, args.address, args.write)
        elif args.command == "add":
            profiles.add(system, paths, data, args.name, args.port, args.profile_dir, args.chrome)
        elif args.command == "init":
            from .wizard import initialize
            initialize(system, paths, data, args.yes, args.name, args.port, args.chrome, args.no_open, args.notice, args.quiet)
        elif args.command == "connect":
            from .connect import show
            show(system, data, args.name, args.client, args.ws, args.json)
        elif args.command == "open":
            profiles.open_profile(system, paths, data, args.name, args.wait, args.no_wait, args.headless)
        elif args.command == "stop":
            from .stop import stop
            stop(system, data, args.name, args.apply)
        elif args.command == "set-port":
            profiles.set_port(system, paths, data, args.name, args.port, args.apply)
        elif args.command == "remove":
            profiles.remove_profile(system, paths, data, args.name, args.delete_data, args.apply)
        elif args.command == "startup":
            if args.action == "run":
                startup.run_task(system, paths, data, args.name, args.apply)
            elif args.action == "status":
                if args.name:
                    profiles.get_profile(data, args.name)
                rows = [{"name": name, "startup": startup.status(system, paths, data, name)} for name in ([args.name] if args.name else sorted(data["profiles"]))]
                print(json.dumps({"profiles": rows}) if args.json else "\n".join(row["name"] + ": " + row["startup"] for row in rows) or "No profiles yet.")
            else:
                startup.change(system, paths, data, args.name, args.action, args.apply, getattr(args, "force_no_desktop", False))
        else:
            raise KitError(2, "unknown command")
        return 0
    except KitError as exc:
        print("error: " + str(exc), file=sys.stderr)
        if exc.hint:
            print("hint: " + exc.hint, file=sys.stderr)
        return exc.exit_code
    except TimeoutError:
        print("error: a system command timed out; nothing further was changed by this step", file=sys.stderr)
        return 1
    except EOFError:
        print("error: input ended before the question was answered; nothing was changed", file=sys.stderr)
        return 1
    except OSError as exc:
        print("error: file operation failed" + (": " + str(exc.filename) if exc.filename else "") + " (" + (exc.strerror or type(exc).__name__) + ")", file=sys.stderr)
        print("hint: check that the folder exists, is writable and has free space", file=sys.stderr)
        return 1
    except Exception:
        print("error: unexpected internal error", file=sys.stderr)
        return 1

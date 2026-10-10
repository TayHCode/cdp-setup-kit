import contextlib
import datetime
import http.server
import io
import json
import ntpath
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

from cdp_setup_kit.constants import LOOPBACK
from cdp_setup_kit.system import RealSystem

ROOT = Path(__file__).resolve().parent.parent


def git_read(args):
    if not shutil.which("git"):
        return None
    result = subprocess.run(["git", "-C", str(ROOT)] + args, capture_output=True,
                            text=True, check=False)
    return result.stdout if result.returncode == 0 else None


def repo_files():
    listing = git_read(["ls-files", "-co", "--exclude-standard", "-z"])
    if listing is not None:
        return sorted({ROOT / name for name in listing.split("\0") if name})
    ignored = {".git", ".venv", "build", "dist", "__pycache__", "scratch"}
    return sorted(p for p in ROOT.rglob("*") if p.is_file() and not any(
        part in ignored or part.endswith(".egg-info") for part in p.relative_to(ROOT).parts))


class KitTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kit-test-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.system = FakeSystem(self.folder)

    def run_cli(self, args):
        from cdp_setup_kit.cli import main
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(args, system=self.system)
        return code, out.getvalue(), err.getvalue()


def cdp_body():
    return {"Browser": "Chrome/141.0.7390.54", "Protocol-Version": "1.3",
            "webSocketDebuggerUrl": "ws://" + LOOPBACK + ":9222/devtools/browser/01234567-abcd-abcd-abcd-0123456789ab"}


class FakeSystem(RealSystem):
    def __init__(self, folder, platform="linux"):
        self.folder = Path(folder).resolve()
        self.platform = platform
        self.env = {"CDP_SETUP_KIT_DIR": str(self.folder / "kit"), "DISPLAY": ":test",
                    "XDG_CONFIG_HOME": str(self.folder / "config"), "XDG_DATA_HOME": str(self.folder / "data"),
                    "XDG_STATE_HOME": str(self.folder / "state"), "APPDATA": str(self.folder / "roaming"),
                    "LOCALAPPDATA": str(self.folder / "appdata"), "USERDOMAIN": "PC", "USERNAME": "operator", "SESSIONNAME": "Console"}
        self.calls = []
        self.runs = {}
        self.binaries = {}
        self.registry = {}
        self.probes = {}
        self.busy = set()
        self.addresses = []
        self.reachable = set()
        self.answers = []
        self.clock = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        self.is_interactive = True
        self.process_code = None
        self.spawn_hook = None
        self.owned_listeners = set()
        self.close_hook = None

    def _disk(self, path):
        value = str(path)
        if self.platform == "windows":
            value = value.replace("\\", "/").replace(":", "")
            result = self.folder / "windows" / value.lstrip("/")
        else:
            result = Path(value)
            if not result.is_absolute():
                result = self.folder / result
        if self.folder != result.resolve() and self.folder not in result.resolve().parents:
            raise AssertionError("fake disk path outside test folder")
        return result

    def windows_account(self):
        user = self.env.get("USERNAME", "")
        domain = self.env.get("USERDOMAIN", "")
        return domain + "\\" + user if domain and user else user

    def make_profile_dir(self, path):
        self.make_dir(path, 0o700)

    def user_dir(self):
        return str(self.folder / "user")

    def _guard(self, path=None):
        if path is not None:
            self._disk(path)

    def resolve_path(self, path):
        if self.platform == "windows":
            return ntpath.normpath(path)
        target = Path(path)
        if self.folder in target.parents or target == self.folder:
            return str(target.resolve())
        return os.path.abspath(path)

    def exists(self, path):
        if self.platform == "linux" and str(path).startswith("/proc/"):
            return str(path) in getattr(self, "process_paths", set())
        try:
            return self._disk(path).exists()
        except AssertionError:
            return False

    def is_file(self, path):
        try:
            return self._disk(path).is_file()
        except AssertionError:
            return False

    def is_dir(self, path):
        try:
            return self._disk(path).is_dir()
        except AssertionError:
            return False

    def is_link(self, path):
        return self._disk(path).is_symlink()

    def file_mode(self, path):
        return self._disk(path).stat().st_mode & 0o777

    def list_dir(self, path):
        return [p.name for p in self._disk(path).iterdir()]

    def read_text(self, path, encoding="utf-8"):
        self.calls.append(("read_text", str(path)))
        return self._disk(path).read_text(encoding=encoding)

    def read_link(self, path):
        return os.readlink(self._disk(path))

    def write_text(self, path, text, encoding="utf-8", mode=0o600):
        self.calls.append(("write_text", str(path), text, encoding, mode))
        target = self._disk(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding=encoding)
        target.chmod(mode)

    def make_dir(self, path, mode=0o700):
        self.calls.append(("make_dir", str(path), mode))
        self._disk(path).mkdir(parents=True, exist_ok=True, mode=mode)

    def remove_file(self, path):
        self.calls.append(("remove_file", str(path)))
        self._disk(path).unlink()

    def remove_tree(self, path):
        self.calls.append(("remove_tree", str(path)))
        shutil.rmtree(self._disk(path))

    def which(self, name):
        return self.binaries.get(name)

    def registry_value(self, root, key):
        return self.registry.get(root)

    def run(self, argv, timeout=5):
        self.calls.append(("run", list(argv)))
        for prefix, result in self.runs.items():
            if tuple(argv[:len(prefix)]) == prefix:
                return result
        return (1, "", "")

    def spawn_detached(self, argv):
        self.calls.append(("spawn", list(argv)))
        if self.spawn_hook:
            self.spawn_hook()
        return self

    def poll(self):
        return self.process_code

    def cdp_version(self, port, timeout=0.5):
        self.calls.append(("probe", port))
        results = self.probes.get(port, {"kind": "refused"})
        if isinstance(results, list):
            return results.pop(0) if len(results) > 1 else results[0]
        return results

    def can_bind(self, port):
        return port not in self.busy

    def listener_owns_profile(self, port, binary, folder):
        self.calls.append(("ownership", port, binary, folder))
        return (port, binary, folder) in self.owned_listeners

    def close_browser(self, url, port, binary, folder):
        self.calls.append(("close_browser", url, port, binary, folder))
        if self.close_hook:
            self.close_hook()

    def non_loopback_addresses(self):
        return self.addresses

    def tcp_connect(self, address, port, timeout):
        return (address, port) in self.reachable

    def ask(self, prompt):
        self.calls.append(("ask", prompt))
        return self.answers.pop(0)

    def interactive(self):
        return self.is_interactive

    def has_desktop_session(self):
        if self.platform == "linux":
            return bool(self.env.get("DISPLAY") or self.env.get("WAYLAND_DISPLAY"))
        if self.platform == "windows":
            return bool(self.env.get("SESSIONNAME")) and not any(self.env.get(key) for key in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"))
        return getattr(self, "desktop_session", True)

    def now_utc(self):
        return self.clock

    def sleep(self, seconds):
        self.clock += datetime.timedelta(seconds=seconds)


class FakeCdpServer:
    def __init__(self, mode="valid"):
        self.mode, self.requests = mode, []
        fixture = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                fixture.requests.append(self.path)
                if fixture.mode == "slow":
                    time.sleep(1.7)
                self.send_response(404 if self.path != "/json/version" else 500 if fixture.mode == "http_500" else 200)
                self.end_headers()
                payload = b"not json" if fixture.mode == "not_json" else json.dumps(cdp_body()).encode()
                try:
                    self.wfile.write(payload)
                except OSError:
                    pass

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer((LOOPBACK, 0), Handler)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

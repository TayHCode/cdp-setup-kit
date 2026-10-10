"""The only package boundary for operating-system effects."""
import datetime
import base64
import csv
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Mapping, Optional, Protocol, Tuple
from urllib.parse import urlsplit

from .constants import LOOPBACK
from .errors import RealActionForbidden


class System(Protocol):
    platform: str
    env: Mapping[str, str]

    def user_dir(self) -> str: ...
    def windows_account(self) -> str: ...
    def which(self, name: str) -> Optional[str]: ...
    def exists(self, path: str) -> bool: ...
    def is_file(self, path: str) -> bool: ...
    def is_dir(self, path: str) -> bool: ...
    def is_link(self, path: str) -> bool: ...
    def resolve_path(self, path: str) -> str: ...
    def file_mode(self, path: str) -> int: ...
    def list_dir(self, path: str) -> List[str]: ...
    def read_text(self, path: str, encoding: str = "utf-8") -> str: ...
    def read_link(self, path: str) -> str: ...
    def write_text(self, path: str, text: str, encoding: str = "utf-8", mode: int = 0o600) -> None: ...
    def make_dir(self, path: str, mode: int = 0o700) -> None: ...
    def make_profile_dir(self, path: str) -> None: ...
    def remove_file(self, path: str) -> None: ...
    def remove_tree(self, path: str) -> None: ...
    def registry_value(self, root: str, key: str) -> Optional[str]: ...
    def run(self, argv: List[str], timeout: float = 5) -> Tuple[int, str, str]: ...
    def spawn_detached(self, argv: List[str]) -> Any: ...
    def join_windows_args(self, args: List[str]) -> str: ...
    def can_bind(self, port: int) -> bool: ...
    def cdp_version(self, port: int, timeout: float = 0.5) -> Dict[str, Any]: ...
    def cdp_at(self, address: str, port: int, timeout: float = 0.5) -> Dict[str, Any]: ...
    def non_loopback_addresses(self) -> List[str]: ...
    def tcp_connect(self, address: str, port: int, timeout: float) -> bool: ...
    def now_utc(self) -> datetime.datetime: ...
    def sleep(self, seconds: float) -> None: ...
    def ask(self, prompt: str) -> str: ...
    def interactive(self) -> bool: ...
    def has_desktop_session(self) -> bool: ...
    def listener_owns_profile(self, port: int, binary: str, folder: str) -> bool: ...
    def close_browser(self, url: str, port: int, binary: str, folder: str) -> None: ...


class RealSystem:
    def __init__(self, kit_dir: Optional[str] = None) -> None:
        self.platform = "windows" if sys.platform == "win32" else "linux" if sys.platform.startswith("linux") else "macos" if sys.platform == "darwin" else "other"
        self.env = dict(os.environ)
        if kit_dir:
            self.env["CDP_SETUP_KIT_DIR"] = kit_dir

    def _guard(self, path: Optional[str] = None) -> None:
        if self.env.get("CDP_SETUP_KIT_FORBID_REAL") != "1":
            return
        root = self.env.get("CDP_SETUP_KIT_DIR")
        if path is not None and root:
            destination, base = Path(path).resolve(), Path(root).resolve()
            if destination == base or base in destination.parents:
                return
        raise RealActionForbidden()

    def user_dir(self) -> str:
        return os.path.expanduser("~")

    def windows_account(self) -> str:
        """Read the security identity; SSH environment names may not resolve."""
        code, output, _ = self.run(["whoami", "/user", "/fo", "csv", "/nh"])
        rows = list(csv.reader(output.strip().splitlines()))
        if code or len(rows) != 1 or len(rows[0]) != 2:
            raise OSError("Windows security identity is unavailable")
        sid = rows[0][1].strip()
        if not sid.startswith("S-1-") or any(part == "" or not part.isdigit() for part in sid.split("-")[1:]):
            raise OSError("Windows security identity is unavailable")
        return sid

    def which(self, name: str) -> Optional[str]:
        return shutil.which(name)

    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def is_file(self, path: str) -> bool:
        return Path(path).is_file()

    def is_dir(self, path: str) -> bool:
        return Path(path).is_dir()

    def is_link(self, path: str) -> bool:
        return Path(path).is_symlink()

    def resolve_path(self, path: str) -> str:
        return str(Path(path).expanduser().resolve())

    def file_mode(self, path: str) -> int:
        return stat.S_IMODE(Path(path).stat().st_mode)

    def list_dir(self, path: str) -> List[str]:
        return [p.name for p in Path(path).iterdir()]

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        return Path(path).read_text(encoding=encoding)

    def read_link(self, path: str) -> str:
        return os.readlink(path)

    def write_text(self, path: str, text: str, encoding: str = "utf-8", mode: int = 0o600) -> None:
        self._guard(path)
        destination = Path(path)
        self.make_dir(str(destination.parent))
        descriptor, temporary = tempfile.mkstemp(prefix=".kit-", dir=str(destination.parent))
        try:
            with os.fdopen(descriptor, "w", encoding=encoding, newline="") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, mode)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def make_dir(self, path: str, mode: int = 0o700) -> None:
        self._guard(path)
        Path(path).mkdir(parents=True, exist_ok=True, mode=mode)

    def make_profile_dir(self, path: str) -> None:
        self.make_dir(path, 0o700)
        if self.platform == "windows":
            # Elevated SSH shells can make Administrators the owner. The
            # least-privilege sign-in token still needs its own inherited grant.
            sid = self.windows_account()
            code, _, _ = self.run(["icacls", path, "/grant:r", "*" + sid + ":(OI)(CI)F"])
            if code:
                raise OSError("could not grant the current Windows user access to the new profile")

    def remove_file(self, path: str) -> None:
        self._guard(path)
        Path(path).unlink()

    def remove_tree(self, path: str) -> None:
        self._guard(path)

        def removed_during_walk(function: Any, failed_path: str, error: Any) -> None:
            # Older Python versions fail when Chrome's exiting helpers remove
            # a temporary child during the walk. Never suppress other errors.
            if isinstance(error[1], FileNotFoundError) and Path(failed_path) != Path(path):
                return
            raise error[1]

        shutil.rmtree(path, onerror=removed_during_walk)

    def registry_value(self, root: str, key: str) -> Optional[str]:
        if self.platform != "windows":
            return None
        import winreg
        try:
            with winreg.OpenKey(getattr(winreg, root), key) as handle:
                value = winreg.QueryValueEx(handle, None)[0]
                return value if isinstance(value, str) else None
        except OSError:
            return None

    def run(self, argv: List[str], timeout: float = 5) -> Tuple[int, str, str]:
        self._guard()
        try:
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                                    text=True, errors="replace", timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise TimeoutError("system command timed out") from None
        return result.returncode, result.stdout, result.stderr

    def spawn_detached(self, argv: List[str]) -> Any:
        self._guard()
        options = {"creationflags": getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)} if self.platform == "windows" else {"start_new_session": True}
        return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, **options)

    def join_windows_args(self, args: List[str]) -> str:
        return subprocess.list2cmdline(args)

    def can_bind(self, port: int) -> bool:
        # Availability means no accepting loopback listener. A bind test can
        # fail on TIME-WAIT even with SO_REUSEADDR when the old socket did not
        # use reuse. Chrome does the eventual bind; never stop a conflicting
        # process. Keep this interface name for the allocator/fake systems.
        return not self.tcp_connect(LOOPBACK, port, 0.3)

    def cdp_version(self, port: int, timeout: float = 0.5) -> Dict[str, Any]:
        return self.cdp_at(LOOPBACK, port, timeout)

    def cdp_at(self, address: str, port: int, timeout: float = 0.5) -> Dict[str, Any]:
        connection = http.client.HTTPConnection(address, port, timeout=timeout)
        connected = False
        try:
            connection.connect()
            connected = True
            connection.sock.settimeout(1.5)
            connection.request("GET", "/json/version")
            response = connection.getresponse()
            if response.status != 200:
                return {"kind": "not_cdp"}
            raw = response.read(65537)
            if len(raw) > 65536:
                return {"kind": "not_cdp"}
            data = json.loads(raw)
            if isinstance(data, dict) and all(isinstance(data.get(key), str) for key in ("Browser", "webSocketDebuggerUrl")):
                return {"kind": "valid", "data": data}
            return {"kind": "not_cdp"}
        except (OSError, ValueError, http.client.HTTPException):
            return {"kind": "not_cdp" if connected else "refused"}
        finally:
            connection.close()

    def non_loopback_addresses(self) -> List[str]:
        import ipaddress
        addresses = set()
        try:
            addresses.update(item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
        except OSError:
            pass
        # Host-name resolution can return loopback only. Include the existing
        # VPN's address without changing its configuration or probing ports.
        binary = self.which("tailscale")
        if binary:
            code, output, _ = self.run([binary, "ip", "-4"])
            if code == 0:
                addresses.update(output.split())
        result = []
        for value in addresses:
            try:
                ip = ipaddress.ip_address(value)
                if ip.version == 4 and not ip.is_loopback and not ip.is_unspecified:
                    result.append(str(ip))
            except ValueError:
                continue
        return sorted(result)

    def tcp_connect(self, address: str, port: int, timeout: float) -> bool:
        try:
            with socket.create_connection((address, port), timeout=timeout):
                return True
        except OSError:
            return False

    def now_utc(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def ask(self, prompt: str) -> str:
        return input(prompt)

    def interactive(self) -> bool:
        return sys.stdin.isatty()

    def has_desktop_session(self) -> bool:
        if self.platform == "linux":
            return bool(self.env.get("DISPLAY") or self.env.get("WAYLAND_DISPLAY"))
        if self.platform == "windows":
            if any(self.env.get(key) for key in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY")):
                return False
            script = "[Environment]::UserInteractive -and ([System.Diagnostics.Process]::GetProcessById(" + str(os.getpid()) + ").SessionId -gt 0)"
            code, output, _ = self.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script])
            return code == 0 and output.strip().lower() == "true"
        if self.platform == "macos":
            # An SSH shell can use an existing GUI login; Background managername
            # alone does not mean the account has no graphical session.
            code, _, _ = self.run(["launchctl", "print", "gui/" + str(os.getuid())])
            return code == 0
        return False

    def listener_owns_profile(self, port: int, binary: str, folder: str) -> bool:
        """Read only the recorded loopback listener's launch identity; fail closed."""
        from .chrome import build_chrome_argv
        expected = build_chrome_argv(binary, folder, port)
        try:
            if self.platform == "linux":
                inodes = set()
                for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
                    fields = line.split()
                    if fields[1] == "0100007F:{:04X}".format(port) and fields[3] == "0A":
                        inodes.add(fields[9])
                if not inodes:
                    return False
                owners = []
                for process in Path("/proc").iterdir():
                    if not process.name.isdigit():
                        continue
                    try:
                        if any(os.readlink(fd) == "socket:[" + inode + "]" for fd in (process / "fd").iterdir() for inode in inodes):
                            owners.append(process)
                    except OSError:
                        continue
                if len(owners) != 1:
                    return False
                process = owners[0]
                argv = [os.fsdecode(value) for value in (process / "cmdline").read_bytes().split(b"\0") if value]
                executables = {self.resolve_path(binary)}
                if Path(binary).name in {"google-chrome", "google-chrome-stable"}:
                    executables.add(self.resolve_path(str(Path(binary).with_name("chrome"))))
                executable = self.resolve_path(str(process / "exe"))
                if executable not in executables:
                    return False
                if len(argv) == 1:
                    # Chrome can rewrite argv as one display title in /proc.
                    # Match the known contiguous flags, including paths with spaces.
                    command = argv[0]
                    flags = " ".join(expected[1:])
                    return (command.startswith(executable + " ")
                            and " " + flags + " " in " " + command + " "
                            and command.count("--user-data-dir") == 1 and command.count("--remote-debugging-port") == 1)
                return (argv.count(expected[1]) == 1
                        and [arg for arg in argv if arg.startswith("--user-data-dir")] == [expected[1]]
                        and [arg for arg in argv if arg.startswith("--remote-debugging-port")] == [expected[2]]
                        and expected[3] in argv)
            if self.platform == "windows":
                script = ("$ErrorActionPreference='Stop'; $owners=@(Get-NetTCPConnection -State Listen -LocalAddress '" + LOOPBACK + "' -LocalPort " + str(port) +
                          " | Select-Object -ExpandProperty OwningProcess -Unique); if ($owners.Count -ne 1) { exit 1 }; "
                          "Get-CimInstance Win32_Process -Filter ('ProcessId=' + $owners[0]) | Select-Object ExecutablePath,CommandLine | ConvertTo-Json -Compress")
                code, output, _ = self.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], timeout=30)
                if code:
                    return False
                process = json.loads(output)
                import ntpath
                if ntpath.normcase(process["ExecutablePath"]) != ntpath.normcase(binary):
                    return False
                command = process["CommandLine"]
                # These contiguous flags are produced by the kit, including Windows quoting.
                flags = self.join_windows_args(expected[1:4])
                return (" " + flags.lower() + " " in " " + command.lower() + " "
                        and command.count("--user-data-dir") == 1 and command.count("--remote-debugging-port") == 1)
            if self.platform == "macos":
                code, output, _ = self.run(["/usr/sbin/lsof", "-nP", "-a", "-iTCP@" + LOOPBACK + ":" + str(port), "-sTCP:LISTEN", "-t"])
                owners = set(output.split())
                if code or len(owners) != 1 or not all(owner.isdigit() for owner in owners):
                    return False
                code, command, _ = self.run(["ps", "-ww", "-p", owners.pop(), "-o", "args="])
                flags = " ".join(expected[1:4])
                return (code == 0 and command.strip().startswith(binary + " ")
                        and " " + flags + " " in " " + command.strip() + " "
                        and command.count("--user-data-dir") == 1 and command.count("--remote-debugging-port") == 1)
        except (OSError, ValueError, KeyError, TypeError, TimeoutError):
            return False
        return False

    def close_browser(self, url: str, port: int, binary: str, folder: str) -> None:
        """One bounded RFC 6455 handshake and masked Browser.close frame, no tab access."""
        self._guard()
        if any(ord(char) < 33 or ord(char) == 127 for char in url):
            raise ValueError("refused unsafe debugging WebSocket URL")
        parts = urlsplit(url)
        if (parts.scheme != "ws" or parts.hostname not in {LOOPBACK, "localhost"} or parts.port != port
                or parts.username or parts.password or parts.query or parts.fragment
                or not parts.path.startswith("/devtools/browser/")
                or not parts.path.removeprefix("/devtools/browser/").replace("-", "").isalnum()
                or not parts.path.isascii()):
            raise ValueError("refused: debugging WebSocket must be on the recorded loopback port")
        with socket.create_connection((LOOPBACK, port), timeout=5) as connection:
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            connection.sendall(("GET " + parts.path + " HTTP/1.1\r\nHost: " + LOOPBACK + ":" + str(port) +
                                "\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: " + key +
                                "\r\nSec-WebSocket-Version: 13\r\n\r\n").encode("ascii"))
            headers = bytearray()
            deadline = time.monotonic() + 5
            while not headers.endswith(b"\r\n\r\n"):
                connection.settimeout(max(0.01, deadline - time.monotonic()))
                chunk = connection.recv(1)
                if not chunk or len(headers) >= 8192 or time.monotonic() >= deadline:
                    raise ValueError("debugging WebSocket handshake failed")
                headers.extend(chunk)
            lines = headers.decode("ascii").split("\r\n")
            fields = dict(line.split(":", 1) for line in lines[1:] if ":" in line)
            fields = {name.lower(): value.strip() for name, value in fields.items()}
            guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
            accept = base64.b64encode(hashlib.sha1((key + guid).encode("ascii")).digest()).decode("ascii")
            if (lines[0].split()[:2] != ["HTTP/1.1", "101"] or fields.get("sec-websocket-accept") != accept
                    or fields.get("upgrade", "").lower() != "websocket"
                    or "upgrade" not in [value.strip() for value in fields.get("connection", "").lower().split(",")]):
                raise ValueError("debugging WebSocket handshake failed")
            # Verify after connecting, on this same socket, before the sole mutating command.
            if not self.listener_owns_profile(port, binary, folder):
                raise ValueError("refused: listener ownership changed or could not be verified")
            connection.settimeout(5)
            payload = b'{"id":1,"method":"Browser.close"}'
            mask = os.urandom(4)
            connection.sendall(bytes([0x81, 0x80 | len(payload)]) + mask +
                               bytes(value ^ mask[index % 4] for index, value in enumerate(payload)))

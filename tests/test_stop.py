import base64
import hashlib
import json
from unittest import mock

from cdp_setup_kit import chrome, config
from cdp_setup_kit.constants import LOOPBACK
from cdp_setup_kit.paths import locations
from cdp_setup_kit.system import RealSystem
from tests import support


class StopTests(support.KitTestCase):
    def setUp(self):
        super().setUp()
        self.binary = str(self.folder / "chrome")
        self.system.write_text(self.binary, "")
        self.run_cli(["add", "work", "--port", "9530", "--chrome", self.binary])
        self.profile = config.load(self.system, locations(self.system).config)["profiles"]["work"]
        body = support.cdp_body()
        body["webSocketDebuggerUrl"] = "ws://" + LOOPBACK + ":9530/devtools/browser/test-browser"
        self.system.probes[9530] = {"kind": "valid", "data": body}
        self.system.owned_listeners.add((9530, self.binary, self.profile["profile_dir"]))
        self.system.calls.clear()

    def test_preview_and_confirmed_close_preserve_records(self):
        before = self.system.read_text(locations(self.system).config)
        code, out, err = self.run_cli(["stop", "work"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn('profile "work"', out)
        self.assertIn("Browser.close", out)
        self.assertFalse(any(call[0] == "close_browser" for call in self.system.calls))
        self.system.close_hook = lambda: self.system.probes.update({9530: {"kind": "refused"}})
        code, out, err = self.run_cli(["stop", "work", "--apply"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("stopped (endpoint no longer answers)", out)
        self.assertEqual(self.system.read_text(locations(self.system).config), before)
        self.assertTrue(self.system.is_dir(self.profile["profile_dir"]))

    def test_foreign_or_unverifiable_endpoint_never_closed(self):
        self.system.owned_listeners.clear()
        for apply in ([], ["--apply"]):
            self.assertEqual(self.run_cli(["stop", "work"] + apply)[0], 8)
        self.system.probes[9530] = {"kind": "not_cdp"}
        self.assertEqual(self.run_cli(["stop", "work", "--apply"])[0], 8)
        self.assertFalse(any(call[0] == "close_browser" for call in self.system.calls))

    def test_incomplete_close_reports_remaining_endpoint(self):
        code, out, err = self.run_cli(["stop", "work", "--apply"])
        self.assertEqual(code, 5)
        self.assertNotIn("stopped", out)
        self.assertIn("CDP still answers", err)
        self.assertIn("stop was not confirmed", err)
        self.assertEqual(sum(call[0] == "close_browser" for call in self.system.calls), 1)

    def test_dropped_connection_only_succeeds_if_endpoint_disappears(self):
        def close():
            self.system.probes[9530] = {"kind": "refused"}
            raise OSError("connection ended")
        self.system.close_hook = close
        self.assertEqual(self.run_cli(["stop", "work", "--apply"])[0], 0)
        self.system.busy.add(9530)
        code, out, err = self.run_cli(["stop", "work", "--apply"])
        self.assertEqual(code, 8)
        self.assertNotIn("stopped", out)

    def test_already_stopped_and_unknown_profile(self):
        self.system.probes[9530] = {"kind": "refused"}
        self.assertIn("stopped", self.run_cli(["stop", "work", "--apply"])[1])
        self.assertEqual(self.run_cli(["stop", "missing"])[0], 3)
        self.assertFalse(any(call[0] == "close_browser" for call in self.system.calls))

    def test_dropped_connection_waits_for_later_shutdown(self):
        answering = self.system.probes[9530]
        def close():
            self.system.probes[9530] = [answering, {"kind": "refused"}]
            raise OSError("connection ended before shutdown")
        self.system.close_hook = close
        code, out, err = self.run_cli(["stop", "work", "--apply"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("stopped (endpoint no longer answers)", out)


class SocketFixture:
    def __init__(self, bad=False):
        self.bad = bad
        self.frames = []
        self.response = b""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def settimeout(self, timeout):
        pass

    def sendall(self, data):
        self.frames.append(data)
        if data.startswith(b"GET "):
            headers = dict(line.split(b": ", 1) for line in data.split(b"\r\n")[1:] if b": " in line)
            challenge = headers[b"Sec-WebSocket-Key"]
            accept = base64.b64encode(hashlib.sha1(challenge + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
            self.response = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + (b"bad" if self.bad else accept) + b"\r\n\r\n"

    def recv(self, size):
        part, self.response = self.response[:size], self.response[size:]
        return part


class TransportTests(support.KitTestCase):
    def test_masked_browser_close_and_ownership_recheck(self):
        system = RealSystem()
        url = "ws://" + LOOPBACK + ":9530/devtools/browser/test-browser"
        for owned, bad in [(True, False), (False, False), (True, True)]:
            fixture = SocketFixture(bad)
            with mock.patch.object(system, "_guard"), mock.patch.object(system, "listener_owns_profile", return_value=owned), mock.patch("socket.create_connection", return_value=fixture):
                if not owned or bad:
                    with self.assertRaises(ValueError):
                        system.close_browser(url, 9530, "/test/chrome", "/test/profile")
                    self.assertEqual(len(fixture.frames), 1)
                else:
                    system.close_browser(url, 9530, "/test/chrome", "/test/profile")
                    frame = fixture.frames[1]
                    self.assertEqual(frame[:2], bytes([0x81, 0x80 | (len(frame) - 6)]))
                    mask = frame[2:6]
                    payload = bytes(value ^ mask[index % 4] for index, value in enumerate(frame[6:]))
                    self.assertEqual(json.loads(payload), {"id": 1, "method": "Browser.close"})

    def test_untrusted_websocket_never_connected(self):
        system = RealSystem()
        urls = ["ws://HOST:9530/devtools/browser/test", "ws://localhost:9531/devtools/browser/test", "ws://localhost:9530/devtools/page/test", "ws://localhost:9530/devtools/browser/test?x=1", "ws://localhost:9530/devtools/browser/test\r\n"]
        for url in urls:
            with mock.patch.object(system, "_guard"), mock.patch("socket.create_connection") as connect:
                with self.assertRaises(ValueError):
                    system.close_browser(url, 9530, "/test/chrome", "/test/profile")
                connect.assert_not_called()

    def test_windows_and_mac_process_identity_matches_only_kit_flags(self):
        system = RealSystem()
        for platform, binary, folder in [("windows", r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\kit data\profiles\work"), ("macos", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/test/kit data/profiles/work")]:
            system.platform = platform
            args = chrome.build_chrome_argv(binary, folder, 9530)
            command = system.join_windows_args(args) if platform == "windows" else " ".join(args)
            for line, matches in [(command, True), (command.replace(folder, folder + "-other"), False), (command + " --user-data-dir=other", False), (command.replace("9530", "9531"), False)]:
                results = [(0, json.dumps({"ExecutablePath": binary, "CommandLine": line}), "")] if platform == "windows" else [(0, "123\n", ""), (0, line, "")]
                with mock.patch.object(system, "run", side_effect=results):
                    self.assertEqual(system.listener_owns_profile(9530, binary, folder), matches)

    def test_linux_listener_ownership_uses_socket_inode_and_exact_argv(self):
        from pathlib import Path
        system = RealSystem()
        system.platform = "linux"
        proc = self.folder / "proc"
        (proc / "net").mkdir(parents=True)
        (proc / "net" / "tcp").write_text("header\n0: 0100007F:253A 00000000:0000 0A 0 0 0 0 0 800\n")
        process = proc / "123"
        (process / "fd").mkdir(parents=True)
        (process / "fd" / "7").symlink_to("socket:[800]")
        binary = self.folder / "chrome"
        binary.write_text("")
        (process / "exe").symlink_to(binary)
        folder = str(self.folder / "profile")
        args = chrome.build_chrome_argv(str(binary), folder, 9530)
        def mapped(value):
            return proc / str(value)[6:] if str(value).startswith("/proc/") else proc if str(value) == "/proc" else Path(value)
        for argv, expected in [(args, True), ([" ".join(args)], True), ([" ".join(args) + " --user-data-dir=other"], False), (args + ["--user-data-dir=other"], False), (chrome.build_chrome_argv(str(binary), folder + "-other", 9530), False)]:
            (process / "cmdline").write_bytes(b"\0".join(value.encode() for value in argv))
            with mock.patch("cdp_setup_kit.system.Path", side_effect=mapped):
                self.assertEqual(system.listener_owns_profile(9530, str(binary), folder), expected)

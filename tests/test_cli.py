from tests import support
import json
import os
import socket
import subprocess
import sys
from unittest import mock

from cdp_setup_kit import config
from cdp_setup_kit.errors import KitError
from cdp_setup_kit.constants import LOOPBACK
from cdp_setup_kit.paths import locations
from cdp_setup_kit.textout import list_table


class CliTests(support.KitTestCase):
    def test_version(self):
        self.assertEqual(self.run_cli(["--version"]), (0, "cdp-setup-kit 0.2.0\n", ""))

    def test_help(self):
        code, out, err = self.run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("usage:", out)
        self.assertEqual(err, "")

    def test_command_help(self):
        commands = ["init", "add", "open", "list", "doctor", "startup", "connect", "set-port", "remove"]
        for command in commands:
            self.assertEqual(self.run_cli([command, "--help"])[0], 0)
        for action in ["status", "enable", "disable"]:
            self.assertEqual(self.run_cli(["startup", action, "--help"])[0], 0)

    def test_platform_rejection(self):
        self.system.platform = "other"
        for command in [["init"], ["add", "work"], ["open", "work"], ["list"], ["doctor"], ["startup", "status"], ["connect", "work"], ["set-port", "work", "9223"], ["remove", "work"]]:
            self.assertEqual(self.run_cli(command)[0], 9)
        self.assertEqual(self.run_cli(["--version"])[0], 0)

    def test_error_mapping(self):
        for code in range(2, 10):
            with mock.patch("cdp_setup_kit.config.load", side_effect=KitError(code, "message", "next step")):
                result, _, err = self.run_cli(["list"])
                self.assertEqual(result, code)
                self.assertEqual(err, "error: message\nhint: next step\n")
        with mock.patch("cdp_setup_kit.config.load", side_effect=RuntimeError()):
            self.assertEqual(self.run_cli(["list"])[0], 1)

    def test_list_empty(self):
        self.assertIn("No profiles", self.run_cli(["list"])[1])
        self.assertEqual(json.loads(self.run_cli(["list", "--json"])[1]), {"profiles": []})

    def test_list_json_no_check(self):
        paths = locations(self.system)
        data = config.load(self.system, paths.config)
        data["profiles"]["work"] = {"port": 9222, "profile_dir": str(self.folder / "work"), "created": "2026-01-01T00:00:00Z", "created_by_kit": True}
        config.save(self.system, paths.config, data)
        self.system.calls.clear()
        code, out, _ = self.run_cli(["list", "--json", "--no-check"])
        self.assertEqual(code, 0)
        row = json.loads(out)["profiles"][0]
        self.assertEqual(set(row), {"name", "port", "profile_dir", "http_endpoint", "status", "browser", "startup"})
        self.assertEqual(row["status"], "not-checked")
        self.assertFalse(any(call[0] == "probe" for call in self.system.calls))

    def test_table_golden(self):
        from cdp_setup_kit.endpoint import http_endpoint
        rows = [{"name": "shop", "port": 9223, "http_endpoint": http_endpoint(9223), "status": "stopped", "startup": "disabled", "browser": None},
                {"name": "work", "port": 9222, "http_endpoint": http_endpoint(9222), "status": "running", "startup": "enabled", "browser": "Chrome/141.0.7390.54"}]
        self.assertEqual(list_table(rows) + "\n", (support.ROOT / "tests/golden/list-table.txt").read_text())

    def test_guarded_subprocess_walk(self):
        binary = self.folder / "chrome-placeholder"
        binary.write_text("")
        env = {"CDP_SETUP_KIT_FORBID_REAL": "1", "CDP_SETUP_KIT_DIR": str(self.folder / "kit"),
               "CDP_SETUP_KIT_CHROME": str(binary), "XDG_CONFIG_HOME": str(self.folder / "config"),
               "DISPLAY": ":test"}
        with socket.socket() as listener:
            listener.bind((LOOPBACK, 0))
            port = listener.getsockname()[1]
        commands = [["add", "work", "--port", str(port)], ["add", "work"],
                    ["list", "--json", "--no-check"], ["startup", "enable", "work"], ["remove", "work"]]
        for args in commands:
            result = subprocess.run([sys.executable, "-m", "cdp_setup_kit"] + args, cwd=str(support.ROOT),
                                    env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            if args[0] == "list":
                self.assertEqual(json.loads(result.stdout)["profiles"][0]["status"], "not-checked")
        result = subprocess.run([sys.executable, "-m", "cdp_setup_kit", "open", "work", "--no-wait"], cwd=str(support.ROOT),
                                env=env, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 6)
        self.assertIn("refused: test mode", result.stderr)
        self.assertFalse((self.folder / "config" / "autostart").exists())

    def test_invalid_wait_and_unknown_commands(self):
        for value in ["-1", "nan", "inf"]:
            self.assertEqual(self.run_cli(["open", "work", "--wait", value])[0], 2)
        self.assertEqual(self.run_cli(["unknown"])[0], 2)


class FailureMessageTests(support.KitTestCase):
    def test_write_failure_names_the_path(self):
        for code, reason in [(13, "Permission denied"), (28, "No space left on device"), (30, "Read-only file system")]:
            target = str(self.folder / "kit" / "config.json")
            with self.subTest(reason=reason), mock.patch.object(self.system, "write_text", side_effect=OSError(code, reason, target)):
                status, _, err = self.run_cli(["add", "work", "--port", "41601"])
            self.assertEqual(status, 1)
            self.assertIn(target, err)
            self.assertIn(reason, err)
            self.assertNotIn("unexpected internal error", err)

    def test_end_of_input_and_timeout(self):
        binary = str(self.folder / "chrome")
        self.system.write_text(binary, "")
        with mock.patch.object(self.system, "ask", side_effect=EOFError()):
            status, _, err = self.run_cli(["init", "--chrome", binary])
        self.assertEqual(status, 1)
        self.assertIn("input ended", err)
        with mock.patch.object(self.system, "can_bind", side_effect=TimeoutError()):
            status, _, err = self.run_cli(["add", "work"])
        self.assertEqual(status, 1)
        self.assertIn("timed out", err)


class HostileTextTests(support.KitTestCase):
    HOSTILE = "Chrome/1\x1b]0;owned\x07\x1b[2J‮\x9b31m" + "A" * 400

    def test_terminal_output_has_no_control_characters(self):
        binary = str(self.folder / "chrome")
        self.system.write_text(binary, "")
        self.run_cli(["add", "work", "--chrome", binary])
        body = dict(support.cdp_body(), Browser=self.HOSTILE, webSocketDebuggerUrl="ws://" + LOOPBACK + ":9222/devtools/browser/x\x1b[2J")
        self.system.probes[9222] = {"kind": "valid", "data": body}
        for args in (["list"], ["open", "work"], ["connect", "work", "--ws"]):
            with self.subTest(args=args):
                _, out, err = self.run_cli(args)
                for char in out + err:
                    self.assertTrue(char in "\n" or (char.isprintable()), repr(char))
        self.assertLess(max(len(line) for line in self.run_cli(["list"])[1].splitlines()), 400)

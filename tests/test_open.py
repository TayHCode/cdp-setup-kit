from tests import support
from urllib.parse import urlsplit
from pathlib import Path
from unittest import mock

from cdp_setup_kit import chrome, config, profiles
from cdp_setup_kit.paths import locations
from cdp_setup_kit.errors import KitError
import shlex

class OpenFixture:
    def setUp(self):
        super().setUp()
        self.binary = str(self.folder / "chrome")
        self.system.write_text(self.binary, "")
        self.run_cli(["add", "work", "--chrome", self.binary])
        self.paths = locations(self.system)
        self.data = config.load(self.system, self.paths.config)
        self.profile = self.data["profiles"]["work"]
        self.system.calls.clear()

    def active(self):
        self.system.write_text(self.profile["profile_dir"] + "/DevToolsActivePort", "9222\n" + urlsplit(support.cdp_body()["webSocketDebuggerUrl"]).path)

class OpenTests(OpenFixture, support.KitTestCase):
    def test_already_running_and_unconfirmed(self):
        self.system.probes[9222] = {"kind": "valid", "data": support.cdp_body()}
        self.assertIn("already open", self.run_cli(["open", "work"])[1])
        self.active()
        self.assertIn("already open", self.run_cli(["open", "work"])[1])
        self.assertFalse(any(call[0] in {"spawn", "run"} for call in self.system.calls))

    def test_conflicts_do_not_spawn(self):
        for probe in [{"kind": "not_cdp"}, {"kind": "valid", "data": support.cdp_body()}]:
            self.system.probes[9222] = probe
            self.system.write_text(self.profile["profile_dir"] + "/DevToolsActivePort", "9223\n/other")
            self.assertEqual(self.run_cli(["open", "work"])[0], 4)
        self.assertFalse(any(call[0] in {"spawn", "run"} for call in self.system.calls))

    def test_bind_conflict(self):
        self.system.busy.add(9222)
        self.assertEqual(self.run_cli(["open", "work"])[0], 4)
        self.assertFalse(any(call[0] == "spawn" for call in self.system.calls))

    def test_normal_launch(self):
        self.system.probes[9222] = [{"kind": "refused"}, {"kind": "valid", "data": support.cdp_body()}]
        self.system.spawn_hook = self.active
        code, out, _ = self.run_cli(["open", "work"])
        self.assertEqual(code, 0)
        self.assertIn("The window is open", out)
        self.assertEqual([call for call in self.system.calls if call[0] == "spawn"], [("spawn", chrome.build_chrome_argv(self.binary, self.profile["profile_dir"], 9222))])

    def test_timeout_and_early_exit(self):
        code, _, err = self.run_cli(["open", "work", "--wait", "0.5"])
        self.assertEqual(code, 5)
        self.assertIn("Chrome is asking a question", err)
        self.system.process_code = 0
        self.assertIn("without the debugging port", self.run_cli(["open", "work", "--wait", "0"])[2])

    def test_no_desktop(self):
        del self.system.env["DISPLAY"]
        self.assertEqual(self.run_cli(["open", "work"])[0], 5)
        self.assertFalse(any(call[0] == "spawn" for call in self.system.calls))

    def test_no_desktop_route_quotes_kit_directory_and_preserves_port(self):
        del self.system.env["DISPLAY"]
        kit = str(self.folder / "operator's kit")
        self.system.env["CDP_SETUP_KIT_DIR"] = kit
        with self.assertRaises(KitError) as failure:
            profiles.require_launch_session(self.system, "work", port=9333)
        record = failure.exception.hint.split("record with ", 1)[1].split("; then ", 1)[0]
        self.assertEqual(shlex.split(record), ["python3", "-m", "cdp_setup_kit", "--kit-dir", kit, "init", "--yes", "--no-open", "--name", "work", "--port", "9333"])

    def test_no_wait(self):
        self.assertEqual(self.run_cli(["open", "work", "--no-wait"])[0], 0)
        self.assertEqual(len([call for call in self.system.calls if call[0] == "probe"]), 1)

    def test_missing_folder_and_spawn_failure(self):
        folder = Path(self.profile["profile_dir"])
        folder.rmdir()
        with mock.patch.object(self.system, "spawn_detached", side_effect=OSError()):
            self.assertEqual(self.run_cli(["open", "work"])[0], 5)
        self.assertTrue(folder.is_dir())
        Path(self.binary).unlink()
        self.assertEqual(self.run_cli(["open", "work"])[0], 5)

    def test_linux_headless_without_desktop(self):
        del self.system.env["DISPLAY"]
        self.system.probes[9222] = [{"kind": "refused"}, {"kind": "valid", "data": support.cdp_body()}]
        code, out, err = self.run_cli(["open", "work", "--headless"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Headless Chrome is ready", out)
        self.assertNotIn("The window is open", out)
        argv = [call[1] for call in self.system.calls if call[0] == "spawn"][0]
        self.assertIn("--headless=new", argv)
        self.assertNotIn("--no-sandbox", argv)

    def test_headless_timeout_has_actionable_diagnosis(self):
        code, out, err = self.run_cli(["open", "work", "--headless", "--wait", "0"])
        self.assertEqual(code, 5)
        self.assertIn("shared-library dependencies", err)
        self.assertNotIn("Look at the window", err)

    def test_headless_rejected_on_other_platforms(self):
        for platform in ("windows", "macos"):
            self.system.platform = platform
            with mock.patch("cdp_setup_kit.config.load", return_value=self.data):
                code, out, err = self.run_cli(["open", "work", "--headless"])
            self.assertEqual(code, 2)
            self.assertIn("Linux only", err)
        self.assertFalse(any(call[0] == "spawn" for call in self.system.calls))

    def test_windows_ssh_and_mac_without_gui_refuse_before_probe(self):
        for platform in ("windows", "macos"):
            self.system.platform = platform
            self.system.env["SSH_CONNECTION"] = "present"
            self.system.desktop_session = False
            with mock.patch("cdp_setup_kit.config.load", return_value=self.data):
                code, out, err = self.run_cli(["open", "work"])
            self.assertEqual(code, 5)
            self.assertIn("no desktop session", err)
            if platform == "windows":
                self.assertIn("startup run work --apply", err)
            else:
                self.assertIn("Mac graphical desktop", err)
        self.assertFalse(any(call[0] in {"spawn", "probe"} for call in self.system.calls))

class StaleActivePortTests(OpenFixture, support.KitTestCase):
    def stale(self):
        self.system.write_text(self.profile["profile_dir"] + "/DevToolsActivePort", "9222\n/devtools/browser/previous-run")

    def probe_counter(self):
        return len([call for call in self.system.calls if call[0] == "probe"])

    def test_transient_conflict_during_own_start_resolves(self):
        real_probe = self.system.cdp_version
        self.system.spawn_hook = self.stale

        def probe(port, timeout=0.5):
            result = real_probe(port, timeout)
            if self.probe_counter() == 4:
                self.active()
            return result

        self.system.probes[9222] = [{"kind": "refused"}, {"kind": "valid", "data": support.cdp_body()}]
        self.system.cdp_version = probe
        code, out, err = self.run_cli(["open", "work"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("The window is open", out)
        self.assertEqual(len([call for call in self.system.calls if call[0] == "spawn"]), 1)

    def test_persistent_conflict_still_exits_4_after_bounded_retries(self):
        self.system.spawn_hook = self.stale
        self.system.probes[9222] = [{"kind": "refused"}, {"kind": "valid", "data": support.cdp_body()}]
        code, _, err = self.run_cli(["open", "work"])
        self.assertEqual(code, 4)
        self.assertIn("will not stop it", err)
        self.assertLessEqual(self.probe_counter(), 1 + 1 + 8)
        self.assertEqual([call[0] for call in self.system.calls if call[0] not in {"probe", "read_text", "make_dir", "spawn", "write_text"}], [])

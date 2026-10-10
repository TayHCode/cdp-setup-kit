from tests import support
import json
from pathlib import Path
from urllib.parse import urlsplit
from unittest import mock

from cdp_setup_kit import config, doctor, startup_linux
from cdp_setup_kit.paths import locations


class DoctorTests(support.KitTestCase):
    def setUp(self):
        super().setUp()
        self.binary = str(self.folder / "chrome")
        self.system.write_text(self.binary, "")
        self.system.runs[(self.binary, "--version")] = (0, "Google Chrome 141.0.7390.54", "")
        self.run_cli(["add", "work", "--chrome", self.binary])
        self.paths = locations(self.system)
        self.data = config.load(self.system, self.paths.config)
        self.folder_path = Path(self.data["profiles"]["work"]["profile_dir"])

    def report(self):
        code, out, err = self.run_cli(["doctor", "--json"])
        self.assertEqual(err, "")
        return code, json.loads(out)

    def test_stopped_and_json(self):
        code, data = self.report()
        self.assertEqual(code, 0)
        self.assertEqual(set(data), {"locations", "checks"})
        self.assertTrue(any(row["check"] == "work endpoint" and row["level"] == "INFO" for row in data["checks"]))
        self.assertIn("dedicated browser data", self.run_cli(["doctor"])[1])

    def test_missing_chrome_and_unknown_identity(self):
        Path(self.binary).unlink()
        self.assertEqual(self.report()[0], 7)
        self.system.write_text(self.binary, "")
        self.system.runs[(self.binary, "--version")] = (0, "Other", "")
        self.assertTrue(any(row["level"] == "WARN" and row["check"] == "Chrome identity and version" for row in self.report()[1]["checks"]))

    def test_invalid_config(self):
        for change in ["name", "port", "folder"]:
            data = json.loads(json.dumps(self.data))
            if change == "name":
                data["profiles"]["Work"] = data["profiles"].pop("work")
            else:
                data["profiles"]["shop"] = dict(data["profiles"]["work"])
                data["profiles"]["shop"]["profile_dir" if change == "port" else "port"] = str(self.folder / "shop") if change == "port" else 9223
            self.system.write_text(self.paths.config, json.dumps(data))
            self.assertEqual(self.report()[0], 7)

    def test_unknown_keys_do_not_affect_argv(self):
        self.data["extra_args"] = ["untrusted"]
        self.data["address"] = "untrusted"
        config.save(self.system, self.paths.config, self.data)
        self.assertIn("unknown key, ignored", self.run_cli(["doctor"])[1])
        self.run_cli(["open", "work", "--no-wait"])
        argv = [call[1] for call in self.system.calls if call[0] == "spawn"][0]
        self.assertEqual(len(argv), 6)
        self.assertFalse(any("untrusted" in arg for arg in argv))

    def test_folder_results(self):
        self.folder_path.chmod(0o744)
        self.assertIn("group or others", self.run_cli(["doctor"])[1])
        self.folder_path.rmdir()
        self.assertIn("not created yet", self.run_cli(["doctor"])[1])
        self.folder_path.parent.rmdir()
        self.assertEqual(self.report()[0], 7)
        self.data["profiles"]["work"]["profile_dir"] = self.system.user_dir()
        config.save(self.system, self.paths.config, self.data)
        self.assertEqual(self.report()[0], 7)

    def test_endpoint_results_and_exposure(self):
        self.system.probes[9222] = {"kind": "valid", "data": support.cdp_body()}
        code, out, err = self.run_cli(["doctor"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("PASS work endpoint: running (endpoint answers)", out)
        self.assertIn("INFO work folder marker: Fixed-port/headless", out)
        self.assertNotIn("WARN", out)
        self.assertIn("running (endpoint answers)", self.run_cli(["list"])[1])
        self.system.write_text(str(self.folder_path / "DevToolsActivePort"), "9222\n" + urlsplit(support.cdp_body()["webSocketDebuggerUrl"]).path)
        self.assertEqual(self.report()[0], 0)
        self.system.addresses = ["BROWSER-MACHINE"]
        self.system.reachable.add(("BROWSER-MACHINE", 9222))
        self.assertIn("reachable on a non-loopback", self.run_cli(["doctor"])[1])
        self.system.probes[9222] = {"kind": "not_cdp"}
        self.assertEqual(self.report()[0], 7)

    def test_startup_results(self):
        self.run_cli(["startup", "enable", "work", "--apply"])
        self.assertIn("Chrome is asking a question", self.run_cli(["doctor"])[1])
        self.run_cli(["set-port", "work", "9223", "--apply"])
        self.assertIn("stale", self.run_cli(["doctor"])[1])
        self.system.write_text(startup_linux.entry_path(self.system, self.paths, "work"), "unfamiliar")
        self.assertEqual(self.report()[0], 7)

    def test_platform_check_and_unknown_profile(self):
        self.system.platform = "other"
        report = doctor.diagnose(self.system, self.paths, {"schema": 1, "chrome_path": None, "profiles": {}})
        self.assertEqual(report["checks"][0]["level"], "FAIL")
        self.system.platform = "linux"
        self.assertEqual(self.run_cli(["doctor", "research"])[0], 3)

    def test_unreadable_marker_is_a_real_warning(self):
        self.system.probes[9222] = {"kind": "valid", "data": support.cdp_body()}
        original = self.system.read_text
        def read(path, encoding="utf-8"):
            if str(path).endswith("DevToolsActivePort"):
                raise PermissionError()
            return original(path, encoding)
        with mock.patch.object(self.system, "read_text", side_effect=read):
            out = self.run_cli(["doctor"])[1]
        self.assertIn("WARN work endpoint: running-unconfirmed", out)
        self.assertIn("check folder permissions", out)

    def test_marker_mismatch_still_refuses_healthy_foreign_endpoint(self):
        self.system.probes[9222] = {"kind": "valid", "data": support.cdp_body()}
        self.system.write_text(str(self.folder_path / "DevToolsActivePort"), "9223\n/other")
        self.assertEqual(self.report()[0], 7)
        self.assertIn("profile folder marker differs", self.run_cli(["doctor"])[1])

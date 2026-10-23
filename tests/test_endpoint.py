from tests import support
from urllib.parse import urlsplit
from unittest import mock

from cdp_setup_kit.endpoint import exposure, looks_open, status


class EndpointTests(support.KitTestCase):
    def setUp(self):
        super().setUp()
        self.profile = {"port": 9222, "profile_dir": str(self.folder / "work")}
        self.active = self.folder / "work" / "DevToolsActivePort"

    def test_supplied_http_origins(self):
        from cdp_setup_kit.endpoint import parse_http_endpoint
        for value, expected in (
            ("http://localhost:9333/", ("http://localhost:9333", "localhost", 9333)),
            ("http://browser.example", ("http://browser.example:80", "browser.example", 80)),
            ("http://[::1]:9333", ("http://[::1]:9333", "::1", 9333)),
        ):
            with self.subTest(value=value):
                self.assertEqual(parse_http_endpoint(value), expected)

    def test_supplied_endpoint_rejects_non_origins(self):
        from cdp_setup_kit.endpoint import parse_http_endpoint
        from cdp_setup_kit.errors import KitError
        for value in ("", "https://localhost:9333", "ws://localhost:9333", "http://", "http://localhost:",
                      "http://localhost:0", "http://localhost:65536", "http://localhost:wrong",
                      "http://user:password@localhost:9333", "http://localhost:9333/json/version",
                      "http://localhost:9333?", "http://localhost:9333#", "http://local host:9333",
                      "http://localhost:9333\n", "http://local'host:9333", "http://[::1%zone]:9333"):
            with self.subTest(value=value), self.assertRaises(KitError) as error:
                parse_http_endpoint(value)
            self.assertEqual(error.exception.exit_code, 2)

    def test_status_rows(self):
        self.assertEqual(status(self.system, self.profile)["status"], "stopped")
        self.assertEqual(status(self.system, self.profile, False)["status"], "not-checked")
        self.system.probes[9222] = {"kind": "not_cdp"}
        self.assertEqual(status(self.system, self.profile)["status"], "conflict")
        self.system.probes[9222] = {"kind": "valid", "data": support.cdp_body()}
        self.assertEqual(status(self.system, self.profile)["status"], "running")
        for text in ["", "9222", "9223\n/wrong", "9222\n/wrong"]:
            self.system.write_text(str(self.active), text)
            self.assertEqual(status(self.system, self.profile)["status"], "conflict")
        self.system.write_text(str(self.active), "9222\n" + urlsplit(support.cdp_body()["webSocketDebuggerUrl"]).path)
        self.assertEqual(status(self.system, self.profile)["status"], "running")

    def test_no_check_does_not_probe(self):
        status(self.system, self.profile, False)
        self.assertEqual(self.system.calls, [])

    def test_unreadable_active_port(self):
        self.system.probes[9222] = {"kind": "valid", "data": support.cdp_body()}
        with mock.patch.object(self.system, "read_text", side_effect=PermissionError()):
            self.assertEqual(status(self.system, self.profile)["status"], "running-unconfirmed")

    def test_open_hints(self):
        self.assertFalse(looks_open(self.system, self.profile))
        self.active.parent.mkdir()
        (self.active.parent / "SingletonLock").symlink_to("BROWSER-MACHINE-123")
        self.system.process_paths = {"/proc/123"}
        self.assertTrue(looks_open(self.system, self.profile))
        self.system.process_paths.clear()
        self.assertFalse(looks_open(self.system, self.profile))
        system = support.FakeSystem(self.folder, "windows")
        profile = {"profile_dir": r"D:\kit-data\profiles\work"}
        system.write_text(r"D:\kit-data\profiles\work\lockfile", "")
        self.assertTrue(looks_open(system, profile))

    def test_exposure_rows(self):
        ws = support.cdp_body()["webSocketDebuggerUrl"]
        self.assertEqual(exposure(self.system, 9222, ws)[0]["level"], "INFO")
        self.system.addresses = ["BROWSER-MACHINE"]
        self.assertEqual(exposure(self.system, 9222, ws)[0]["level"], "PASS")
        self.system.reachable.add(("BROWSER-MACHINE", 9222))
        self.assertEqual(exposure(self.system, 9222, ws)[0]["level"], "WARN")
        self.assertEqual(exposure(self.system, 9222, "ws://BROWSER-MACHINE/changed")[-1]["level"], "WARN")

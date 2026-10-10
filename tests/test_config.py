from tests import support
import copy
import json
from unittest import mock

from cdp_setup_kit import config
from cdp_setup_kit.errors import KitError
from cdp_setup_kit.paths import locations


class ConfigTests(support.KitTestCase):
    def setUp(self):
        super().setUp()
        self.path = locations(self.system).config
        self.data = config.load(self.system, self.path)

    def test_missing_and_roundtrip(self):
        self.assertEqual(self.data, {"schema": 1, "chrome_path": None, "profiles": {}})
        self.data["future"] = {"flag": True}
        config.save(self.system, self.path, self.data)
        self.assertEqual(config.load(self.system, self.path), self.data)
        self.data["future"]["flag"] = False
        config.save(self.system, self.path, self.data)
        self.assertTrue(json.loads(self.system.read_text(self.path + ".bak"))["future"]["flag"])

    def test_invalid_and_newer_preserved(self):
        for text in ["{", "[]", '{"schema": 2}', '{"schema": true}', '{"schema": 0}']:
            self.system.write_text(self.path, text)
            for action in [lambda: config.load(self.system, self.path), lambda: config.save(self.system, self.path, self.data)]:
                with self.assertRaises(KitError) as caught:
                    action()
                self.assertEqual(caught.exception.exit_code, 3)
            self.assertEqual(self.system.read_text(self.path), text)

    def test_names_and_ports(self):
        for name in ["work", "shop", "research", "main"]:
            config.validate_name(name)
        for name in ["", "Work", "work-", "9work", "work/next", "w" * 33]:
            with self.assertRaises(KitError):
                config.validate_name(name)
        for port in [1024, 65535, 9222]:
            config.validate_port(port)
        for port in [True, None, "9222", 1023, 65536]:
            with self.assertRaises(KitError):
                config.validate_port(port)

    def test_duplicate_port_and_folder(self):
        profile = {"port": 9222, "profile_dir": str(self.folder / "profiles" / "work"), "created_by_kit": True, "created": "2026-01-01T00:00:00Z", "unknown": "kept"}
        self.data["profiles"]["work"] = profile
        config.validate(self.data, self.system)
        for field, value in [("port", 9223), ("profile_dir", str(self.folder / "profiles" / "shop"))]:
            other = copy.deepcopy(profile)
            other[field] = value
            self.data["profiles"]["shop"] = other
            with self.assertRaises(KitError):
                config.validate(self.data, self.system)

    def test_unknown_profile_keys(self):
        self.data["address"] = "ignored"
        self.data["profiles"]["work"] = {"port": 9222, "profile_dir": str(self.folder / "work"), "created_by_kit": False, "created": "2026-01-01T00:00:00Z", "extra_args": []}
        config.save(self.system, self.path, self.data)
        self.assertEqual(config.load(self.system, self.path), self.data)
        self.assertEqual(config.unknown_keys(self.data), ["address", "work:extra_args"])

    def test_unreadable_is_not_overwritten(self):
        config.save(self.system, self.path, self.data)
        self.system.calls.clear()
        with mock.patch.object(self.system, "read_text", side_effect=PermissionError()):
            with self.assertRaises(KitError):
                config.load(self.system, self.path)
            with self.assertRaises(KitError):
                config.save(self.system, self.path, self.data)
        self.assertFalse(any(call[0] == "write_text" for call in self.system.calls))

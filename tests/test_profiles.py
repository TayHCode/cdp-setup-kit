from tests import support
import json
from pathlib import Path

from cdp_setup_kit import config
from cdp_setup_kit.paths import locations


class ProfileTests(support.KitTestCase):
    def setUp(self):
        super().setUp()
        self.paths = locations(self.system)

    def read(self):
        return config.load(self.system, self.paths.config)

    def test_add_and_repeat(self):
        self.assertEqual(self.run_cli(["add", "work", "--port", "9222"])[0], 0)
        before = self.read()
        folder = Path(before["profiles"]["work"]["profile_dir"])
        self.assertTrue(folder.is_dir())
        self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
        self.system.calls.clear()
        self.assertIn("already set up, unchanged", self.run_cli(["add", "work"])[1])
        self.assertEqual(self.read(), before)
        self.assertFalse(any(call[0] in {"write_text", "make_dir", "probe"} for call in self.system.calls))

    def test_changed_settings_rejected(self):
        self.run_cli(["add", "work"])
        before = self.read()
        for extra in [["--port", "9223"], ["--profile-dir", str(self.folder / "other")]]:
            self.assertEqual(self.run_cli(["add", "work"] + extra)[0], 3)
        self.assertEqual(self.read(), before)

    def test_adopt_and_busy(self):
        folder = self.folder / "adopted"
        folder.mkdir()
        self.system.probes[9222] = {"kind": "not_cdp"}
        code, out, _ = self.run_cli(["add", "work", "--port", "9222", "--profile-dir", str(folder)])
        self.assertEqual(code, 0)
        self.assertIn("busy", out)
        self.assertFalse(self.read()["profiles"]["work"]["created_by_kit"])

    def test_set_port(self):
        self.run_cli(["add", "work"])
        before = self.read()
        self.assertEqual(self.run_cli(["set-port", "work", "9223"])[0], 0)
        self.assertEqual(self.read(), before)
        self.assertEqual(self.run_cli(["set-port", "work", "9223", "--apply"])[0], 0)
        before["profiles"]["work"]["port"] = 9223
        self.assertEqual(self.read(), before)

    def test_remove_retains_folder(self):
        self.run_cli(["add", "work"])
        before = self.read()
        self.assertEqual(self.run_cli(["remove", "work"])[0], 0)
        self.assertEqual(self.read(), before)
        self.assertEqual(self.run_cli(["remove", "work", "--apply"])[0], 0)
        self.assertTrue(Path(before["profiles"]["work"]["profile_dir"]).exists())
        self.assertEqual(self.read()["profiles"], {})

    def test_delete_own_stopped_folder(self):
        self.run_cli(["add", "work"])
        folder = Path(self.read()["profiles"]["work"]["profile_dir"])
        self.assertEqual(self.run_cli(["remove", "work", "--delete-data", "--apply"])[0], 0)
        self.assertFalse(folder.exists())

    def test_delete_refusals_leave_config(self):
        self.run_cli(["add", "work"])
        original = self.read()
        for kind in ["adopted", "outside", "busy", "open"]:
            data = json.loads(json.dumps(original))
            self.system.probes.clear()
            if kind == "adopted":
                data["profiles"]["work"]["created_by_kit"] = False
            elif kind == "outside":
                data["profiles"]["work"]["profile_dir"] = str(self.folder / "elsewhere")
            elif kind == "busy":
                self.system.probes[9222] = {"kind": "not_cdp"}
            else:
                folder = Path(data["profiles"]["work"]["profile_dir"])
                (folder / "SingletonLock").symlink_to("BROWSER-MACHINE-123")
                self.system.process_paths = {"/proc/123"}
            config.save(self.system, self.paths.config, data)
            self.assertEqual(self.run_cli(["remove", "work", "--delete-data", "--apply"])[0], 8)
            self.assertEqual(self.read(), data)

    def test_delete_symlink_refused(self):
        self.run_cli(["add", "work"])
        before = self.read()
        folder = Path(before["profiles"]["work"]["profile_dir"])
        folder.rmdir()
        target = self.folder / "target"
        target.mkdir()
        folder.symlink_to(target, target_is_directory=True)
        self.assertEqual(self.run_cli(["remove", "work", "--delete-data", "--apply"])[0], 8)
        self.assertEqual(self.read(), before)

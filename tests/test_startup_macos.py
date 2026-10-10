from tests import support
import json
from pathlib import Path
import plistlib
from unittest import mock

from cdp_setup_kit import chrome, config, startup, startup_macos
from cdp_setup_kit.constants import MACOS_MARKER
from cdp_setup_kit.errors import KitError
from cdp_setup_kit.paths import locations
from tests.test_macos import MAC_BINARY


class MacStartupTests(support.KitTestCase):
    def setUp(self):
        super().setUp()
        self.system = support.FakeSystem(self.folder, "macos")
        self.binary = str(self.folder / "Google Chrome.app/Contents/MacOS/Google Chrome")
        self.system.write_text(self.binary, "")
        self.assertEqual(self.run_cli(["add", "work", "--chrome", self.binary])[0], 0)
        self.paths = locations(self.system)
        self.data = config.load(self.system, self.paths.config)
        self.target = startup_macos.entry_path(self.system, self.paths, "work")
        self.system.calls.clear()

    def plan(self, action="enable"):
        return startup.build_plan(self.system, self.paths, self.data, "work", action)

    def enable(self):
        self.assertEqual(self.run_cli(["startup", "enable", "work", "--apply"])[0], 0)

    def assert_no_changes(self):
        self.assertFalse(any(call[0] in {"write_text", "make_dir", "remove_file", "remove_tree", "run", "spawn"} for call in self.system.calls))

    def test_no_desktop_preview_refusal_override_and_disable(self):
        from unittest import mock
        with mock.patch.object(self.system, "has_desktop_session", return_value=False):
            self.system.calls.clear()
            code, out, err = self.run_cli(["startup", "enable", "work"])
            self.assertEqual((code, err), (0, ""))
            self.assertIn("This shell has no desktop session (it is a remote/SSH or service session): a visible window cannot open from here", out)
            self.assertIn("--force-no-desktop", out)
            self.assertNotIn("Effect: ", out)
            self.assertFalse(any(call[0] in {"write_text", "make_dir", "spawn", "remove_file"} for call in self.system.calls))
            self.system.calls.clear()
            code, out, err = self.run_cli(["startup", "enable", "work", "--apply"])
            self.assertEqual(code, 5)
            self.assertIn("--force-no-desktop", err)
            self.assertFalse(any(call[0] in {"write_text", "make_dir", "spawn", "remove_file", "run"} for call in self.system.calls))
            self.assertEqual(self.run_cli(["startup", "enable", "work", "--apply", "--force-no-desktop"])[0], 0)
            self.assertEqual(self.run_cli(["startup", "disable", "work", "--apply"])[0], 0)

    def test_plist_and_preview_goldens(self):
        argv = chrome.build_chrome_argv(MAC_BINARY, "/srv/kit-data/profiles/work", 9222)
        text = startup_macos.plist_text("work", argv)
        self.assertEqual(text, (support.ROOT / "tests/golden/macos-launchagent.plist.txt").read_text())
        values = plistlib.loads(text.encode())
        self.assertEqual(values["ProgramArguments"], argv)
        self.assertEqual(values["Label"], "cdp-setup-kit-work")
        self.assertEqual(values[MACOS_MARKER], "1")
        self.assertEqual(values["X-Cdp-Setup-Kit-Profile"], "work")
        self.assertIs(values["RunAtLoad"], True)
        self.assertIs(values["KeepAlive"], False)
        self.assertEqual(values["LimitLoadToSessionType"], "Aqua")
        plan = startup.StartupPlan("work", "enable", files=[("/srv/kit-data/Library/LaunchAgents/cdp-setup-kit-work.plist", text, "utf-8", 0o600)], effect='the "work" Chrome window opens each time you sign in. Takes effect at the next graphical sign-in; existing windows stay open.')
        self.assertEqual(startup.preview(self.system, plan) + "\n", (support.ROOT / "tests/golden/startup-preview-macos.txt").read_text())

    def test_arguments_are_not_shell_text_and_xml_is_escaped(self):
        argv = chrome.build_chrome_argv(MAC_BINARY, "/srv/kit-data/o'neil & <work>/profiles/work", 9222)
        text = startup_macos.plist_text("work", argv)
        self.assertIn("&amp; &lt;work&gt;", text)
        self.assertEqual(plistlib.loads(text.encode())["ProgramArguments"], argv)

    def test_preview_then_apply_exact_file_and_idempotence(self):
        plan = self.plan()
        code, out, _ = self.run_cli(["startup", "enable", "work"])
        self.assertEqual(code, 0)
        self.assertIn("next graphical sign-in", out)
        self.assert_no_changes()
        self.assertEqual(plan.commands, [])
        self.enable()
        self.assertEqual(self.system.read_text(self.target), plan.files[0][1])
        self.assertEqual(self.system.file_mode(self.target), 0o600)
        writes = [call[1:] for call in self.system.calls if call[0] == "write_text"]
        self.assertEqual(writes, plan.files)
        self.assertFalse(any(call[0] in {"run", "spawn"} for call in self.system.calls))
        self.system.calls.clear()
        self.assertIn("already enabled, unchanged", self.run_cli(["startup", "enable", "work", "--apply"])[1])
        self.assert_no_changes()

    def test_unchanged_previews_have_no_action_guidance(self):
        for args in (["startup", "disable", "work"], ["remove", "work"]):
            with self.subTest(args=args):
                code, out, _ = self.run_cli(args)
                self.assertEqual(code, 0)
                self.assertIn("nothing to remove" if args[0] == "startup" else "No sign-in entry exists", out)
                if args[0] == "remove":
                    self.assertNotIn("nothing to remove", out)
                self.assertNotIn("Effect:", out)
                self.assertNotIn("To do it:", out)
                self.assertNotIn("To undo it:", out)
        self.assert_no_changes()
        self.enable()
        self.system.calls.clear()
        code, out, _ = self.run_cli(["startup", "enable", "work"])
        self.assertEqual(code, 0)
        self.assertIn("already enabled, unchanged", out)
        self.assertNotIn("Effect:", out)
        self.assertNotIn("To do it:", out)
        self.assertNotIn("To undo it:", out)
        self.assert_no_changes()

    def test_port_and_chrome_changes_are_stale_and_repaired(self):
        self.enable()
        self.assertIn("old port", self.run_cli(["set-port", "work", "9223", "--apply"])[1])
        self.assertIn("stale", self.run_cli(["startup", "status", "work"])[1])
        self.enable()
        self.assertIn("enabled", self.run_cli(["startup", "status", "work"])[1])
        data = config.load(self.system, self.paths.config)
        binary = str(self.folder / "other Google Chrome")
        self.system.write_text(binary, "")
        data["chrome_path"] = binary
        config.save(self.system, self.paths.config, data)
        self.assertIn("stale", self.run_cli(["startup", "status", "work"])[1])
        self.enable()
        self.assertEqual(plistlib.loads(self.system.read_text(self.target).encode())["ProgramArguments"][0], binary)

    def test_disable_owned_only_and_without_chrome(self):
        other = self.paths.startup + "/other.plist"
        self.system.write_text(other, "unfamiliar")
        self.enable()
        data = config.load(self.system, self.paths.config)
        data["chrome_path"] = str(self.folder / "unsafe$")
        config.save(self.system, self.paths.config, data)
        self.assertEqual(self.run_cli(["list", "--no-check"])[0], 0)
        self.system.calls.clear()
        self.assertEqual(self.run_cli(["startup", "disable", "work"])[0], 0)
        self.assert_no_changes()
        self.assertTrue(self.system.exists(self.target))
        self.assertEqual(self.run_cli(["startup", "disable", "work", "--apply"])[0], 0)
        self.assertFalse(self.system.exists(self.target))
        self.assertEqual(self.system.read_text(other), "unfamiliar")
        self.system.calls.clear()
        self.assertIn("nothing to remove", self.run_cli(["startup", "disable", "work", "--apply"])[1])
        self.assert_no_changes()

    def test_foreign_invalid_or_wrong_profile_is_kept(self):
        owned = self.plan().files[0][1]
        fixtures = ["unfamiliar", "<plist/>", owned.replace(MACOS_MARKER, "Other-Marker"),
                    owned.replace("<string>1</string>", "<integer>1</integer>"),
                    owned.replace("cdp-setup-kit-work", "cdp-setup-kit-shop"),
                    owned.replace("<string>work</string>", "<string>shop</string>"),
                    owned.replace("</dict>", "<key>Label</key><string>duplicate</string></dict>")]
        for text in fixtures:
            with self.subTest(text=text[:20]):
                self.system.write_text(self.target, text)
                self.system.calls.clear()
                self.assertIn("foreign", self.run_cli(["startup", "status", "work"])[1])
                for args in [["startup", "enable", "work"], ["startup", "enable", "work", "--apply"], ["startup", "disable", "work", "--apply"], ["remove", "work", "--apply"]]:
                    code, out, _ = self.run_cli(args)
                    self.assertEqual(code, 6)
                    self.assertNotIn("Removing", out)
                    self.assertEqual(self.system.read_text(self.target), text)
                    self.assertIn("work", config.load(self.system, self.paths.config)["profiles"])
                self.assert_no_changes()

    def test_symlinks_and_unreadable_entries_are_foreign(self):
        target = Path(self.target)
        target.parent.mkdir(parents=True)
        other = self.folder / "other.plist"
        for exists in (False, True):
            if exists:
                other.write_text(self.plan().files[0][1])
            target.symlink_to(other)
            self.system.calls.clear()
            self.assertIn("foreign", self.run_cli(["startup", "status", "work"])[1])
            self.assertEqual(self.run_cli(["startup", "disable", "work", "--apply"])[0], 6)
            self.assertTrue(target.is_symlink())
            self.assert_no_changes()
            target.unlink()
        self.enable()
        with mock.patch.object(self.system, "read_text", side_effect=PermissionError()):
            self.assertEqual(startup_macos.status(self.system, self.target, "", "work"), "foreign")

    def test_apply_rechecks_ownership(self):
        enable = self.plan()
        self.system.write_text(self.target, "unfamiliar")
        self.system.calls.clear()
        with self.assertRaises(KitError) as caught:
            startup.apply_plan(self.system, enable)
        self.assertEqual(caught.exception.exit_code, 6)
        self.assert_no_changes()
        self.system.remove_file(self.target)
        self.enable()
        disable = self.plan("disable")
        self.system.write_text(self.target, "unfamiliar")
        self.system.calls.clear()
        with self.assertRaises(KitError):
            startup.apply_plan(self.system, disable)
        self.assert_no_changes()

    def test_apply_rechecks_unchanged_plan(self):
        self.enable()
        plan = self.plan()
        self.system.remove_file(self.target)
        self.system.calls.clear()
        with self.assertRaises(KitError):
            startup.apply_plan(self.system, plan)
        self.assert_no_changes()

    def test_list_and_doctor_integration(self):
        self.enable()
        row = json.loads(self.run_cli(["list", "--json", "--no-check"])[1])["profiles"][0]
        self.assertEqual(row["startup"], "enabled")
        self.assertEqual(row["status"], "not-checked")
        self.assertIn("Chrome is asking a question", self.run_cli(["doctor", "work"])[1])
        self.run_cli(["set-port", "work", "9223", "--apply"])
        self.assertEqual(json.loads(self.run_cli(["list", "--json", "--no-check"])[1])["profiles"][0]["startup"], "stale")
        self.system.write_text(self.target, "unfamiliar")
        self.assertEqual(self.run_cli(["doctor", "work"])[0], 7)
        self.assertEqual(json.loads(self.run_cli(["list", "--json", "--no-check"])[1])["profiles"][0]["startup"], "foreign")

    def test_permission_failure_names_launchagent_and_help(self):
        with mock.patch.object(self.system, "write_text", side_effect=PermissionError()):
            code, _, err = self.run_cli(["startup", "enable", "work", "--apply"])
        self.assertEqual(code, 6)
        self.assertIn(self.target, err)
        self.assertIn("permissions", err)
        self.assertIn("docs/startup.md", err)

    def test_remove_retains_data_and_only_removes_owned_plist(self):
        self.enable()
        profile = self.data["profiles"]["work"]
        self.assertEqual(self.run_cli(["remove", "work"])[0], 0)
        self.assertTrue(self.system.exists(self.target))
        self.assertEqual(self.run_cli(["remove", "work", "--apply"])[0], 0)
        self.assertFalse(self.system.exists(self.target))
        self.assertTrue(self.system.is_dir(profile["profile_dir"]))
        self.assertNotIn("work", config.load(self.system, self.paths.config)["profiles"])

    def test_delete_data_refuses_lock_then_allows_stopped_kit_folder(self):
        self.enable()
        profile = self.data["profiles"]["work"]
        lock = Path(profile["profile_dir"]) / "SingletonLock"
        lock.symlink_to("BROWSER-MACHINE-123")
        self.assertEqual(self.run_cli(["remove", "work", "--delete-data", "--apply"])[0], 8)
        self.assertTrue(self.system.exists(self.target))
        lock.unlink()
        self.assertEqual(self.run_cli(["remove", "work", "--delete-data", "--apply"])[0], 0)
        self.assertFalse(self.system.exists(profile["profile_dir"]))


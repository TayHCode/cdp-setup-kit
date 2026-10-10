from tests import support
import json
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

from cdp_setup_kit import chrome, config, endpoint
from cdp_setup_kit.constants import LOOPBACK
from cdp_setup_kit.errors import KitError
from cdp_setup_kit.paths import locations


MAC_BINARY = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class MacChromeTests(support.KitTestCase):
    def setUp(self):
        super().setUp()
        self.system = support.FakeSystem(self.folder, "macos")

    def test_search_precedence_and_app_binary(self):
        candidates = [str(self.folder / item) for item in ("explicit", "config", "env")]
        for candidate in candidates:
            self.system.write_text(candidate, "")
        self.system.env["CDP_SETUP_KIT_CHROME"] = candidates[2]
        data = {"chrome_path": candidates[1]}
        original = self.system.is_file
        with mock.patch.object(self.system, "is_file", side_effect=lambda value: value == MAC_BINARY or original(value)):
            self.assertEqual(chrome.find_chrome(self.system, data, candidates[0]), candidates[0])
            self.assertEqual(chrome.find_chrome(self.system, data), candidates[1])
            self.system.remove_file(candidates[1])
            self.assertEqual(chrome.find_chrome(self.system, data), candidates[2])
            self.system.remove_file(candidates[2])
            self.assertEqual(chrome.find_chrome(self.system, data), MAC_BINARY)
        self.assertIsNone(chrome.find_chrome(self.system, data))
        self.assertFalse(any(call[0] in {"run", "spawn"} for call in self.system.calls))

    def test_identity_is_scripted(self):
        self.system.runs[(MAC_BINARY, "--version")] = (0, "Google Chrome 141.0.7390.54", "")
        self.assertEqual(chrome.identity(self.system, MAC_BINARY), ("141.0.7390.54", True))
        self.system.runs[(MAC_BINARY, "--version")] = (0, "Unknown", "")
        self.assertEqual(chrome.identity(self.system, MAC_BINARY), (None, False))
        with mock.patch.object(self.system, "run", side_effect=TimeoutError()):
            self.assertEqual(chrome.identity(self.system, MAC_BINARY), (None, False))

    def test_command_golden(self):
        argv = chrome.build_chrome_argv(MAC_BINARY, "/srv/kit-data/profiles/work", 9222)
        self.assertEqual(argv, json.loads((support.ROOT / "tests/golden/macos-command.json").read_text()))
        self.assertEqual(len(argv), 6)
        self.assertEqual(argv[3], "--remote-debugging-address=" + LOOPBACK)

    def test_default_data_folders_ancestors_and_case_refused(self):
        base = self.system.user_dir() + "/Library/Application Support"
        for item in ("Google/Chrome", "Google/Chrome Beta", "Google/Chrome Canary", "Chromium", "Microsoft Edge"):
            for target in (base + "/" + item, base + "/" + item + "/Default", (base + "/" + item).upper()):
                with self.subTest(item=item, target=target), self.assertRaises(KitError) as caught:
                    chrome.check_profile_dir(self.system, target, {"profiles": {}})
                self.assertEqual(caught.exception.exit_code, 8)
        for target in (base, base + "/Google", self.system.user_dir(), "/"):
            with self.subTest(target=target), self.assertRaises(KitError):
                chrome.check_profile_dir(self.system, target, {"profiles": {}})
        target = base + "/Google/Chrome"
        code, _, _ = self.run_cli(["add", "work", "--profile-dir", target])
        self.assertEqual(code, 8)
        self.assertFalse(Path(locations(self.system).config).exists())

    def test_symlink_to_default_data_refused(self):
        target = Path(self.system.user_dir()) / "Library/Application Support/Google/Chrome"
        target.mkdir(parents=True)
        alias = self.folder / "alias"
        alias.symlink_to(target, target_is_directory=True)
        with self.assertRaises(KitError):
            chrome.check_profile_dir(self.system, str(alias), {"profiles": {}})

    def test_checkout_unsafe_paths_and_duplicate_case_refused(self):
        self.system.write_text(str(self.folder / "checkout/.git"), "fixture")
        with self.assertRaises(KitError):
            chrome.check_profile_dir(self.system, str(self.folder / "checkout/work"), {"profiles": {}})
        for char in ['"', '`', '$', '%', '\\', '\n', chr(127)]:
            with self.subTest(char=char), self.assertRaises(KitError):
                chrome.safe_characters(self.system, "/srv/kit-data/work" + char)
        folder = str(self.folder / "dedicated/Work")
        data = {"profiles": {"shop": {"profile_dir": folder}}}
        with self.assertRaises(KitError):
            chrome.check_profile_dir(self.system, folder.lower(), data, "work")
        self.assertEqual(chrome.check_profile_dir(self.system, folder, {"profiles": {}}), folder)


class MacProfileTests(support.KitTestCase):
    def setUp(self):
        super().setUp()
        self.system = support.FakeSystem(self.folder, "macos")
        self.binary = str(self.folder / "Google Chrome.app/Contents/MacOS/Google Chrome")
        self.system.write_text(self.binary, "")
        self.assertEqual(self.run_cli(["add", "work", "--chrome", self.binary])[0], 0)
        self.paths = locations(self.system)
        self.data = config.load(self.system, self.paths.config)
        self.profile = self.data["profiles"]["work"]
        self.system.calls.clear()

    def active(self):
        self.system.write_text(self.profile["profile_dir"] + "/DevToolsActivePort", "9222\n" + urlsplit(support.cdp_body()["webSocketDebuggerUrl"]).path)

    def test_direct_launch_and_active_port(self):
        self.system.probes[9222] = [{"kind": "refused"}, {"kind": "valid", "data": support.cdp_body()}]
        self.system.spawn_hook = self.active
        self.assertEqual(self.run_cli(["open", "work"])[0], 0)
        self.assertEqual([call[1] for call in self.system.calls if call[0] == "spawn"], [chrome.build_chrome_argv(self.binary, self.profile["profile_dir"], 9222)])
        self.assertEqual(endpoint.status(self.system, self.profile)["status"], "running")
        self.assertEqual(self.system.file_mode(self.profile["profile_dir"]), 0o700)

    def test_unconfirmed_running_and_conflict_do_not_launch(self):
        self.system.probes[9222] = {"kind": "valid", "data": support.cdp_body()}
        self.assertIn("already open", self.run_cli(["open", "work"])[1])
        self.active()
        self.assertIn("already open", self.run_cli(["open", "work"])[1])
        self.system.write_text(self.profile["profile_dir"] + "/DevToolsActivePort", "9223\n/other")
        self.assertEqual(self.run_cli(["open", "work"])[0], 4)
        self.system.probes[9222] = {"kind": "not_cdp"}
        self.assertEqual(self.run_cli(["open", "work"])[0], 4)
        self.assertFalse(any(call[0] in {"spawn", "run"} for call in self.system.calls))

    def test_conservative_lock_hint_and_timeout_help(self):
        lock = Path(self.profile["profile_dir"]) / "SingletonLock"
        lock.symlink_to("BROWSER-MACHINE-123")
        self.assertTrue(endpoint.looks_open(self.system, self.profile))
        code, _, err = self.run_cli(["open", "work", "--wait", "0"])
        self.assertEqual(code, 5)
        for hint in ("without the debugging port", "Look at the window", "managed-device policy", "--wait 60"):
            self.assertIn(hint, err)
        lock.unlink()
        self.assertFalse(endpoint.looks_open(self.system, self.profile))

    def test_launch_error_help(self):
        with mock.patch.object(self.system, "spawn_detached", side_effect=OSError()):
            code, _, err = self.run_cli(["open", "work"])
        self.assertEqual(code, 5)
        self.assertIn("check the Chrome path and file permissions", err)

    def test_init_add_connect_doctor_and_case_duplicates(self):
        self.assertEqual(self.run_cli(["init", "--yes", "--no-open"])[0], 0)
        self.assertIn("unchanged", self.run_cli(["add", "work"])[1])
        self.assertEqual(self.run_cli(["connect", "work"])[0], 0)
        self.system.runs[(self.binary, "--version")] = (0, "Google Chrome 141.0.7390.54", "")
        code, out, _ = self.run_cli(["doctor", "work", "--json"])
        self.assertEqual(code, 0)
        self.assertIn({"level": "PASS", "check": "platform", "message": "macos"}, json.loads(out)["checks"])
        self.assertEqual(self.run_cli(["add", "shop", "--profile-dir", self.profile["profile_dir"].upper()])[0], 8)
        duplicate = dict(self.profile, port=9223, profile_dir=self.profile["profile_dir"].upper())
        self.data["profiles"]["shop"] = duplicate
        with self.assertRaises(KitError):
            config.validate(self.data, self.system)


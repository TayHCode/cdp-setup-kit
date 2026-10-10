from tests import support
from pathlib import Path
from unittest import mock

from cdp_setup_kit.chrome import build_chrome_argv, check_profile_dir, find_chrome, identity, safe_characters
from cdp_setup_kit.constants import LOOPBACK
from cdp_setup_kit.errors import KitError
from cdp_setup_kit.paths import path_module


class ChromeTests(support.KitTestCase):
    def test_linux_search_order(self):
        candidates = [str(self.folder / name) for name in ("explicit", "config", "env", "stable", "chrome")]
        for candidate in candidates:
            self.system.write_text(candidate, "")
        self.system.binaries = dict(zip(["google-chrome-stable", "google-chrome"], candidates[3:]))
        self.system.env["CDP_SETUP_KIT_CHROME"] = candidates[2]
        data = {"chrome_path": candidates[1]}
        self.assertEqual(find_chrome(self.system, data, candidates[0]), candidates[0])
        self.assertEqual(find_chrome(self.system, data), candidates[1])
        data["chrome_path"] = None
        self.assertEqual(find_chrome(self.system, data), candidates[2])
        del self.system.env["CDP_SETUP_KIT_CHROME"]
        self.assertEqual(find_chrome(self.system, data), candidates[3])
        self.system.binaries.pop("google-chrome-stable")
        self.assertEqual(find_chrome(self.system, data), candidates[4])

    def test_windows_search_order(self):
        system = support.FakeSystem(self.folder, "windows")
        paths = [r"D:\kit-data\machine.exe", r"D:\kit-data\account.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
        for path in paths:
            system.write_text(path, "")
        system.registry = dict(zip(["HKEY_LOCAL_MACHINE", "HKEY_CURRENT_USER"], paths))
        system.env["ProgramFiles"] = r"C:\Program Files"
        self.assertEqual(find_chrome(system, {}), paths[0])
        system.registry.pop("HKEY_LOCAL_MACHINE")
        self.assertEqual(find_chrome(system, {}), paths[1])
        system.registry.clear()
        self.assertEqual(find_chrome(system, {}), paths[2])

    def test_identity(self):
        binary = str(self.folder / "chrome")
        self.system.runs[(binary, "--version")] = (0, "Google Chrome 141.0.7390.54", "")
        self.assertEqual(identity(self.system, binary), ("141.0.7390.54", True))
        self.system.runs[(binary, "--version")] = (0, "Other browser", "")
        self.assertEqual(identity(self.system, binary), (None, False))
        system = support.FakeSystem(self.folder, "windows")
        binary = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        system.make_dir(r"C:\Program Files\Google\Chrome\Application\141.0.7390.54")
        self.assertEqual(identity(system, binary), ("141.0.7390.54", True))
        self.assertFalse(any(call[0] == "run" for call in system.calls))

    def test_launch_list(self):
        for name in ["work", "shop", "research", "main"]:
            for port in [1024, 9222, 65535]:
                folder = str(self.folder / name)
                self.assertEqual(build_chrome_argv("chrome", folder, port), ["chrome", "--user-data-dir=" + folder, "--remote-debugging-port=" + str(port), "--remote-debugging-address=" + LOOPBACK, "--no-first-run", "--no-default-browser-check"])

    def test_linux_refused_folders(self):
        user = self.system.user_dir()
        folders = [user, "/"] + [user + "/" + part for part in (".config/google-chrome", ".config/google-chrome-beta", ".config/google-chrome-unstable", ".config/chromium", "snap/chromium", ".var/app/com.google.Chrome")]
        for folder in folders:
            with self.subTest(folder=folder), self.assertRaises(KitError) as caught:
                check_profile_dir(self.system, folder, {"profiles": {}})
            self.assertEqual(caught.exception.exit_code, 8)
        checkout = self.folder / "checkout"
        (checkout / ".git").mkdir(parents=True)
        with self.assertRaises(KitError):
            check_profile_dir(self.system, str(checkout / "profiles"), {"profiles": {}})
        with self.assertRaises(KitError):
            check_profile_dir(self.system, user + "/.config/google-chrome/nested", {"profiles": {}})

    def test_windows_refused_folders(self):
        system = support.FakeSystem(self.folder, "windows")
        base = system.env["LOCALAPPDATA"]
        for part in [r"Google\Chrome\User Data", r"Google\Chrome Beta\User Data", r"Google\Chrome SxS\User Data", r"Chromium\User Data", r"Microsoft\Edge\User Data"]:
            for suffix in ["", r"\nested"]:
                with self.assertRaises(KitError):
                    check_profile_dir(system, path_module(system).join(base, part) + suffix, {"profiles": {}})

    def test_characters_duplicates_and_link(self):
        for char in ['"', '`', '$', '%', '\\', '\n', '\t', chr(127)]:
            with self.assertRaises(KitError):
                safe_characters(self.system, str(self.folder / ("work" + char)))
        folder = str(self.folder / "work")
        with self.assertRaises(KitError):
            check_profile_dir(self.system, folder, {"profiles": {"shop": {"profile_dir": folder}}}, "work")
        target = Path(self.system.user_dir()) / ".config/google-chrome"
        target.mkdir(parents=True)
        (self.folder / "alias").symlink_to(target, target_is_directory=True)
        with self.assertRaises(KitError):
            check_profile_dir(self.system, str(self.folder / "alias"), {"profiles": {}})

    def test_linux_last_fallback_and_missing(self):
        with mock.patch.object(self.system, "is_file", side_effect=lambda value: value == "/opt/google/chrome/chrome"):
            self.assertEqual(find_chrome(self.system, {}), "/opt/google/chrome/chrome")
        self.assertIsNone(find_chrome(self.system, {}))

    def test_windows_fallbacks_and_versions(self):
        system = support.FakeSystem(self.folder, "windows")
        system.env.update({"ProgramFiles(x86)": r"D:\kit-data\programs", "LOCALAPPDATA": r"D:\kit-data\appdata"})
        binary = r"D:\kit-data\programs\Google\Chrome\Application\chrome.exe"
        account_binary = r"D:\kit-data\appdata\Google\Chrome\Application\chrome.exe"
        system.write_text(binary, "")
        system.write_text(account_binary, "")
        self.assertEqual(find_chrome(system, {}), binary)
        system.remove_file(binary)
        self.assertEqual(find_chrome(system, {}), account_binary)
        base = path_module(system).dirname(account_binary)
        for version in ["140.0.7390.54", "141.0.7390.54", "invalid"]:
            system.make_dir(path_module(system).join(base, version))
        self.assertEqual(identity(system, account_binary), ("141.0.7390.54", True))

    def test_windows_root_checkout_and_characters(self):
        system = support.FakeSystem(self.folder, "windows")
        system.write_text(r"D:\kit-data\checkout\.git", "fixture")
        for folder in ["D:\\", system.user_dir(), r"D:\kit-data\checkout\profiles\work"]:
            with self.assertRaises(KitError):
                check_profile_dir(system, folder, {"profiles": {}})
        for char in ['"', '`', '$', '%', '\n', chr(127)]:
            with self.assertRaises(KitError):
                safe_characters(system, "D:\\kit-data\\work" + char)

    def test_chrome_symlink_destination_characters(self):
        target = self.folder / "unsafe$"
        target.write_text("")
        alias = self.folder / "alias"
        alias.symlink_to(target)
        with self.assertRaises(KitError):
            find_chrome(self.system, {}, str(alias))


class CustomRootRefusalTests(support.KitTestCase):
    def refused(self, system, folder):
        with self.assertRaises(KitError) as caught:
            check_profile_dir(system, folder, {"profiles": {}})
        self.assertEqual(caught.exception.exit_code, 8)

    def test_custom_xdg_config_home_default_folders(self):
        other = str(self.folder / "elsewhere")
        self.system.env["XDG_CONFIG_HOME"] = other
        for part in ("google-chrome", "google-chrome-beta", "google-chrome-unstable", "chromium", "google-chrome/Default"):
            with self.subTest(part=part):
                self.refused(self.system, other + "/" + part)

    def test_ancestors_of_default_folders_refused(self):
        user = self.system.user_dir()
        self.refused(self.system, user + "/.config")
        other = str(self.folder / "elsewhere")
        self.system.env["XDG_CONFIG_HOME"] = other
        self.refused(self.system, other)
        self.refused(self.system, user + "/snap")
        self.refused(self.system, user + "/Library/Application Support/Google")

    def test_cli_review_reproductions(self):
        other = str(self.folder / "elsewhere")
        self.system.env["XDG_CONFIG_HOME"] = other
        for target in (other + "/google-chrome", str(Path(self.system.user_dir()) / ".config")):
            with self.subTest(target=target):
                self.assertEqual(self.run_cli(["add", "yn", "--profile-dir", target])[0], 8)
        self.assertNotIn("yn", config_names(self))

    def test_windows_userprofile_and_custom_local_app_data(self):
        system = support.FakeSystem(self.folder, "windows")
        system.env["LOCALAPPDATA"] = r"D:\Redirected\Local"
        user = system.user_dir()
        for folder in (r"D:\Redirected\Local\Google\Chrome\User Data", r"D:\Redirected\Local", path_module(system).join(user, "AppData", "Local", "Google", "Chrome", "User Data"), path_module(system).join(user, "AppData", "Local", "Google")):
            with self.subTest(folder=folder):
                self.refused(system, folder)

    def test_ordinary_dedicated_folder_still_allowed(self):
        self.system.env["XDG_CONFIG_HOME"] = str(self.folder / "elsewhere")
        folder = str(self.folder / "dedicated" / "work")
        self.assertEqual(check_profile_dir(self.system, folder, {"profiles": {}}), folder)


def config_names(case):
    from cdp_setup_kit import config
    from cdp_setup_kit.paths import locations
    return list(config.load(case.system, locations(case.system).config)["profiles"])

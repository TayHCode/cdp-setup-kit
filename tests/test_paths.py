from tests import support

from cdp_setup_kit.paths import locations, path_module


class PathsTests(support.KitTestCase):
    def test_macos_defaults_ignore_xdg(self):
        system = support.FakeSystem(self.folder, "macos")
        del system.env["CDP_SETUP_KIT_DIR"]
        paths = locations(system)
        base = system.user_dir() + "/Library/Application Support/cdp-setup-kit"
        self.assertEqual(paths.config, base + "/config.json")
        self.assertEqual(paths.profiles, base + "/profiles")
        self.assertEqual(paths.state, base + "/state")
        self.assertEqual(paths.startup, system.user_dir() + "/Library/LaunchAgents")

    def test_macos_override_precedence_keeps_launchagents_location(self):
        system = support.FakeSystem(self.folder, "macos")
        first = locations(system)
        self.assertEqual(first.config, str(self.folder / "kit/config.json"))
        paths = locations(system, str(self.folder / "override"))
        self.assertEqual(paths.config, str(self.folder / "override/config.json"))
        self.assertEqual(paths.profiles, str(self.folder / "override/profiles"))
        self.assertEqual(paths.state, str(self.folder / "override/state"))
        self.assertEqual(paths.startup, first.startup)

    def test_linux_defaults(self):
        self.system.env = {}
        paths = locations(self.system)
        user = self.system.user_dir()
        self.assertEqual(paths.config, user + "/.config/cdp-setup-kit/config.json")
        self.assertEqual(paths.profiles, user + "/.local/share/cdp-setup-kit/profiles")
        self.assertEqual(paths.state, user + "/.local/state/cdp-setup-kit")
        self.assertEqual(paths.startup, user + "/.config/autostart")

    def test_linux_variables(self):
        del self.system.env["CDP_SETUP_KIT_DIR"]
        paths = locations(self.system)
        for attr, key, tail in [("config", "XDG_CONFIG_HOME", "/cdp-setup-kit/config.json"),
                                ("profiles", "XDG_DATA_HOME", "/cdp-setup-kit/profiles"),
                                ("state", "XDG_STATE_HOME", "/cdp-setup-kit")]:
            self.assertEqual(getattr(paths, attr), self.system.env[key] + tail)
        self.assertEqual(paths.startup, self.system.env["XDG_CONFIG_HOME"] + "/autostart")

    def test_windows_defaults_and_variables(self):
        system = support.FakeSystem(self.folder, "windows")
        system.env = {}
        path = path_module(system)
        paths = locations(system)
        self.assertEqual(paths.config, path.join(system.user_dir(), "AppData", "Roaming", "cdp-setup-kit", "config.json"))
        self.assertEqual(paths.profiles, path.join(system.user_dir(), "AppData", "Local", "cdp-setup-kit", "profiles"))
        system.env = {"APPDATA": r"D:\kit-data\roaming", "LOCALAPPDATA": r"D:\kit-data\appdata"}
        paths = locations(system)
        self.assertEqual(paths.config, r"D:\kit-data\roaming\cdp-setup-kit\config.json")
        self.assertEqual(paths.state, r"D:\kit-data\appdata\cdp-setup-kit\state")
        self.assertEqual(paths.startup, "Task Scheduler (cdp-setup-kit-NAME)")

    def test_override_precedence(self):
        first = locations(self.system)
        other = locations(self.system, str(self.folder / "override"))
        self.assertEqual(other.config, str(self.folder / "override" / "config.json"))
        self.assertEqual(other.profiles, str(self.folder / "override" / "profiles"))
        self.assertEqual(other.state, str(self.folder / "override" / "state"))
        self.assertEqual(other.startup, first.startup)

    def test_windows_override_precedence(self):
        system = support.FakeSystem(self.folder, "windows")
        system.env["CDP_SETUP_KIT_DIR"] = r"D:\kit-data\env"
        self.assertEqual(locations(system).config, r"D:\kit-data\env\config.json")
        paths = locations(system, r"D:\kit-data\option")
        self.assertEqual(paths.config, r"D:\kit-data\option\config.json")
        self.assertEqual(paths.profiles, r"D:\kit-data\option\profiles")
        self.assertEqual(paths.state, r"D:\kit-data\option\state")
        self.assertEqual(paths.startup, "Task Scheduler (cdp-setup-kit-NAME)")

from tests import support

from cdp_setup_kit import config
from cdp_setup_kit.constants import LOOPBACK
from cdp_setup_kit.paths import locations


class WizardTests(support.KitTestCase):
    def setUp(self):
        super().setUp()
        self.binary = str(self.folder / "chrome")
        self.system.write_text(self.binary, "")
        self.system.env["CDP_SETUP_KIT_CHROME"] = self.binary
        self.system.runs[(self.binary, "--version")] = (0, "Google Chrome 141.0.7390.54", "")
        self.paths = locations(self.system)
        self.system.calls.clear()

    def test_scripted_answers(self):
        self.system.answers = ["y", "work", "9223", "n"]
        code, out, _ = self.run_cli(["init"])
        self.assertEqual(code, 0)
        self.assertIn("SECURITY NOTICE", out)
        self.assertIn("startup enable work", out)
        self.assertEqual(config.load(self.system, self.paths.config)["profiles"]["work"]["port"], 9223)
        self.assertFalse(self.system.exists(self.paths.startup))
        self.assertFalse(any(call[0] == "spawn" for call in self.system.calls))

    def test_yes_no_terminal(self):
        self.system.is_interactive = False
        self.assertEqual(self.run_cli(["init"])[0], 2)
        self.assertEqual(self.run_cli(["init", "--yes", "--no-open"])[0], 0)
        self.assertIn("main", config.load(self.system, self.paths.config)["profiles"])
        self.assertFalse(any(call[0] == "ask" for call in self.system.calls))

    def test_declining_no_write(self):
        self.system.answers = ["n"]
        self.assertEqual(self.run_cli(["init"])[0], 0)
        self.assertFalse(self.system.exists(self.paths.config))
        self.assertFalse(any(call[0] in {"write_text", "make_dir", "spawn"} for call in self.system.calls))

    def test_second_run_unchanged(self):
        self.run_cli(["init", "--yes", "--no-open", "--name", "work", "--port", "9223"])
        before = config.load(self.system, self.paths.config)
        self.run_cli(["init", "--yes", "--no-open", "--name", "work", "--port", "9222"])
        self.run_cli(["init", "--yes", "--no-open"])
        self.assertEqual(config.load(self.system, self.paths.config), before)
        self.assertFalse(self.system.exists(self.paths.startup))

    def test_open_after_consent(self):
        def answer():
            self.system.probes[9222] = {"kind": "valid", "data": support.cdp_body()}
        self.system.spawn_hook = answer
        self.assertEqual(self.run_cli(["init", "--yes"])[0], 0)
        self.assertEqual(len([call for call in self.system.calls if call[0] == "spawn"]), 1)


    def test_failed_init_preserves_existing_config_and_backup(self):
        self.run_cli(["init", "--yes", "--no-open", "--name", "work", "--port", "9333"])
        before = self.system.read_text(self.paths.config)
        backup = self.paths.config + ".bak"
        self.system.write_text(backup, "retained backup")
        self.system.calls.clear()
        code, out, err = self.run_cli(["init", "--yes", "--name", "new", "--port", "9334"])
        self.assertEqual(code, 5)
        self.assertIn("was not recorded", out)
        self.assertNotIn("Added profile", out)
        self.assertEqual(self.system.read_text(self.paths.config), before)
        self.assertEqual(self.system.read_text(backup), "retained backup")
        self.assertNotIn("new", config.load(self.system, self.paths.config)["profiles"])

    def test_no_desktop_init_has_no_disk_changes(self):
        self.system.env.pop("DISPLAY")
        code, out, err = self.run_cli(["init", "--yes", "--name", "work", "--port", "9333"])
        self.assertEqual(code, 5)
        self.assertIn("no desktop session", err)
        self.assertIn("--headless", err)
        self.assertIn("--port 9333", err)
        self.assertIn(self.system.env["CDP_SETUP_KIT_DIR"], err)
        self.assertNotIn("Added profile", out)
        self.assertFalse(any(call[0] in {"write_text", "make_dir", "spawn"} for call in self.system.calls))
        self.assertFalse(self.system.exists(self.paths.config))

    def test_no_open_reports_defaults_and_busy_explicit_port(self):
        self.system.busy.update({9222, 9223, 9224, 9225})
        code, out, err = self.run_cli(["init", "--yes", "--no-open"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn('Recorded profile "main"', out)
        self.assertIn("port:         9226", out)
        self.assertIn(self.paths.profiles + "/main", out)
        self.assertIn("Chrome was not opened", out)
        self.assertNotIn("Sign in to your accounts in that window", out)
        self.system.busy.add(9333)
        self.assertIn("warning: port 9333 is busy", self.run_cli(["init", "--yes", "--no-open", "--name", "busy", "--port", "9333"])[1])

    def test_reinit_is_quiet_and_notice_is_explicit(self):
        args = ["init", "--yes", "--no-open", "--name", "work", "--port", "9333"]
        self.assertIn("SECURITY NOTICE", self.run_cli(args)[1])
        before = self.system.read_text(self.paths.config)
        self.system.calls.clear()
        code, out, err = self.run_cli(args)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.count("already set up; nothing changed"), 1)
        for text in ["SECURITY NOTICE", "Profile recorded", "Recorded profile"]:
            self.assertNotIn(text, out)
        self.assertFalse(any(call[0] in {"write_text", "make_dir", "spawn"} for call in self.system.calls))
        self.assertEqual(self.system.read_text(self.paths.config), before)
        self.assertIn("SECURITY NOTICE", self.run_cli(args + ["--notice"])[1])
        self.assertIn("SECURITY NOTICE", self.run_cli(["init", "--yes", "--no-open", "--name", "second", "--port", "9334"])[1])

    def test_missing_chrome_points_to_exact_testing_commands(self):
        self.system.remove_file(self.binary)
        code, out, err = self.run_cli(["init", "--yes", "--no-open"])
        self.assertEqual(code, 5)
        self.assertIn("Chrome for Testing", err)
        self.assertIn("README.md#install-chrome-on-linux", err)
        self.assertIn("exact download/extract/chmod commands", err)

    def test_result_first_and_quiet_only_result(self):
        for quiet, name, port in [(False, "first", "9530"), (True, "second", "9531")]:
            args = ["init", "--yes", "--no-open", "--name", name, "--port", port] + (["--quiet"] if quiet else [])
            code, out, err = self.run_cli(args)
            self.assertEqual((code, err), (0, ""))
            self.assertTrue(out.startswith('Profile "' + name + '" recorded; Chrome was not opened: '))
            self.assertEqual(len(out.splitlines()) == 1, quiet)
            if not quiet:
                self.assertIn("SECURITY NOTICE", out)
                self.assertIn("MCP", out)
        self.assertEqual(self.run_cli(["init", "--quiet"])[0], 2)


class ExistingEndpointTests(support.KitTestCase):
    def test_reachable_endpoint_needs_no_chrome_or_local_profile(self):
        with support.FakeCdpServer() as server:
            address = 'http://' + LOOPBACK + ':' + str(server.port)
            code, out, err = self.run_cli(['init', '--yes', '--no-open', '--endpoint', address])
            self.assertEqual((code, err), (0, ''))
            self.assertIn(address, out)
            self.assertIn('No local profile was created', out)
            self.assertIn('connectOverCDP', out)
            self.assertEqual(server.requests, ['/json/version'])
        self.assertFalse(any(c[0] in {'write_text', 'make_dir', 'spawn', 'run'} for c in self.system.calls))
        self.assertFalse(self.system.exists(locations(self.system).config))

    def test_unreachable_or_non_cdp_endpoint_fails_without_changes(self):
        from unittest.mock import patch
        for kind in ('refused', 'not_cdp'):
            with self.subTest(kind=kind), patch.object(self.system, 'cdp_at', return_value={'kind': kind}):
                code, out, err = self.run_cli(['init', '--yes', '--endpoint', 'http://localhost:9333'])
                self.assertEqual(code, 5)
                self.assertIn('CDP endpoint', err)
                self.assertNotIn('No local profile was created', out)
        self.assertFalse(self.system.exists(locations(self.system).config))

    def test_external_endpoint_rejects_local_profile_options(self):
        for option in (['--name', 'work'], ['--port', '9333'], ['--chrome', 'chrome']):
            with self.subTest(option=option):
                code, _, err = self.run_cli(['init', '--yes', '--endpoint', 'http://localhost:9333', *option])
                self.assertEqual(code, 2)
                self.assertIn('cannot combine --endpoint', err)
        self.assertFalse(self.system.exists(locations(self.system).config))

    def test_external_endpoint_consent_and_quiet(self):
        from unittest.mock import patch
        with patch.object(self.system, 'cdp_at', return_value={'kind': 'valid'}) as probe:
            self.system.answers = ['n']
            code, out, _ = self.run_cli(['init', '--endpoint', 'http://localhost:9333'])
            self.assertEqual(code, 0)
            self.assertIn('No changes made', out)
            probe.assert_not_called()
            self.assertEqual(self.run_cli(['init', '--quiet', '--endpoint', 'http://localhost:9333'])[0], 2)
            code, out, _ = self.run_cli(['init', '--yes', '--quiet', '--endpoint', 'http://localhost:9333'])
            self.assertEqual(code, 0)
            self.assertNotIn('SECURITY NOTICE', out)
            self.assertIn('http://localhost:9333', out)

    def test_external_endpoint_preserves_existing_config_and_backup(self):
        from unittest.mock import patch
        self.run_cli(['add', 'work', '--port', '9333'])
        paths = locations(self.system)
        before = self.system.read_text(paths.config)
        self.system.write_text(paths.config + '.bak', 'existing backup')
        self.system.calls.clear()
        with patch.object(self.system, 'cdp_at', return_value={'kind': 'valid'}):
            self.assertEqual(self.run_cli(['init', '--yes', '--endpoint', 'http://localhost:9334'])[0], 0)
        self.assertEqual(self.system.read_text(paths.config), before)
        self.assertEqual(self.system.read_text(paths.config + '.bak'), 'existing backup')
        self.assertFalse(any(c[0] in {'write_text', 'make_dir', 'spawn', 'run'} for c in self.system.calls))

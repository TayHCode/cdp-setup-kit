from tests import support
import os
import socket
from unittest import mock

from cdp_setup_kit.constants import LOOPBACK
from cdp_setup_kit.errors import RealActionForbidden
from cdp_setup_kit.system import RealSystem


class SystemTests(support.KitTestCase):
    def test_new_windows_profile_grants_its_user_not_elevated_owner(self):
        system = RealSystem()
        system.platform = "windows"
        folder = str(self.folder / "profile")
        sid = "S-1-5-21-123-456-789-1001"
        with mock.patch.object(system, "make_dir") as mkdir, mock.patch.object(system, "windows_account", return_value=sid), mock.patch.object(system, "run", return_value=(0, "", "")) as run:
            system.make_profile_dir(folder)
            mkdir.assert_called_once_with(folder, 0o700)
            run.assert_called_once_with(["icacls", folder, "/grant:r", "*" + sid + ":(OI)(CI)F"])
        with mock.patch.object(system, "make_dir"), mock.patch.object(system, "windows_account", return_value=sid), mock.patch.object(system, "run", return_value=(1, "", "")), self.assertRaises(OSError):
            system.make_profile_dir(folder)

    def test_windows_identity_uses_sid_and_rejects_bad_output(self):
        system = RealSystem()
        system.env.update(USERDOMAIN="wrong", USERNAME="wrong")
        with mock.patch.object(system, "run", return_value=(0, '"PC\\operator","S-1-5-21-123-456-789-1001"\n', "")) as run:
            self.assertEqual(system.windows_account(), "S-1-5-21-123-456-789-1001")
            run.assert_called_once_with(["whoami", "/user", "/fo", "csv", "/nh"])
        for result in [(1, "", ""), (0, "malformed", ""), (0, '"user","wrong"', "")]:
            with mock.patch.object(system, "run", return_value=result), self.assertRaises(OSError):
                system.windows_account()

    def test_darwin_detection_and_detached_launch_options(self):
        with mock.patch("sys.platform", "darwin"):
            system = RealSystem()
        self.assertEqual(system.platform, "macos")
        with mock.patch("subprocess.Popen") as spawn:
            with self.assertRaises(RealActionForbidden):
                system.spawn_detached(["fake"])
            spawn.assert_not_called()

            system.env.pop("CDP_SETUP_KIT_FORBID_REAL", None)
            system.spawn_detached(["fake"])
            self.assertTrue(spawn.call_args.kwargs["start_new_session"])

    def test_desktop_detection_for_linux_and_macos_gui_domain(self):
        system = RealSystem()
        system.platform = "linux"
        for env, expected in [({}, False), ({"DISPLAY": ":1"}, True), ({"WAYLAND_DISPLAY": "wayland-1"}, True)]:
            system.env = env
            self.assertEqual(system.has_desktop_session(), expected)
        system.platform = "macos"
        for code, expected in [(0, True), (1, False)]:
            with mock.patch.object(system, "run", return_value=(code, "", "")) as run, mock.patch("os.getuid", return_value=123):
                self.assertEqual(system.has_desktop_session(), expected)
                run.assert_called_once_with(["launchctl", "print", "gui/123"])

    def test_windows_ssh_detection_does_not_call_native_gui_api(self):
        system = RealSystem()
        system.platform = "windows"
        for variable in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"):
            system.env = {variable: "present", "SESSIONNAME": "Console"}
            self.assertFalse(system.has_desktop_session())

    def test_windows_desktop_requires_interactive_nonzero_session(self):
        system = RealSystem()
        system.platform = "windows"
        system.env = {}
        for result, expected in [((0, "True\n", ""), True), ((0, "False\n", ""), False), ((1, "", ""), False)]:
            with mock.patch.object(system, "run", return_value=result) as run:
                self.assertEqual(system.has_desktop_session(), expected)
                self.assertIn("SessionId -gt 0", run.call_args.args[0][-1])
                self.assertIn("UserInteractive", run.call_args.args[0][-1])

    def test_profile_deletion_tolerates_only_disappearing_children(self):
        system = RealSystem(str(self.folder))
        root = str(self.folder / "profile")
        def rmtree(path, onerror):
            onerror(None, path + "/temporary-child", (FileNotFoundError, FileNotFoundError(), None))
        with mock.patch("shutil.rmtree", side_effect=rmtree):
            system.remove_tree(root)
        for failure, target in [(PermissionError(), root + "/child"), (FileNotFoundError(), root)]:
            def rmtree(path, onerror):
                onerror(None, target, (type(failure), failure, None))
            with mock.patch("shutil.rmtree", side_effect=rmtree), self.assertRaises(type(failure)):
                system.remove_tree(root)

    def test_http_modes(self):
        system = RealSystem()
        for mode, expected in [("valid", "valid"), ("not_json", "not_cdp"), ("http_500", "not_cdp"), ("slow", "not_cdp")]:
            with self.subTest(mode=mode), support.FakeCdpServer(mode) as server:
                self.assertEqual(system.cdp_version(server.port)["kind"], expected)
                self.assertEqual(server.requests, ["/json/version"])
                self.assertFalse(system.can_bind(server.port))

    def test_closed_port(self):
        with socket.socket() as sock:
            sock.bind((LOOPBACK, 0))
            port = sock.getsockname()[1]
        system = RealSystem()
        self.assertEqual(system.cdp_version(port)["kind"], "refused")
        self.assertTrue(system.can_bind(port))

    def test_guard_processes(self):
        system = RealSystem()
        with mock.patch("subprocess.run") as run, mock.patch("subprocess.Popen") as spawn:
            for action in [lambda: system.run(["fake"]), lambda: system.spawn_detached(["fake"])]:
                with self.assertRaises(RealActionForbidden):
                    action()
            run.assert_not_called()
            spawn.assert_not_called()

    def test_guard_writes_and_links(self):
        root = self.folder / "allowed"
        root.mkdir()
        system = RealSystem(str(root))
        outside = self.folder / "outside"
        for action in [lambda: system.write_text(str(outside), "x"), lambda: system.make_dir(str(outside)),
                       lambda: system.remove_file(str(outside)), lambda: system.remove_tree(str(outside))]:
            with self.assertRaises(RealActionForbidden):
                action()
        (root / "link").symlink_to(self.folder, target_is_directory=True)
        with self.assertRaises(RealActionForbidden):
            system.write_text(str(root / "link" / "outside"), "x")
        system.write_text(str(root / "config.json"), "old")
        system.write_text(str(root / "config.json"), "new")
        self.assertEqual((root / "config.json").read_text(), "new")
        self.assertEqual(system.file_mode(str(root / "config.json")), 0o600)
        self.assertFalse(outside.exists())

    def test_fake_env_isolated(self):
        self.assertNotEqual(self.system.env, dict(os.environ))
        with self.assertRaises(AssertionError):
            self.system.write_text("/srv/kit-data/outside", "x")

    def test_listener_probe_ignores_time_wait_and_checks_accepting_socket(self):
        system = RealSystem()
        # A stale TCP tuple would reject bind even when reuse is requested.
        # The probe must never bind, so either reusable or non-reusable old
        # sockets in TIME-WAIT are irrelevant.
        with mock.patch('socket.create_connection', side_effect=ConnectionRefusedError), mock.patch('socket.socket') as factory:
            self.assertTrue(system.can_bind(9510))
            factory.assert_not_called()
        with mock.patch('socket.create_connection') as connect, mock.patch('socket.socket') as factory:
            self.assertFalse(system.can_bind(9510))
            connect.assert_called_once_with((LOOPBACK, 9510), timeout=0.3)
            factory.assert_not_called()
        with mock.patch('socket.create_connection', side_effect=TimeoutError):
            self.assertTrue(system.can_bind(9510))

    def test_address_discovery_includes_existing_tailnet(self):
        import ipaddress
        system = RealSystem()
        host = str(ipaddress.IPv4Address(0x6440000a))
        with mock.patch('socket.getaddrinfo', return_value=[]), mock.patch.object(system, 'which', return_value='/test/tailscale'), mock.patch.object(system, 'run', return_value=(0, host + '\ninvalid\n', '')):
            self.assertEqual(system.non_loopback_addresses(), [host])

from tests import support
import xml.etree.ElementTree as ET
from unittest import mock

from cdp_setup_kit import chrome, config, startup, startup_windows
from cdp_setup_kit.constants import TASK_NAMESPACE
from cdp_setup_kit.paths import locations


class WindowsStartupTests(support.KitTestCase):
    def test_run_task_preview_running_and_foreign_refusal(self):
        self.system.runs[tuple(startup_windows.query_argv("work"))] = (0, startup_windows.task_xml(self.system, "work", self.plan.expected), "")
        self.system.calls.clear()
        self.assertIn("PREVIEW", self.run_cli(["startup", "run", "work"])[1])
        self.assertFalse(any(call[0] == "run" and call[1][0] == "powershell.exe" for call in self.system.calls))
        for feedback in ["already running", "start requested"]:
            self.system.runs[("powershell.exe",)] = (0, feedback, "")
            code, out, err = self.run_cli(["startup", "run", "work", "--apply"])
            self.assertEqual((code, err), (0, ""))
            self.assertIn(feedback, out)
        self.system.runs[tuple(startup_windows.query_argv("work"))] = (0, "<foreign/>", "")
        self.system.calls.clear()
        self.assertEqual(self.run_cli(["startup", "run", "work", "--apply"])[0], 6)
        self.assertFalse(any(call[0] == "run" and call[1][0] == "powershell.exe" for call in self.system.calls))

    def test_doctor_startup_location_has_real_name(self):
        out = self.run_cli(["doctor", "work"])[1]
        self.assertIn("Task Scheduler (cdp-setup-kit-work)", out)
        self.assertNotIn("cdp-setup-kit-NAME", out)
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
            self.system.runs[("schtasks", "/Create")] = (0, "", "")
            self.assertEqual(self.run_cli(["startup", "enable", "work", "--apply", "--force-no-desktop"])[0], 0)
            self.assertEqual(self.run_cli(["startup", "disable", "work", "--apply"])[0], 0)

    def test_security_identity_overrides_ssh_environment(self):
        self.system.env.update(USERDOMAIN="unresolvable", USERNAME="wrong")
        with mock.patch.object(self.system, "windows_account", return_value=r"PC\actual"):
            text = startup_windows.task_xml(self.system, "work", self.plan.expected)
        root = ET.fromstring(text)
        ns = {"t": TASK_NAMESPACE}
        self.assertEqual(root.findtext("t:Principals/t:Principal/t:UserId", namespaces=ns), r"PC\actual")
        self.assertEqual(root.findtext("t:Triggers/t:LogonTrigger/t:UserId", namespaces=ns), r"PC\actual")
        with mock.patch.object(self.system, "windows_account", side_effect=OSError()):
            self.assertEqual(self.run_cli(["startup", "enable", "work", "--apply"])[0], 6)

    def setUp(self):
        super().setUp()
        self.system = support.FakeSystem(self.folder, "windows")
        self.system.env["CDP_SETUP_KIT_DIR"] = r"D:\kit-data"
        self.binary = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.system.write_text(self.binary, "")
        self.assertEqual(self.run_cli(["add", "work", "--chrome", self.binary])[0], 0)
        self.paths = locations(self.system)
        self.data = config.load(self.system, self.paths.config)
        self.plan = startup.build_plan(self.system, self.paths, self.data, "work", "enable")
        self.system.calls.clear()

    def set_query(self, text):
        self.system.runs[tuple(startup_windows.query_argv("work"))] = (0, text, "")

    def test_xml_and_preview_goldens(self):
        text = self.plan.files[0][1]
        self.assertEqual(text, (support.ROOT / "tests/golden/windows-task.xml.txt").read_text())
        self.assertEqual(ET.fromstring(text).tag, "{" + TASK_NAMESPACE + "}Task")
        self.assertEqual(startup.preview(self.system, self.plan) + "\n", (support.ROOT / "tests/golden/startup-preview-windows.txt").read_text())
        self.assertEqual(self.run_cli(["startup", "enable", "work"])[0], 0)
        self.assertFalse(any(call[0] in {"run", "write_text", "make_dir", "remove_file"} for call in self.system.calls))

    def test_escaping(self):
        self.system.env["USERNAME"] = "operator&<"
        text = startup_windows.task_xml(self.system, "work", chrome.build_chrome_argv(self.binary, r"D:\kit-data\work&<", 9222))
        self.assertIn("&amp;&lt;", text)
        self.assertIsNotNone(ET.fromstring(text))

    def test_apply_exact_commands_and_encoding(self):
        self.system.runs[("schtasks", "/Create")] = (0, "", "")
        self.assertEqual(self.run_cli(["startup", "enable", "work", "--apply"])[0], 0)
        self.assertEqual([call[1] for call in self.system.calls if call[0] == "run"], self.plan.commands)
        target, text, codec, _ = self.plan.files[0]
        self.assertEqual(self.system.read_text(target, codec), text)
        self.assertTrue(self.system._disk(target).read_bytes().startswith(b"\xff\xfe"))
        self.assertNotIn("/F", self.plan.commands[1])

    def test_query_declaration_and_idempotence(self):
        for declaration in ["", '<?xml version="1.0" encoding="utf_16"?>\n']:
            self.set_query(declaration + self.plan.files[0][1])
            self.system.calls.clear()
            self.assertIn("already enabled, unchanged", self.run_cli(["startup", "enable", "work", "--apply"])[1])
            self.assertFalse(any(call[0] == "write_text" for call in self.system.calls))
            self.assertEqual(len([call for call in self.system.calls if call[0] == "run"]), 1)

    def test_force_only_owned_stale(self):
        text = self.plan.files[0][1].replace("--remote-debugging-port=9222", "--remote-debugging-port=9223")
        self.set_query(text)
        self.system.runs[("schtasks", "/Create")] = (0, "", "")
        self.assertEqual(self.run_cli(["startup", "enable", "work", "--apply"])[0], 0)
        self.assertEqual([call[1] for call in self.system.calls if call[0] == "run"][-1], self.plan.stale_command)

    def test_foreign_no_mutation(self):
        self.set_query("<Task />")
        for action in ["enable", "disable"]:
            self.system.calls.clear()
            self.assertEqual(self.run_cli(["startup", action, "work", "--apply"])[0], 6)
            self.assertFalse(any(call[0] in {"write_text", "remove_file"} for call in self.system.calls))
            self.assertEqual([call[1] for call in self.system.calls if call[0] == "run"], [startup_windows.query_argv("work")])

    def test_refusal_and_disable(self):
        code, _, err = self.run_cli(["startup", "enable", "work", "--apply"])
        self.assertEqual(code, 6)
        self.assertIn("administrator terminal", err)
        self.assertIn(self.system.join_windows_args(self.plan.commands[1]), err)
        self.set_query(self.plan.files[0][1])
        self.system.runs[("schtasks", "/Delete")] = (0, "", "")
        self.assertEqual(self.run_cli(["startup", "disable", "work", "--apply"])[0], 0)
        self.assertFalse(self.system.exists(self.plan.files[0][0]))
        self.assertEqual([call[1] for call in self.system.calls if call[0] == "run"][-1], startup_windows.delete_argv("work"))

    def test_disable_preview_and_absent(self):
        self.assertEqual(self.run_cli(["startup", "disable", "work"])[0], 0)
        self.assertFalse(any(call[0] in {"run", "write_text", "remove_file"} for call in self.system.calls))
        self.assertIn("nothing to remove", self.run_cli(["startup", "disable", "work", "--apply"])[1])
        self.assertEqual([call[1] for call in self.system.calls if call[0] == "run"], [startup_windows.query_argv("work")])

    def test_source_marker_and_task_settings(self):
        text = self.plan.files[0][1]
        self.set_query(text.replace("<Source>cdp-setup-kit</Source>", "<Source>unfamiliar</Source>"))
        self.assertEqual(self.run_cli(["startup", "enable", "work", "--apply"])[0], 6)
        root = ET.fromstring(text)
        ns = {"t": TASK_NAMESPACE}
        for branch, value in [("Principals/Principal/LogonType", "InteractiveToken"), ("Principals/Principal/RunLevel", "LeastPrivilege"), ("Settings/ExecutionTimeLimit", "PT0S"), ("Settings/MultipleInstancesPolicy", "IgnoreNew"), ("Triggers/LogonTrigger/UserId", r"PC\operator")]:
            self.assertEqual(root.findtext("/".join("t:" + part for part in branch.split("/")), namespaces=ns), value)

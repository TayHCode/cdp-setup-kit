import shlex
import unittest

from tests import support

from cdp_setup_kit import chrome, config, startup, startup_linux
from cdp_setup_kit.paths import locations


class LinuxStartupTests(support.KitTestCase):
    def setUp(self):
        super().setUp()
        binary = str(self.folder / "chrome with space")
        self.system.write_text(binary, "")
        self.run_cli(["add", "work", "--chrome", binary])
        self.paths = locations(self.system)
        self.data = config.load(self.system, self.paths.config)
        self.target = startup_linux.entry_path(self.system, self.paths, "work")
        self.system.calls.clear()

    def test_no_desktop_preview_refusal_override_and_disable(self):
        from unittest import mock
        with mock.patch.object(self.system, "has_desktop_session", return_value=False):
            self.system.calls.clear()
            code, out, err = self.run_cli(["startup", "enable", "work"])
            self.assertEqual((code, err), (0, ""))
            self.assertIn("This machine has no desktop session: a visible window cannot open here", out)
            self.assertIn("use headless mode / run at the desktop", out)
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

    def test_golden_text(self):
        text = startup_linux.desktop_text("work", chrome.build_chrome_argv("/opt/google/chrome/chrome", "/srv/kit-data/profiles/work", 9222))
        self.assertEqual(text, (support.ROOT / "tests/golden/linux-autostart.desktop.txt").read_text())
        plan = startup.StartupPlan("work", "enable", files=[("/srv/kit-data/config/autostart/cdp-setup-kit-work.desktop", text, "utf-8", 0o644)], effect='the "work" Chrome window opens each time you sign in.')
        self.assertEqual(startup.preview(self.system, plan) + "\n", (support.ROOT / "tests/golden/startup-preview-linux.txt").read_text())

    def test_preview_and_apply_same_plan(self):
        plan = startup.build_plan(self.system, self.paths, self.data, "work", "enable")
        self.assertIn('"' + str(self.folder / "chrome with space") + '"', plan.files[0][1])
        self.assertEqual(self.run_cli(["startup", "enable", "work"])[0], 0)
        self.assertFalse(any(call[0] in {"write_text", "make_dir", "run", "remove_file"} for call in self.system.calls))
        self.assertEqual(self.run_cli(["startup", "enable", "work", "--apply"])[0], 0)
        self.assertEqual(self.system.read_text(self.target), plan.files[0][1])
        self.assertEqual(self.system.file_mode(self.target), 0o644)
        self.system.calls.clear()
        self.assertIn("already enabled, unchanged", self.run_cli(["startup", "enable", "work", "--apply"])[1])
        self.assertFalse(any(call[0] == "write_text" for call in self.system.calls))

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
        self.assertEqual(self.run_cli(["startup", "enable", "work", "--apply"])[0], 0)
        self.system.calls.clear()
        code, out, _ = self.run_cli(["startup", "enable", "work"])
        self.assertEqual(code, 0)
        self.assertIn("already enabled, unchanged", out)
        self.assertNotIn("Effect:", out)
        self.assertNotIn("To do it:", out)
        self.assertNotIn("To undo it:", out)
        self.assertFalse(any(call[0] in {"write_text", "make_dir", "run", "remove_file"} for call in self.system.calls))

    def test_stale_after_port_change(self):
        self.run_cli(["startup", "enable", "work", "--apply"])
        self.assertIn("old port", self.run_cli(["set-port", "work", "9223", "--apply"])[1])
        self.assertIn("stale", self.run_cli(["startup", "status"])[1])
        self.assertEqual(self.run_cli(["startup", "enable", "work", "--apply"])[0], 0)
        self.assertIn("enabled", self.run_cli(["startup", "status", "work"])[1])

    def test_disable_owned_only(self):
        other = self.paths.startup + "/other.desktop"
        self.system.write_text(other, "unfamiliar")
        self.run_cli(["startup", "enable", "work", "--apply"])
        self.run_cli(["startup", "disable", "work"])
        self.assertTrue(self.system.exists(self.target))
        self.run_cli(["startup", "disable", "work", "--apply"])
        self.assertFalse(self.system.exists(self.target))
        self.assertEqual(self.system.read_text(other), "unfamiliar")
        self.assertIn("nothing to remove", self.run_cli(["startup", "disable", "work", "--apply"])[1])

    def test_foreign_entry_untouched(self):
        self.system.write_text(self.target, "unfamiliar")
        for args in [["startup", "enable", "work"], ["startup", "disable", "work", "--apply"], ["remove", "work", "--apply"]]:
            self.assertEqual(self.run_cli(args)[0], 6)
            self.assertEqual(self.system.read_text(self.target), "unfamiliar")
            self.assertIn("work", config.load(self.system, self.paths.config)["profiles"])

    def test_disable_does_not_require_working_chrome(self):
        self.run_cli(["startup", "enable", "work", "--apply"])
        self.data["chrome_path"] = str(self.folder / 'unsafe$')
        config.save(self.system, self.paths.config, self.data)
        self.assertEqual(self.run_cli(["list", "--no-check"])[0], 0)
        self.assertEqual(self.run_cli(["startup", "disable", "work", "--apply"])[0], 0)
        self.assertFalse(self.system.exists(self.target))

    def test_dangling_symlink_is_foreign_and_kept(self):
        import os
        self.system.make_dir(self.paths.startup)
        os.symlink(str(self.folder / "nowhere"), self.target)
        self.assertIn("foreign", self.run_cli(["startup", "status", "work"])[1])
        for args in [["startup", "enable", "work", "--apply"], ["startup", "disable", "work", "--apply"]]:
            self.assertEqual(self.run_cli(args)[0], 6)
            self.assertTrue(os.path.islink(self.target))
            self.assertEqual(os.readlink(self.target), str(self.folder / "nowhere"))

    def test_foreign_entry_remove_prints_no_removal_banner(self):
        self.system.write_text(self.target, "unfamiliar")
        code, out, _ = self.run_cli(["remove", "work", "--apply"])
        self.assertEqual(code, 6)
        self.assertNotIn("Removing", out)

    def test_set_port_to_same_port_is_unchanged(self):
        out = self.run_cli(["set-port", "work", "9222", "--apply"])[1]
        self.assertIn("unchanged", out)
        self.assertNotIn("->", out)

    def test_startup_preview_without_chrome_has_no_effect_and_apply_refuses(self):
        binary = self.data["chrome_path"]
        self.system.remove_file(binary)
        self.system.calls.clear()
        code, out, err = self.run_cli(["startup", "enable", "work"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Preview only: Chrome is not installed", out)
        self.assertIn(binary, out)
        self.assertFalse(any(call[0] in {"write_text", "make_dir", "spawn", "remove_file", "run"} for call in self.system.calls))
        self.assertEqual(self.run_cli(["startup", "enable", "work", "--apply"])[0], 5)
        self.assertFalse(self.system.exists(self.target))



def desktop_split(exec_line):
    """Desktop Entry Specification: reserved characters only inside double quotes; backslash escapes inside them."""
    words, current, quoted, started, index = [], "", False, False, 0
    while index < len(exec_line):
        char = exec_line[index]
        if quoted:
            if char == "\\":
                index += 1
                current += exec_line[index]
            elif char == '"':
                quoted = False
            else:
                current += char
        elif char == '"':
            quoted, started = True, True
        elif char == " ":
            if started or current:
                words.append(current)
            current, started = "", False
        else:
            if char in "\t\n'><~|&;$*?#()`\\":
                raise ValueError("unquoted reserved character " + repr(char))
            current += char
        index += 1
    if quoted:
        raise ValueError("unterminated quote")
    if started or current:
        words.append(current)
    return words


def systemd_split(exec_line):
    """systemd ExecStart-style: quotes group, a lone ';' separates commands, '$' and '%' expand."""
    words = shlex.split(exec_line, posix=True)
    if ";" in words:
        raise ValueError("command separator")
    if any("$" in word or "%" in word for word in words):
        raise ValueError("expansion")
    return words


class DesktopQuotingTests(unittest.TestCase):
    PATHS = ["/srv/o'neil/chrome", "/tmp/a;b&c/p", "/tmp/a#(b)/p", "/tmp/a b/p", "/tmp/<x>|y/p", "/tmp/s*?~/p", "/tmp/plain/p", "/tmp/tab\there/p"]

    def exec_line(self, text):
        return [line for line in text.splitlines() if line.startswith("Exec=")][0][len("Exec="):]

    def test_special_characters_round_trip(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                argv = chrome.build_chrome_argv("/opt/google/chrome/chrome", path, 9222)
                line = self.exec_line(startup_linux.desktop_text("work", argv))
                self.assertEqual(desktop_split(line), argv)
                if "\t" not in path:
                    self.assertEqual(systemd_split(line), argv)

    def test_apostrophe_review_reproduction(self):
        argv = chrome.build_chrome_argv("/opt/google/chrome/chrome", "/tmp/o'neil", 9222)
        line = self.exec_line(startup_linux.desktop_text("work", argv))
        self.assertIn('"--user-data-dir=/tmp/o\'neil"', line)
        self.assertEqual(shlex.split(line), argv)

    def test_plain_arguments_stay_unquoted(self):
        line = self.exec_line(startup_linux.desktop_text("work", chrome.build_chrome_argv("/opt/google/chrome/chrome", "/srv/p", 9222)))
        self.assertNotIn('"', line)

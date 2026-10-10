from tests import support
import ast
import re
import unittest

from cdp_setup_kit.constants import LOOPBACK


class SafetyTests(unittest.TestCase):
    def test_static_rules(self):
        isolated = {"subprocess", "socket", "http.client", "winreg", "shutil"}
        forbidden = {"urllib.request", "ssl", "ftplib", "smtplib", "webbrowser", "ctypes", "signal"}
        allowed = {"argparse", "base64", "collections", "contextlib", "csv", "dataclasses", "datetime", "http", "io", "ipaddress", "hashlib", "json", "math", "ntpath", "os", "pathlib", "posixpath", "re", "shutil", "socket", "stat", "subprocess", "sys", "tempfile", "time", "typing", "urllib", "winreg", "xml"}
        disk_calls = {"write_text", "write_bytes", "unlink", "rmtree", "remove", "replace", "rename", "mkdir", "makedirs", "make_dir", "remove_file", "remove_tree"}
        private_files = ["Cook" + "ies", "Login" + " Data", "Local" + " State", "Web" + " Data", "Hist" + "ory", "Prefer" + "ences"]
        for path in (support.ROOT / "cdp_setup_kit").glob("*.py"):
            with self.subTest(path=path.name):
                text = path.read_text()
                tree = ast.parse(text, feature_version=(3, 9))
                self.assertIsNone(re.search(r"\b(kill|terminate|taskkill|pkill|killall)\b", text))
                self.assertNotIn(".".join(["0"] * 4), text)
                if path.name != "constants.py":
                    self.assertNotIn(LOOPBACK, text)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        modules = [a.name for a in node.names] if isinstance(node, ast.Import) else ([] if node.level else [node.module])
                        for module in modules:
                            self.assertNotIn(module, forbidden)
                            self.assertIn(module.split(".")[0], allowed)
                            if path.name != "system.py":
                                self.assertNotIn(module, isolated)
                                if module == "http":
                                    self.assertFalse(any(a.name == "client" for a in node.names))
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        if node.value.startswith("/json"):
                            self.assertEqual(node.value, "/json/version")
                        self.assertNotIn(node.value, private_files)
                    if path.name != "system.py" and isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Attribute) and node.func.attr in disk_calls:
                            receiver = ast.unparse(node.func.value)
                            self.assertIn(receiver, {"system", "self.system"})
                        if (isinstance(node.func, ast.Name) and node.func.id == "open") or (isinstance(node.func, ast.Attribute) and node.func.attr == "open"):
                            modes = [arg.value for arg in node.args[1:] if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
                            modes += [kw.value.value for kw in node.keywords if kw.arg == "mode" and isinstance(kw.value, ast.Constant)]
                            self.assertFalse(any(set(mode) & set("wax+") for mode in modes))

    def test_launch_invariants(self):
        from cdp_setup_kit.chrome import build_chrome_argv
        banned = ["--headless", "--remote-allow-origins", "--no-sandbox", "--disable-web-security", "--enable-automation"]
        for name in ["work", "shop", "research", "main"]:
            for port in [1024, 9222, 9223, 65535]:
                argv = build_chrome_argv("/opt/google/chrome/chrome", "/srv/kit-data/profiles/" + name, port)
                self.assertEqual(len(argv), 6)
                self.assertEqual(argv[3], "--remote-debugging-address=" + LOOPBACK)
                self.assertFalse(any(arg.startswith(flag) for arg in argv for flag in banned))

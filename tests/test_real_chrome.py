from tests import support
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from urllib.parse import urlsplit

from cdp_setup_kit import chrome, endpoint
from cdp_setup_kit.constants import LOOPBACK
from cdp_setup_kit.system import RealSystem


@unittest.skipUnless(os.environ.get("CDP_SETUP_KIT_REAL_CHROME") == "1", "owner opt-in only: disposable real Chrome")
class RealChromeTests(unittest.TestCase):
    def test_disposable_profile_restart(self):
        system = RealSystem()
        binary = chrome.find_chrome(system, {})
        if not binary:
            self.skipTest("Google Chrome is not installed")
        if system.platform not in {"windows", "linux", "macos"}:
            self.skipTest("unsupported desktop")
        if system.platform == "linux" and not (system.env.get("DISPLAY") or system.env.get("WAYLAND_DISPLAY")):
            self.skipTest("no desktop session")
        root = Path(tempfile.mkdtemp(prefix="cdpkit-test-"))
        system.env["CDP_SETUP_KIT_DIR"] = str(root)
        folder = root / "profiles" / "research"
        system.make_dir(str(folder))
        port = next((candidate for candidate in range(9333, 9433) if system.can_bind(candidate)), None)
        if port is None:
            shutil.rmtree(root)
            self.skipTest("no free disposable test port from 9333 through 9432")
        profile = {"port": port, "profile_dir": str(folder)}
        argv = chrome.build_chrome_argv(binary, str(folder), port)
        children = []
        addresses = []
        original_folder = folder.stat().st_ino
        try:
            for attempt in range(2):
                child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                children.append(child)
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    health = endpoint.status(system, profile)
                    if health["status"] in {"running", "running-unconfirmed"}:
                        break
                    time.sleep(0.25)
                self.assertIn(health["status"], {"running", "running-unconfirmed"})
                # Fixed-port Chrome may omit DevToolsActivePort. Ownership here is
                # established by our live child, isolated folder and initially free port.
                self.assertIsNone(child.poll())
                address = urlsplit(health["ws_endpoint"])
                self.assertEqual(address.hostname, LOOPBACK)
                self.assertEqual(address.port, port)
                print("Observed endpoint status: " + health["status"])
                self.assertEqual(folder.stat().st_ino, original_folder)
                self.assertFalse(any(row["level"] == "WARN" for row in endpoint.exposure(system, port, health["ws_endpoint"])))
                addresses.append(health["ws_endpoint"])
                print("Observed Browser: " + health["browser"])
                child.terminate()
                child.wait(timeout=10)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and system.cdp_version(port)["kind"] != "refused":
                    time.sleep(0.25)
                self.assertEqual(system.cdp_version(port)["kind"], "refused")
            self.assertNotEqual(addresses[0], addresses[1])
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)
            if all(child.poll() is not None for child in children):
                shutil.rmtree(root)

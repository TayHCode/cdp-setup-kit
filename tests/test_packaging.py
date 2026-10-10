from tests import support
import sys
import unittest

from cdp_setup_kit import __version__


class PackagingTests(unittest.TestCase):
    @unittest.skipIf(sys.version_info < (3, 11), "tomllib needs Python 3.11")
    def test_metadata(self):
        import tomllib
        data = tomllib.loads((support.ROOT / "pyproject.toml").read_text())
        project = data["project"]
        self.assertEqual(project["name"], "cdp-setup-kit")
        self.assertEqual(project["version"], __version__)
        self.assertEqual(project["license"], "MIT")
        self.assertEqual(project["dependencies"], [])
        self.assertEqual(project["requires-python"], ">=3.9")
        self.assertEqual(project["scripts"], {"cdp-setup-kit": "cdp_setup_kit.cli:main"})
        self.assertNotIn("authors", project)
        self.assertNotIn("urls", project)
        self.assertIn("Chrome DevTools Protocol", project["description"])

    def test_license(self):
        text = (support.ROOT / "LICENSE").read_text()
        self.assertTrue(text.startswith("MIT License\n"))
        self.assertIn("Copyright (c) 2026 TayHCode", text)

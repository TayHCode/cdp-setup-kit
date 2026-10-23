from tests import support
import contextlib
import io
import json
import re
import shlex
import unittest

from cdp_setup_kit.cli import parser
from cdp_setup_kit.constants import LOOPBACK, SECURITY_NOTICE


class DocsTests(unittest.TestCase):
    def test_readme_headings_and_status(self):
        text = (support.ROOT / "README.md").read_text()
        expected = ["# cdp-setup-kit", "## What this does", "## Security notice", "## Status", "## What you need", "## Install Chrome on Linux", "## Quickstart (Windows)", "## Quickstart (Linux)", "## Quickstart (macOS)", "## Commands", "## Connect an agent", "## Use it from another machine", "## Remote access", "## Share with your agents", "## Where things are stored", "## Optional: closing idle tabs", "## Limitations", "## Remove it", "## License"]
        self.assertEqual([line for line in text.splitlines() if re.match(r"^#{1,2} ", line)], expected)
        self.assertEqual(text.count("**not yet checked**"), 4)
        self.assertRegex(text, r"Verified on \d{4}-\d{2}-\d{2}.*: macOS")
        self.assertIn("login trigger unverified", text)
        for platform in ["Windows", "Linux", "macOS"]:
            section = text.split("## Quickstart (" + platform + ")\n", 1)[1].split("\n## ", 1)[0]
            self.assertEqual(len(re.findall(r"^\d\. ", section, re.M)), 8)

    def test_macos_support_is_honest_and_owner_checks_are_disposable(self):
        for name in ("README.md", "docs/troubleshooting.md"):
            text = (support.ROOT / name).read_text()
            self.assertIn("26.5.2", text)
            self.assertIn("unverified", text)
            self.assertIn("unit-tested", text)
            self.assertNotIn("macOS is not supported yet", text)
        text = (support.ROOT / "docs/verification.md").read_text().split("## macOS owner checklist\n", 1)[1]
        self.assertEqual(len(re.findall(r"^\d\. ", text, re.M)), 6)
        self.assertIn("disposable", text)
        self.assertIn("CDP_SETUP_KIT_REAL_CHROME=1", text)

    def test_session_routes_and_default_port_contract(self):
        text = (support.ROOT / "README.md").read_text()
        self.assertIn("9222 through 9321 inclusive, ascending", text)
        self.assertIn("--port 9333", text)
        self.assertNotIn(LOOPBACK + ":9222", text)
        self.assertIn("open main --headless", text)
        self.assertIn("schtasks /Run /TN cdp-setup-kit-main", text)
        self.assertIn("chmod +x", text)

    def test_notice(self):
        for name in ["README.md", "SECURITY.md"]:
            text = (support.ROOT / name).read_text()
            self.assertIn("```text\n" + SECURITY_NOTICE + "\n```", text)

    def test_documented_commands_parse(self):
        tree = parser()
        checked = 0
        for path in [support.ROOT / "README.md"] + sorted((support.ROOT / "docs").glob("*.md")):
            text = path.read_text()
            candidates = re.findall(r"(?<!`)`([^`\n]+)`(?!`)", text)
            for block in re.findall(r"```[^\n]*\n(.*?)```", text, re.S):
                candidates += block.splitlines()
            for line in candidates:
                match = re.match(r"(?:cdp-setup-kit\s+|(?:py|python3?|python3\.11)\s+-m\s+cdp_setup_kit\s+)(.+)", line.strip())
                if not match:
                    continue
                with self.subTest(path=path.name, command=line), contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    tree.parse_args(shlex.split(match.group(1)))
                checked += 1
        self.assertGreater(checked, 25)

    def test_examples(self):
        for filename, existing in [("playwright-attach.mjs", "browser.contexts()[0]"), ("playwright_attach.py", "browser.contexts[0]")]:
            text = (support.ROOT / "examples" / filename).read_text()
            self.assertIn(existing, text)
            self.assertNotIn("newContext", text)
            self.assertNotIn("new_context", text)
        for path in (support.ROOT / "examples").glob("*.json"):
            data = json.loads(path.read_text())
            self.assertEqual(data["mcpServers"]["browser"]["command"], "npx")
        for path in [support.ROOT / "README.md", support.ROOT / "SECURITY.md"] + list((support.ROOT / "docs").glob("*.md")):
            self.assertNotIn("--remote-debugging-address", path.read_text())

    def test_required_docs(self):
        for filename in ["README.md", "SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md", "LICENSE"]:
            self.assertTrue((support.ROOT / filename).is_file())
        self.assertEqual({p.name for p in (support.ROOT / "docs").glob("*.md")}, {"connect-agents.md", "remote-access.md", "startup.md", "troubleshooting.md", "idle-tabs.md", "verification.md"})

    def test_first_screen_and_remote_walkthrough(self):
        text = (support.ROOT / 'README.md').read_text()
        first = text.split('## Security notice')[0]
        for command in ['py -m cdp_setup_kit init', 'python3 -m cdp_setup_kit init']:
            self.assertIn(command, first)
        self.assertLess(len(first.splitlines()), 48)
        self.assertIn('reachable existing CDP HTTP endpoint', first)
        self.assertLess(first.index('Requires Python'), first.index('```'))
        self.assertIn('--endpoint http://' + LOOPBACK + ':9333', text)
        self.assertLess(text.index('## Security notice'), text.index('## Share with your agents'))
        for value in ['UserKnownHostsFile=TEMPFILE', 'StrictHostKeyChecking=accept-new', '-i /path/to/key', 'ssh USER@HOST true', 'init --yes --no-open', '--show-script']:
            self.assertIn(value, text)

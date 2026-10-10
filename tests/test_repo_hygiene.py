from tests import support
import ipaddress
import os
import re
import unittest

from cdp_setup_kit.constants import LOOPBACK

WORD = "ren" + "der"
EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}(?![\w.-])")
ACCOUNT_PATH = re.compile(r"(?:/ho" + r"me/[^/\s\"'<>]+|/Use" +
                          r"rs/[^/\s\"'<>]+|[A-Za-z]:[\\/]+Us" +
                          r"ers[\\/]+[^\\/\s\"'<>]+)")
INSIDE = re.compile(r"(?<![\w.-])(?:[\w-]+(?:\.[\w-]+)*\.(?:internal|local|lan|corp|home|localdomain)|[a-z][a-z-]*-\d{2})(?![\w.-]|\()", re.I)
IP = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")


class HygieneTests(unittest.TestCase):
    def test_files(self):
        failures = []
        for path in support.repo_files():
            name = path.relative_to(support.ROOT).as_posix()
            data = path.read_bytes()
            if len(data) > 200000 or b"\0" in data or path.is_symlink():
                failures.append(name + ":1: file type or size")
            if path.name in {".env", "credentials.json", "tokens.py"} or path.suffix in {".pem", ".key"}:
                failures.append(name + ":1: file name")
            for number, line in enumerate([name] + data.decode("utf-8").splitlines()):
                for label, hit in [("word", WORD in line.lower()), ("email", EMAIL.search(line)),
                                   ("user folder", ACCOUNT_PATH.search(line)), ("inside name", INSIDE.search(line))]:
                    if hit:
                        failures.append("{}:{}: {}".format(name, max(1, number), label))
                for match in IP.finditer(line):
                    try:
                        address = str(ipaddress.ip_address(match.group()))
                    except ValueError:
                        continue
                    allowed_file = name in {"cdp_setup_kit/constants.py", "README.md", "SECURITY.md"} or name.startswith(("docs/", "examples/", "tests/golden/"))
                    wildcard = ".".join(["0"] * 4)
                    example = address in {str(ipaddress.IPv4Address(1681915914)), str(ipaddress.IPv4Address(1681915924))} and (name == "README.md" or name.startswith("docs/"))
                    if not allowed_file or (address not in {LOOPBACK, wildcard} and not example) or (address == wildcard and not re.search("never|do not", line, re.I)):
                        failures.append("{}:{}: address".format(name, max(1, number)))
        self.assertEqual(failures, [], "\n".join(failures))

    def test_commit_messages(self):
        history = support.git_read(["log", "--all", "--format=%H%x00%B%x00"])
        if history is not None:
            self.assertNotIn(WORD, history.lower())

    @unittest.skipUnless(os.environ.get("CDPKIT_CHECK_TRAILERS") == "1",
                         "dev-history trailer check: set CDPKIT_CHECK_TRAILERS=1 in the dev repo")
    def test_commit_trailers(self):
        history = support.git_read(["log", "--all", "--format=%B%x00"])
        if history is not None:
            trailer = "Co-Authored-By: Claude Sonnet 5.5 <" + "noreply" + "@" + "anthropic" + ".com>"
            for message in history.split("\0"):
                if message.strip():
                    self.assertEqual(message.strip().splitlines()[-1], trailer)

    def test_only_source_formats(self):
        for path in support.repo_files():
            self.assertTrue(path.suffix in {".py", ".md", ".toml", ".txt", ".json", ".mjs"} or path.name in {"LICENSE", ".gitignore"})
            parts = path.relative_to(support.ROOT).parts
            if ".github" in parts:
                self.assertEqual(parts[:2], (".github", "ISSUE_TEMPLATE"))
                self.assertEqual(len(parts), 3)
                self.assertEqual(path.suffix, ".md")

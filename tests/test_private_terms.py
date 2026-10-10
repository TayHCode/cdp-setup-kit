from tests import support
import json
import os
from pathlib import Path
import re
import unittest


def read_terms(path):
    try:
        resolved = Path(path).resolve(strict=True)
        if resolved == support.ROOT or support.ROOT in resolved.parents:
            raise ValueError()
        text = resolved.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            if text.lstrip().startswith(("{", "[")):
                raise ValueError()
            data = [line.strip() for line in text.splitlines() if line.strip()]
        if isinstance(data, dict):
            if "terms" in data:
                data = data["terms"]
            else:
                categories = data.get("categories", {})
                data = [term for group in categories.values()
                        for term in (group.get("terms", []) if isinstance(group, dict) else group)]
        if not isinstance(data, list) or not data or any(not isinstance(term, str) or not term.strip() for term in data):
            raise ValueError()
        return data
    except (OSError, ValueError, TypeError, AttributeError):
        raise ValueError("term file is missing, unreadable, invalid, empty, or inside the repo") from None


def find_hits(terms, sources):
    patterns = [re.compile((r"(?<![^\W_])" if len(term) <= 3 and term.isalnum() else "") +
                           re.escape(term) + (r"(?![^\W_])" if len(term) <= 3 and term.isalnum() else ""), re.I)
                for term in terms]
    hits = []
    for name, text in sources:
        for number, line in enumerate(text.splitlines(), 1):
            for index, pattern in enumerate(patterns):
                if pattern.search(line):
                    hits.append((name, number, index))
    return hits


def repo_sources():
    result = []
    for path in support.repo_files():
        name = path.relative_to(support.ROOT).as_posix()
        result.extend([(name, name), (name, path.read_text(encoding="utf-8"))])
    history = support.git_read(["log", "--all", "--format=%h%x00%an%n%ae%n%cn%n%ce%n%B%x00"])
    if history:
        trailer = "Co-Authored-By: Claude Sonnet 5.5 <" + "noreply" + "@" + "anthropic" + ".com>"
        parts = history.split("\0")
        for index in range(0, len(parts) - 1, 2):
            body = "\n".join(line for line in parts[index + 1].splitlines()
                             if line != trailer)
            result.append((parts[index].strip(), body))
    return result


class PrivateTermsTests(support.KitTestCase):
    def test_generic_matching(self):
        terms = ["sampleblockedphrase", "xyz"]
        self.assertEqual(find_hits(terms, [("fixture", "SAMPLEBLOCKEDPHRASE xyz xyzq _xyz_")]),
                         [("fixture", 1, 0), ("fixture", 1, 1)])
        self.assertEqual(find_hits(terms, [("fixture", "axyz xyz9")]), [])
        self.assertEqual(find_hits(["generic" + "absentphrase"], repo_sources()), [])

    def test_formats_and_rejections(self):
        path = self.folder / "terms.json"
        for data in [["sampleterm"], {"terms": ["sampleterm"]},
                     {"categories": {"group": ["sampleterm"], "next": {"terms": ["anotherterm"]}}}]:
            path.write_text(json.dumps(data))
            self.assertTrue(read_terms(path))
        path.write_text("sampleterm\nanotherterm\n")
        self.assertEqual(len(read_terms(path)), 2)
        for text in ["", "[]", "{}", "[", "[2]"]:
            path.write_text(text)
            with self.assertRaises(ValueError):
                read_terms(path)
        with self.assertRaises(ValueError):
            read_terms(support.ROOT / "pyproject.toml")
        with self.assertRaises(ValueError):
            read_terms(self.folder / "missing")

    def test_owner_terms(self):
        path = os.environ.get("CDP_SETUP_KIT_DENYLIST")
        if not path:
            self.skipTest("set CDP_SETUP_KIT_DENYLIST to a term file outside this repo to run this test")
        try:
            terms = read_terms(path)
        except ValueError as exc:
            self.fail(str(exc))
        hits = find_hits(terms, repo_sources())
        print("terms={} hits={}".format(len(terms), len(hits)))
        if hits:
            self.fail("\n".join("{}:{}".format(hit[0], hit[1]) for hit in hits))

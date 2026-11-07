"""The Agensi skill pack (agensi/rhino-workbench): its JSON examples build with this runtime, every
SKILL.md has the frontmatter Agensi needs, and the files a skill names are delivered with it."""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.path.join(ROOT, "agensi", "rhino-workbench")
sys.path.insert(0, os.path.join(ROOT, "rhino"))

from rhinospec import validate  # noqa: E402


def files():
    for d, _, names in os.walk(PACK):
        for n in names:
            if n.endswith(".md"):
                yield os.path.join(d, n)


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


class Pack(unittest.TestCase):
    def test_every_json_spec_in_the_pack_validates(self):
        n = 0
        for p in files():
            for block in re.findall(r"```json\n(.*?)```", read(p), re.S):
                if "..." in block:   # a skeleton, not an example
                    continue
                spec = json.loads(block)
                if "parts" in spec:
                    validate(spec)
                    n += 1
        self.assertGreaterEqual(n, 3)

    def test_each_skill_has_name_description_and_its_files(self):
        skills = os.path.join(PACK, "skills")
        shared = set(os.listdir(os.path.join(PACK, "shared")))
        for name in os.listdir(skills):
            text = read(os.path.join(skills, name, "SKILL.md"))
            front = text.split("---")[1]
            self.assertIn("name: %s\n" % name, front)
            self.assertRegex(front, r"description: \S")
            self.assertIn("Requires:", text)
            own = set(os.listdir(os.path.join(skills, name)))
            for ref in set(re.findall(r"\b([a-z0-9]+\.md)\b", text)) - {"SKILL.md"}:
                self.assertIn(ref, own | shared, "%s names %s" % (name, ref))

    def test_no_stale_wording(self):
        # the 0.1.1 rules this version fixed must not come back
        for p in files():
            t = read(p)
            for stale in ("coupled to detector setup", "0.1.1", "6505254", "do not run detector setup",
                          "slab to railing top |", "Do not add `group`, `tilt`, `cut`, `keep` or `join` to composite macros."):
                self.assertNotIn(stale, t, p)


if __name__ == "__main__":
    unittest.main()

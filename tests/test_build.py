import importlib.util
import os
import re
import tempfile
import unittest

from helpers import ROOT, read

spec = importlib.util.spec_from_file_location("build_standalone", os.path.join(ROOT, "tools", "build_standalone.py"))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def write(path, text, newline="\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as f:
        f.write(text)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        write(os.path.join(self.root, "lib", "a.py"), "print('a')\n")
        write(os.path.join(self.root, "install.md"), "# Install\n")
        write(os.path.join(self.root, "standalone", "sherlock.src.md"),
              "intro\ncat > x <<'EOF'\n{{file:lib/a.py}}\nEOF\nend\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_expands_placeholders_and_copies(self):
        self.assertEqual(build.main(["--root", self.root]), 0)
        expected = "intro\ncat > x <<'EOF'\nprint('a')\nEOF\nend\n"
        self.assertEqual(read(os.path.join(self.root, "standalone", "sherlock.md")), expected)
        self.assertEqual(read(os.path.join(self.root, "site", "sherlock.md")), expected)
        self.assertEqual(read(os.path.join(self.root, "site", "install.md")), "# Install\n")

    def test_check_detects_stale_and_writes_nothing(self):
        self.assertEqual(build.main(["--root", self.root, "--check"]), 1)
        self.assertFalse(os.path.exists(os.path.join(self.root, "standalone", "sherlock.md")))
        build.main(["--root", self.root])
        self.assertEqual(build.main(["--root", self.root, "--check"]), 0)
        write(os.path.join(self.root, "lib", "a.py"), "print('b')\n")
        self.assertEqual(build.main(["--root", self.root, "--check"]), 1)

    def test_crlf_checkout_is_not_stale(self):
        build.main(["--root", self.root])
        for rel in ("lib/a.py", "standalone/sherlock.src.md", "standalone/sherlock.md", "site/sherlock.md"):
            path = os.path.join(self.root, rel)
            write(path, read(path), newline="\r\n")
        self.assertEqual(build.main(["--root", self.root, "--check"]), 0)

    def test_eof_line_in_inlined_file_fails(self):
        write(os.path.join(self.root, "lib", "a.py"), "x = 1\nEOF\n")
        self.assertEqual(build.main(["--root", self.root]), 2)

    def test_missing_placeholder_file_fails(self):
        write(os.path.join(self.root, "standalone", "sherlock.src.md"), "{{file:lib/missing.py}}\n")
        self.assertEqual(build.main(["--root", self.root]), 2)


class Repo(unittest.TestCase):
    def test_repo_is_built(self):
        self.assertEqual(build.main(["--root", ROOT, "--check"]), 0, "run: py -3 tools/build_standalone.py")

    def test_install_lists_every_skill_file(self):
        skill = os.path.join(ROOT, "skills", "sherlock")
        files = {os.path.relpath(os.path.join(d, f), skill).replace(os.sep, "/")
                 for d, _, fs in os.walk(skill) for f in fs if "__pycache__" not in d}
        listed = set(re.findall(r"^- `([^`]+)`$", read(os.path.join(ROOT, "install.md")), re.M))
        self.assertEqual(files, listed)

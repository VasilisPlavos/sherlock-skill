import hashlib
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT, read

spec = importlib.util.spec_from_file_location("build_standalone", os.path.join(ROOT, "tools", "build_standalone.py"))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

SRC = "intro\ncat > \"$WORK/a.py\" <<'EOF'\n{{file:lib/a.py}}\nEOF\nend\n"
A_HASH = hashlib.sha256(b"print('a')\n").hexdigest()


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
        self.write_src(SRC)

    def tearDown(self):
        self.tmp.cleanup()

    def write_src(self, text):
        write(os.path.join(self.root, "standalone", "sherlock.src.md"), text)

    def test_expands_placeholders_and_copies(self):
        self.assertEqual(build.main(["--root", self.root]), 0)
        expected = ("intro\ncat > \"$WORK/a.py\" <<'EOF'\nprint('a')\nEOF\n"
                    + build.verify_line("$WORK/a.py", "print('a')\n") + "end\n")
        self.assertEqual(read(os.path.join(self.root, "site", "sherlock.md")), expected)
        self.assertEqual(read(os.path.join(self.root, "site", "install.md")), "# Install\n")
        self.assertFalse(os.path.exists(os.path.join(self.root, "standalone", "sherlock.md")))

    def test_verify_line_hash(self):
        line = build.verify_line("$WORK/a.py", "print('a')\n")
        self.assertIn(A_HASH, line)
        self.assertIn('"$WORK/a.py"', line)
        self.assertTrue(line.endswith("\n"))

    def run_verify(self, content):
        line = build.verify_line("$WORK/a.py", "print('a')\n")
        code = line.split("'")[1]  # the program between the single quotes
        message = re.findall(r'"([^"]*)"', line.split("'", 2)[2])[-1]  # the last quoted argument, if any
        path = os.path.join(self.root, "written.py")
        with open(path, "wb") as f:
            f.write(content)
        extra = [message] if message.startswith("error:") else []
        return subprocess.run([sys.executable, "-c", code, path, A_HASH, *extra], capture_output=True, text=True)

    def test_verify_line_accepts_crlf_copy(self):  # a Windows file tool may write CRLF
        r = self.run_verify(b"print('a')\r\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_verify_line_accepts_bom_copy(self):  # PowerShell 5.1 Out-File / Set-Content -Encoding utf8
        r = self.run_verify(b"\xef\xbb\xbfprint('a')\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_verify_line_accepts_missing_final_newline(self):
        r = self.run_verify(b"print('a')")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_verify_program_has_no_double_quotes(self):  # PowerShell 5.1 strips them from native arguments
        self.assertNotIn('"', build.verify_line("$WORK/a.py", "print('a')\n").split("'")[1])

    def test_verify_line_rejects_a_changed_copy(self):
        r = self.run_verify(b"print('b')\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("was not written verbatim", r.stderr)

    def test_placeholder_without_cat_line_fails(self):
        self.write_src("{{file:lib/a.py}}\nEOF\n")
        self.assertEqual(build.main(["--root", self.root]), 2)

    def test_placeholder_without_eof_fails(self):
        self.write_src("cat > \"$WORK/a.py\" <<'EOF'\n{{file:lib/a.py}}\nend\n")
        self.assertEqual(build.main(["--root", self.root]), 2)

    def test_check_detects_stale_and_writes_nothing(self):
        self.assertEqual(build.main(["--root", self.root, "--check"]), 1)
        self.assertFalse(os.path.exists(os.path.join(self.root, "site", "sherlock.md")))
        build.main(["--root", self.root])
        self.assertEqual(build.main(["--root", self.root, "--check"]), 0)
        write(os.path.join(self.root, "lib", "a.py"), "print('b')\n")
        self.assertEqual(build.main(["--root", self.root, "--check"]), 1)

    def test_crlf_checkout_is_not_stale(self):
        build.main(["--root", self.root])
        for rel in ("lib/a.py", "standalone/sherlock.src.md", "site/sherlock.md"):
            path = os.path.join(self.root, rel)
            write(path, read(path), newline="\r\n")
        self.assertEqual(build.main(["--root", self.root, "--check"]), 0)

    def test_eof_line_in_inlined_file_fails(self):
        write(os.path.join(self.root, "lib", "a.py"), "x = 1\nEOF\n")
        self.assertEqual(build.main(["--root", self.root]), 2)

    def test_missing_placeholder_file_fails(self):
        self.write_src("cat > \"$WORK/m.py\" <<'EOF'\n{{file:lib/missing.py}}\nEOF\n")
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

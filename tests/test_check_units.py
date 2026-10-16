import os
import subprocess
import sys
import tempfile
import unittest

from helpers import load, read, script

check = load("check")


def run_check(*args):
    return subprocess.run([sys.executable, script("check"), *args],
                          capture_output=True, text=True, encoding="utf-8")


class Fill(unittest.TestCase):
    def test_nested(self):
        self.assertEqual(check.fill({"a": ["{}x", 1], "b": "{}"}, "bob"), {"a": ["bobx", 1], "b": "bob"})


class Allowed(unittest.TestCase):
    def test_regex_check(self):
        info = {"url": "https://x.test/{}", "regexCheck": "^[a-z]+$"}
        self.assertTrue(check.allowed(info, "bill"))
        self.assertFalse(check.allowed(info, "bill.gates"))

    def test_subdomain_template(self):
        info = {"url": "https://{}.x.test"}
        self.assertTrue(check.allowed(info, "billgates"))
        self.assertFalse(check.allowed(info, "bill.gates"))
        self.assertFalse(check.allowed(info, "bill_gates"))


class Shape(unittest.TestCase):
    def test_separators(self):
        self.assertEqual(check.shape("billgates"), "")
        self.assertEqual(check.shape("bill.gates"), ".")
        self.assertEqual(check.shape("a_b-c.d"), "-._")
        self.assertEqual(check.shape("γιώργος"), "")


class RandomLike(unittest.TestCase):
    def test_same_separators(self):
        self.assertRegex(check.random_like("bill.gates", {"url": "https://x.test/{}"}), r"^[a-z]{8,}\.[a-z]{8,}$")

    def test_keep_first(self):
        self.assertRegex(check.random_like("bill.gates", {"url": "https://x.test/{}"}, keep_first=True),
                         r"^bill\.[a-z]{8,}$")

    def test_falls_back_to_same_length(self):
        info = {"url": "https://x.test/{}", "regexCheck": "^[a-z]{4}$"}
        self.assertRegex(check.random_like("bill", info), r"^[a-z]{4}$")

    def test_impossible(self):
        self.assertIsNone(check.random_like("bill", {"url": "https://x.test/{}", "regexCheck": r"^\d+$"}))


class Cli(unittest.TestCase):
    def test_version(self):
        r = run_check("--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(check.__version__, r.stdout)

    def test_init_writes_started_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out dir", "bill-gates")
            self.assertEqual(run_check("--init", out).returncode, 0)
            started = os.path.join(out, ".work", "started")
            first = read(started)
            self.assertRegex(first.strip(), r"^\d+$")
            self.assertEqual(run_check("--init", out).returncode, 0)
            self.assertEqual(read(started), first)

    def test_no_usernames_is_an_error(self):
        self.assertNotEqual(run_check().returncode, 0)


if __name__ == "__main__":
    unittest.main()

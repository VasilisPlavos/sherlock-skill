import contextlib
import io
import os
import random
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import Future

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


class PlanCalibration(unittest.TestCase):
    def test_skips_a_username_the_site_cannot_mimic(self):  # 'abcdefghij.klm' is too long for the regex
        sites = {"S": {"url": "https://x.test/{}", "regexCheck": "^[a-z.]{1,12}$"}}
        plan = check.plan_calibration(["abcdefghij.klm", "bill.gates"], sites)
        self.assertRegex(plan[("S", ".")], r"^[a-z]{4}\.[a-z]{5}$")

    def test_one_entry_per_site_and_shape(self):
        sites = {"A": {"url": "https://a.test/{}"}, "B": {"url": "https://b.test/{}"}}
        plan = check.plan_calibration(["alice", "bob", "bill.gates"], sites)
        self.assertEqual(set(plan), {("A", ""), ("A", "."), ("B", ""), ("B", ".")})

    def test_impossible_shape_is_absent(self):
        self.assertEqual(check.plan_calibration(["bill"], {"S": {"url": "https://x.test/{}", "regexCheck": r"^\d+$"}}), {})


def done(row):
    f = Future()
    f.set_result(row)
    return f


def row(site, status="AVAILABLE", username="u"):
    return {"username": username, "site": site, "url": "", "status": status, "context": ""}


class Track(unittest.TestCase):
    def test_collects_all_and_reports_claimed(self):
        jobs = [Future() for _ in range(300)]

        def finish():
            for i in random.sample(range(300), 300):
                jobs[i].set_result(row(f"s{i}", "CLAIMED" if i % 10 == 0 else "AVAILABLE"))
        threading.Thread(target=finish).start()
        rows, seen = [], []
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            check.track(jobs, rows, on_claimed=seen.append)
        self.assertEqual(len(rows), 300)
        self.assertEqual(len(seen), 30)

    def test_counts_calibration_but_does_not_collect_it(self):
        err = io.StringIO()
        rows = []
        with contextlib.redirect_stderr(err):
            check.track([done(row("a")), done(row("b"))], rows, [done(row("c")) for _ in range(3)])
        self.assertEqual(len(rows), 2)
        self.assertIn("progress 5/5 (100%)", err.getvalue())


class CollectFinished(unittest.TestCase):
    def test_adds_only_finished_jobs_not_yet_collected(self):
        f1, f2, f3, f4 = done(row("a")), done(row("b")), Future(), Future()
        f4.cancel()
        rows = [f1.result()]
        self.assertEqual(check.collect_finished([f1, f2, f3, f4], rows), 1)
        self.assertIs(rows[-1], f2.result())
        self.assertEqual(len(rows), 2)


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

    def run_with_file(self, tmp, encoding):
        users = os.path.join(tmp, "usernames.txt")
        with open(users, "w", encoding=encoding) as f:
            f.write("josé\nalice\n")
        data = os.path.join(tmp, "data.json")
        with open(data, "w", encoding="utf-8") as f:
            f.write("{}")
        log = os.path.join(tmp, "check.log")
        r = run_check("--file", users, "--data", data, "--out", os.path.join(tmp, "results.csv"), "--log", log)
        return r, log

    def test_utf16_username_file_is_read(self):  # PowerShell 5.1 '>' writes UTF-16
        with tempfile.TemporaryDirectory() as tmp:
            r, log = self.run_with_file(tmp, "utf-16")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("2 usernames x 0 sites", read(log))

    def test_non_utf8_username_file_fails_on_the_console(self):  # PowerShell 5.1 Set-Content writes cp1252
        with tempfile.TemporaryDirectory() as tmp:
            r, _ = self.run_with_file(tmp, "cp1252")
            self.assertEqual(r.returncode, 2)
            self.assertIn("UTF-8", r.stderr)


if __name__ == "__main__":
    unittest.main()

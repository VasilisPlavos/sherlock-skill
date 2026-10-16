import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from helpers import ROOT, load, read, script

render_report = load("render_report")
TPL = '<html><script id="report-data" type="application/json">__REPORT_DATA__</script></html>\n'
SAMPLE = os.path.join(ROOT, "tests", "fixtures", "sample_report.json")


def extract(html):
    m = re.search(r'<script id="report-data" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


class RenderCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.tmp.name, "out dir")
        os.makedirs(os.path.join(self.out, ".work"))
        self.tpl = os.path.join(self.tmp.name, "tpl.html")
        with open(self.tpl, "w", encoding="utf-8") as f:
            f.write(TPL)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text, encoding="utf-8"):
        with open(os.path.join(self.out, name), "w", encoding=encoding, newline="") as f:
            f.write(text)

    def write_report(self, data, encoding="utf-8"):
        self.write("report.json", json.dumps(data, ensure_ascii=False), encoding)

    def run_render(self, template=True):
        args = [sys.executable, script("render_report"), self.out] + (["--template", self.tpl] if template else [])
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8")

    def html(self):
        return read(os.path.join(self.out, "report.html"))

    def test_script_in_bio_cannot_break_out(self):
        shutil.copy(SAMPLE, os.path.join(self.out, "report.json"))
        r = self.run_render()
        self.assertEqual(r.returncode, 0, r.stderr)
        html = self.html()
        self.assertNotIn("<script>alert", html)
        self.assertEqual(extract(html)["profiles"][0]["bio"], "</script><script>alert(1)</script>")

    def test_default_template_renders_sample(self):
        shutil.copy(SAMPLE, os.path.join(self.out, "report.json"))
        r = self.run_render(template=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        html = self.html()
        self.assertEqual(extract(html)["subject"]["name"], "Jane Example")
        self.assertIn("D.demo", html)
        self.assertIn("photo_credit", html)

    def test_method_is_filled_from_run_files(self):
        self.write(".work/started", str(int(time.time()) - 3725))
        self.write("check.log", "check.py 1.0.0: 2 usernames x 3 sites\nFindings (after calibration):\ntook 2m41s\n")
        self.write("results.csv", "username,site,url,status,http,ms,context\n"
                   + "".join(f"{u},{s},u,AVAILABLE,404,1,\n" for u in ("a", "b") for s in ("S1", "S2", "S3")))
        self.write_report({"method": {"brief": "x", "date": "2020-01-01"}})
        self.assertEqual(self.run_render().returncode, 0)
        m = extract(self.html())["method"]
        self.assertEqual(m["date"], "2020-01-01")
        self.assertEqual(m["brief"], "x")
        self.assertRegex(m["duration"], r"^1h02m0\ds")
        self.assertEqual(m["bulk_check"], "done in 2m41s")
        self.assertEqual((m["sites"], m["variants"]), (3, 2))

    def test_without_python_run_files(self):
        self.write_report({"subject": {"name": "X"}})
        self.assertEqual(self.run_render().returncode, 0)
        m = extract(self.html())["method"]
        self.assertEqual(m["bulk_check"], "not run")
        self.assertRegex(m["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertNotIn("sites", m)

    def test_partial_and_utf16_log(self):
        self.write("check.log", "Findings (after calibration): PARTIAL: 10/20 checked\ntook 0m05s\n", "utf-16")
        self.write_report({})
        self.assertEqual(self.run_render().returncode, 0)
        self.assertEqual(extract(self.html())["method"]["bulk_check"], "done in 0m05s (partial: stopped early)")

    def test_bom_report(self):
        self.write_report({"subject": {"name": "Ζωή"}}, "utf-8-sig")
        r = self.run_render()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(extract(self.html())["subject"]["name"], "Ζωή")

    def test_schema_errors(self):
        cases = [({"profiles": {"a": 1}}, "'profiles' must be a list"),
                 ({"profiles": [{"site": "X", "confidence": "maybe"}]}, "profiles[0].confidence"),
                 ({"subject": "Bill"}, "'subject' must be an object"),
                 ({"contacts": ["x"]}, "'contacts[0]' must be an object")]
        for data, message in cases:
            self.write_report(data)
            r = self.run_render()
            self.assertEqual(r.returncode, 1, data)
            self.assertIn(message, r.stderr)

    def test_invalid_json(self):
        self.write("report.json", "{not json")
        r = self.run_render()
        self.assertEqual(r.returncode, 1)
        self.assertIn("invalid JSON", r.stderr)

    def test_missing_report(self):
        r = self.run_render()
        self.assertEqual(r.returncode, 1)
        self.assertIn("error:", r.stderr)


class Units(unittest.TestCase):
    def test_fmt_duration(self):
        self.assertEqual(render_report.fmt_duration(3725), "1h02m05s")
        self.assertEqual(render_report.fmt_duration(-5), "0h00m00s")

    def test_render_requires_one_placeholder(self):
        with self.assertRaises(render_report.ReportError):
            render_report.render({}, "<html></html>")


if __name__ == "__main__":
    unittest.main()

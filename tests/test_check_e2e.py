import csv
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from helpers import read, script

CHALLENGE = '<html><span id="challenge-error-text">Checking your browser</span></html>'
USERS = ["alice", "bill.gates", "josé"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def answer(self, send_body):
        kind, _, raw = self.path.lstrip("/").partition("/")
        name = urllib.parse.unquote(raw)
        code, body, headers = 404, "Not here", {}
        if kind == "status":
            code, body = (200 if name in ("alice", "bill.gates") else 404), "page"
        elif kind == "msg":
            code, body = 200, ("Profile of alice" if name == "alice" else "No such user")
        elif kind == "waf":
            code, body = 403, "Forbidden"
        elif kind == "cf":
            code, body = 200, CHALLENGE
        elif kind == "always":
            code, body = 200, "page"
        elif kind == "prefix":  # resolves 'bill.<anything>' to the account 'bill'
            code, body = (200 if name == "alice" or name.split(".")[0] == "bill" else 404), "page"
        elif kind == "redir":
            if name == "alice":
                code, body = 200, "page"
            else:
                code, body, headers = 302, "", {"Location": "/home"}
        data = body.encode()
        self.send_response(code)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def do_GET(self):
        self.answer(True)

    def do_HEAD(self):
        self.answer(False)


def manifest(base):
    def site(path, **kw):
        return {"url": f"{base}/{path}/{{}}", "urlMain": base, **kw}
    return {
        "StatusSite": site("status", errorType="status_code"),
        "MessageSite": site("msg", errorType="message", errorMsg="No such user"),
        "WafSite": site("waf", errorType="status_code"),
        "ChallengeSite": site("cf", errorType="message", errorMsg="No such user"),
        "AlwaysSite": site("always", errorType="status_code"),
        "PrefixSite": site("prefix", errorType="status_code"),
        "RegexSite": site("status", errorType="status_code", regexCheck="^[a-z]+$"),
        "RedirectSite": site("redir", errorType="response_url", errorUrl=base + "/home"),
    }


EXPECTED = {
    ("alice", "StatusSite"): "CLAIMED", ("bill.gates", "StatusSite"): "CLAIMED", ("josé", "StatusSite"): "AVAILABLE",
    ("alice", "MessageSite"): "CLAIMED", ("bill.gates", "MessageSite"): "AVAILABLE", ("josé", "MessageSite"): "AVAILABLE",
    ("alice", "WafSite"): "WAF", ("bill.gates", "WafSite"): "WAF", ("josé", "WafSite"): "WAF",
    ("alice", "ChallengeSite"): "WAF", ("bill.gates", "ChallengeSite"): "WAF", ("josé", "ChallengeSite"): "WAF",
    ("alice", "AlwaysSite"): "UNRELIABLE", ("bill.gates", "AlwaysSite"): "UNRELIABLE", ("josé", "AlwaysSite"): "UNRELIABLE",
    ("alice", "PrefixSite"): "CLAIMED", ("bill.gates", "PrefixSite"): "UNRELIABLE", ("josé", "PrefixSite"): "AVAILABLE",
    ("alice", "RegexSite"): "CLAIMED", ("bill.gates", "RegexSite"): "ILLEGAL", ("josé", "RegexSite"): "ILLEGAL",
    ("alice", "RedirectSite"): "CLAIMED", ("bill.gates", "RedirectSite"): "AVAILABLE", ("josé", "RedirectSite"): "AVAILABLE",
}


class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # addClassCleanup runs even when setUpClass fails (tearDownClass would not)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.addClassCleanup(cls.server.server_close)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.server.shutdown)
        base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.out = os.path.join(cls.tmp.name, "out dir")
        os.makedirs(os.path.join(cls.out, ".work"))
        data = os.path.join(cls.out, "data.json")
        with open(data, "w", encoding="utf-8") as f:
            json.dump(manifest(base), f)
        env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
        env["NO_PROXY"] = "*"
        cls.csv = os.path.join(cls.out, "results.csv")
        cls.log = os.path.join(cls.out, "check.log")
        cls.proc = subprocess.run(
            [sys.executable, script("check"), *USERS, "--data", data, "--out", cls.csv, "--log", cls.log,
             "--timeout", "5"],
            env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
        if not os.path.exists(cls.csv):
            log = read(cls.log) if os.path.exists(cls.log) else ""
            raise AssertionError(f"check.py wrote no results.csv (exit {cls.proc.returncode}):\n"
                                 f"{cls.proc.stderr}\n{log}")
        with open(cls.csv, encoding="utf-8", newline="") as f:
            cls.rows = {(r["username"], r["site"]): r for r in csv.DictReader(f)}

    def test_exit_code(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)

    def test_statuses(self):
        for key, status in EXPECTED.items():
            self.assertEqual(self.rows[key]["status"], status, key)

    def test_non_ascii_username_is_percent_encoded(self):
        self.assertIn("jos%C3%A9", self.rows[("josé", "StatusSite")]["url"])

    def test_log_is_utf8_and_complete(self):
        log = read(self.log)
        self.assertIn("check.py 1.1.0:", log)
        self.assertIn("Findings (after calibration):", log)
        self.assertRegex(log, r"(?m)^took \d+m\d{2}s$")
        self.assertIn("[+] alice", log)
        self.assertEqual(self.proc.stdout, "")

    def test_started_written_when_work_dir_exists(self):
        self.assertRegex(read(os.path.join(self.out, ".work", "started")).strip(), r"^\d+$")


if __name__ == "__main__":
    unittest.main()

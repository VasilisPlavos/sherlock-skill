import os
import unittest

from helpers import ROOT, read

ESCAPE = "\\u003c"  # the six characters backslash, u, 0, 0, 3, c


class NoPythonInstructions(unittest.TestCase):
    def test_escape_sequence_is_spelled_out(self):
        for rel in ("skills/sherlock/references/report.md", "standalone/sherlock.src.md"):
            self.assertIn(f"`{ESCAPE}`", read(os.path.join(ROOT, *rel.split("/"))), rel)


class ResumeAdvice(unittest.TestCase):
    def test_partial_runs_are_resumed_by_username(self):  # jobs run username by username, not site by site
        for rel in ("skills/sherlock/references/troubleshooting.md", "standalone/sherlock.src.md"):
            row = next(l for l in read(os.path.join(ROOT, *rel.split("/"))).splitlines()
                       if l.startswith("| Check stopped early"))
            self.assertNotIn("--site X", row, rel)
            self.assertIn("missing usernames", row, rel)


class Workflow(unittest.TestCase):
    def test_pages_permissions_only_on_deploy_job(self):
        text = read(os.path.join(ROOT, ".github", "workflows", "pages.yml"))
        deploy = text.index("\n  deploy:")
        for perm in ("pages: write", "id-token: write"):
            self.assertGreater(text.index(perm), deploy, perm)


if __name__ == "__main__":
    unittest.main()

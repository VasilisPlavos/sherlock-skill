import os
import re
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


class StandaloneMatchesSkill(unittest.TestCase):  # the standalone prose is kept in line with SKILL.md by hand
    def setUp(self):
        self.text = read(os.path.join(ROOT, "standalone", "sherlock.src.md"))
        self.blocks = re.findall(r"```bash\n(.*?)```", self.text, re.S)

    def test_check_uses_log_flag(self):  # PowerShell's '>' writes UTF-16
        self.assertIn('--log "$OUT/check.log"', self.text)
        self.assertNotIn('> "$OUT/check.log"', self.text)

    def test_background_run_has_no_tail(self):
        run = next(b for b in self.blocks if '--log "$OUT/check.log"' in b)
        self.assertNotIn("tail", run)
        self.assertTrue(any('tail -n 3 "$OUT/check.log"' in b for b in self.blocks))

    def test_resume_uses_its_own_log(self):
        row = next(l for l in self.text.splitlines() if l.startswith("| Check stopped early"))
        self.assertIn('--log "$OUT/check-rest.log"', row)
        self.assertNotIn("2>&1", row)

    def test_powershell_log_row(self):
        self.assertTrue(any(l.startswith("| `check.log` unreadable or empty in PowerShell")
                            for l in self.text.splitlines()))


class Workflow(unittest.TestCase):
    def test_pages_permissions_only_on_deploy_job(self):
        text = read(os.path.join(ROOT, ".github", "workflows", "pages.yml"))
        deploy = text.index("\n  deploy:")
        for perm in ("pages: write", "id-token: write"):
            self.assertGreater(text.index(perm), deploy, perm)


if __name__ == "__main__":
    unittest.main()

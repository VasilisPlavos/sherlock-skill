import os
import unittest

from helpers import ROOT, read

ESCAPE = "\\u003c"  # the six characters backslash, u, 0, 0, 3, c


class NoPythonInstructions(unittest.TestCase):
    def test_escape_sequence_is_spelled_out(self):
        for rel in ("skills/sherlock/references/report.md", "standalone/sherlock.src.md"):
            self.assertIn(f"`{ESCAPE}`", read(os.path.join(ROOT, *rel.split("/"))), rel)


if __name__ == "__main__":
    unittest.main()

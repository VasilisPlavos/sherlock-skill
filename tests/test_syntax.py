import ast
import glob
import os
import unittest

from helpers import ROOT


class Py39Syntax(unittest.TestCase):
    def test_python_files_parse_as_3_9(self):
        files = glob.glob(os.path.join(ROOT, "skills", "sherlock", "scripts", "*.py"))
        files += glob.glob(os.path.join(ROOT, "tools", "*.py"))
        self.assertTrue(files)
        for path in files:
            with open(path, encoding="utf-8") as f:
                ast.parse(f.read(), path, feature_version=(3, 10))


if __name__ == "__main__":
    unittest.main()

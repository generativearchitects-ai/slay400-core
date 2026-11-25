#!/usr/bin/env python3
"""Tests of run_examples.py's pure helpers: instrument(), requires_ibmi() and normalize(). The end-to-end
check() -- building a stand-in release, running every example's steps.sh as a real subprocess and comparing
output -- is proven by actually running it against this repository (see the kickoff 16 pull request
description for how), not re-created here with fixtures: it needs a real built pcml-launcher archive and a
real POSIX shell, which would make this file an integration test rather than a unit test.

Run with: python3 -m unittest discover -s scripts/docs
"""
import unittest

import run_examples as run


class RequiresIbmiTest(unittest.TestCase):

    def test_a_requires_ibmi_comment_is_detected(self):
        self.assertTrue(run.requires_ibmi(["# requires: ibmi", "CRTBNDRPG ..."]))

    def test_a_requires_comment_for_something_else_is_not_ibmi(self):
        self.assertFalse(run.requires_ibmi(["# requires: curl"]))

    def test_no_requires_comment_at_all(self):
        self.assertFalse(run.requires_ibmi(["echo hello"]))


class InstrumentTest(unittest.TestCase):

    def write(self, tmp_path, text):
        tmp_path.write_text(text, encoding="utf-8")
        return tmp_path

    def test_each_region_gets_a_sentinel_after_it_in_order(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            steps = self.write(Path(tmp) / "steps.sh",
                                "#!/bin/sh\n# region: a\necho one\n# endregion\n\n# region: b\necho two\n# endregion\n")
            script, order = run.instrument(steps)
        self.assertEqual(["a", "b"], order)
        self.assertIn("echo one", script)
        self.assertIn("==EXAMPLE_REGION_END:a==", script)
        self.assertIn("==EXAMPLE_REGION_END:b==", script)
        self.assertLess(script.index("==EXAMPLE_REGION_END:a=="), script.index("echo two"))

    def test_a_requires_ibmi_region_is_dropped_entirely(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            steps = self.write(Path(tmp) / "steps.sh",
                                "#!/bin/sh\n# region: a\n# requires: ibmi\nCRTBNDRPG FOO\n# endregion\n\n"
                                "# region: b\necho two\n# endregion\n")
            script, order = run.instrument(steps)
        self.assertEqual(["b"], order)
        self.assertNotIn("CRTBNDRPG", script)
        self.assertNotIn("==EXAMPLE_REGION_END:a==", script)

    def test_the_literal_install_line_is_run_locally_instead_of_from_github(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            steps = self.write(Path(tmp) / "steps.sh",
                                "#!/bin/sh\n# region: install\n"
                                "curl -fsSL https://raw.githubusercontent.com/generativearchitects-ai/slay400-core/main/install.sh | sh\n"
                                "# endregion\n")
            script, _ = run.instrument(steps)
        self.assertNotIn("raw.githubusercontent.com", script)
        self.assertIn('sh "', script)
        self.assertIn("install.sh", script)

    def test_lines_outside_any_region_are_kept_without_a_sentinel(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            steps = self.write(Path(tmp) / "steps.sh", "#!/bin/sh\nset -eu\n# region: a\necho one\n# endregion\n")
            script, _ = run.instrument(steps)
        self.assertIn("set -eu", script)


class NormalizeTest(unittest.TestCase):

    def test_the_version_is_replaced(self):
        self.assertEqual("slay400 <version>", run.normalize("slay400 0.1.0-alpha.1", "0.1.0-alpha.1", "/nonexistent"))

    def test_the_workdir_is_replaced(self):
        text = "installed in /tmp/abc123/_home/.slay400/0.1.0"
        self.assertEqual("installed in <workdir>/_home/.slay400/<version>", run.normalize(text, "0.1.0", "/tmp/abc123"))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests of generate_cli_reference.py's find_jar(). render() itself needs a real built jar and a real `java`
on PATH, and is proven by actually running the generator against this repository's build (see the kickoff 16
pull request description), not re-created here with a fake jar.

Run with: python3 -m unittest discover -s scripts/docs
"""
import tempfile
import unittest
from pathlib import Path

import generate_cli_reference as gen


class FindJarTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.target = self.repo / "pcml-cli" / "target"
        self.target.mkdir(parents=True)
        self._real_repo = gen.REPO
        gen.REPO = self.repo
        self.addCleanup(self._restore)

    def _restore(self):
        gen.REPO = self._real_repo

    def touch(self, name):
        (self.target / name).write_text("", encoding="utf-8")

    def test_the_plain_jar_is_found(self):
        self.touch("pcml-cli-0.1.0-alpha.1.jar")
        self.assertEqual(self.target / "pcml-cli-0.1.0-alpha.1.jar", gen.find_jar())

    def test_sources_and_javadoc_jars_are_excluded(self):
        self.touch("pcml-cli-0.1.0-alpha.1-sources.jar")
        self.touch("pcml-cli-0.1.0-alpha.1-javadoc.jar")
        self.touch("pcml-cli-0.1.0-alpha.1.jar")
        self.assertEqual(self.target / "pcml-cli-0.1.0-alpha.1.jar", gen.find_jar())

    def test_no_jar_at_all_raises_a_clear_error(self):
        with self.assertRaises(FileNotFoundError):
            gen.find_jar()


if __name__ == "__main__":
    unittest.main()

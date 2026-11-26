#!/usr/bin/env python3
# Apache License 2.0. Origin: slay400-core, https://github.com/generativearchitects-ai/slay400-core (decision 151).
"""Tests of _snippets.py. Run with: python3 -m unittest discover -s scripts/docs"""
import tempfile
import unittest
from pathlib import Path

import _snippets


class SnippetsInTest(unittest.TestCase):

    def test_a_marked_block_is_found_with_its_source_region_and_body(self):
        page = ("<!-- snippet: examples/quickstart/steps.sh#init -->\n```sh\nslay400 init\n```\n")
        found = _snippets.snippets_in(page)
        self.assertEqual(1, len(found))
        self.assertEqual("examples/quickstart/steps.sh", found[0].source)
        self.assertEqual("init", found[0].region)
        self.assertEqual("slay400 init", found[0].shown_body)

    def test_a_marker_with_no_region_is_a_whole_file_snippet(self):
        page = "<!-- snippet: examples/quickstart/expected/check.out -->\n```text\nslay400 <version>\n```\n"
        found = _snippets.snippets_in(page)
        self.assertIsNone(found[0].region)

    def test_two_snippets_showing_identical_text_get_distinct_spans(self):
        page = ("<!-- snippet: examples/e/steps.sh#a -->\n```sh\nsame\n```\n\n"
                "<!-- snippet: examples/e/steps.sh#b -->\n```sh\nsame\n```\n")
        found = _snippets.snippets_in(page)
        self.assertEqual(2, len(found))
        self.assertNotEqual(found[0].span, found[1].span)
        self.assertLess(found[0].span[1], found[1].span[0])

    def test_unmarked_fence_is_reported_with_its_language(self):
        page = "```json\n{}\n```\n"
        self.assertEqual(["json"], _snippets.unmarked_fences(page))

    def test_a_fence_covered_by_a_marker_is_not_reported_as_unmarked(self):
        page = "<!-- snippet: examples/e/steps.sh#a -->\n```sh\nx\n```\n"
        self.assertEqual([], _snippets.unmarked_fences(page))

    def test_regions_in_a_script_are_found_in_order_without_the_markers(self):
        script = ("#!/bin/sh\n# region: a\necho one\n# endregion\n\n# region: b\necho two\necho three\n# endregion\n")
        regions = _snippets.regions_in(script)
        self.assertEqual(["echo one"], regions["a"])
        self.assertEqual(["echo two", "echo three"], regions["b"])

    def test_an_unterminated_region_is_simply_not_recorded(self):
        script = "# region: a\necho one\n"
        self.assertEqual({}, _snippets.regions_in(script))


class ResolveTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.docs = Path(self.tmp.name) / "docs"
        self.examples = self.docs / "examples"
        self.examples.mkdir(parents=True)
        self._real_examples = _snippets.EXAMPLES
        _snippets.EXAMPLES = self.examples
        self.addCleanup(self._restore)

    def _restore(self):
        _snippets.EXAMPLES = self._real_examples

    def test_resolving_a_whole_file_strips_one_trailing_newline(self):
        (self.examples / "e").mkdir()
        (self.examples / "e" / "out.txt").write_text("hello\n", encoding="utf-8")
        self.assertEqual("hello", _snippets.resolve("examples/e/out.txt", None))

    def test_resolving_a_region_joins_its_lines(self):
        (self.examples / "e").mkdir()
        (self.examples / "e" / "steps.sh").write_text(
            "# region: a\nline one\nline two\n# endregion\n", encoding="utf-8")
        self.assertEqual("line one\nline two", _snippets.resolve("examples/e/steps.sh", "a"))

    def test_an_unknown_region_raises_key_error(self):
        (self.examples / "e").mkdir()
        (self.examples / "e" / "steps.sh").write_text("# region: a\nx\n# endregion\n", encoding="utf-8")
        with self.assertRaises(KeyError):
            _snippets.resolve("examples/e/steps.sh", "missing")

    def test_a_missing_file_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            _snippets.resolve("examples/missing/steps.sh", None)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests of _pages.py. Run with: python3 -m unittest discover -s scripts/docs"""
import tempfile
import unittest
from pathlib import Path

import _pages


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


FRONT_MATTER = "---\ntitle: A page\ndescription: Something\nsection: guides\nslug: a-page\norder: 1\nappliesTo: \"0.1\"\n---\n"


class PagesTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_a_page_under_a_section_is_found(self):
        write(self.root / "guides" / "a-page" / "index.md", FRONT_MATTER + "# A page\n")
        self.assertEqual([self.root / "guides" / "a-page" / "index.md"], _pages.pages(self.root))

    def test_readme_is_excluded(self):
        write(self.root / "guides" / "a-page" / "index.md", FRONT_MATTER)
        write(self.root / "README.md", "not a page")
        self.assertEqual([self.root / "guides" / "a-page" / "index.md"], _pages.pages(self.root))

    def test_examples_and_assets_are_excluded(self):
        write(self.root / "examples" / "foo" / "README.md", "x")
        write(self.root / "assets" / "notes.md", "x")
        self.assertEqual([], _pages.pages(self.root))

    def test_a_file_or_folder_starting_with_underscore_is_excluded(self):
        write(self.root / "reference" / "_notes" / "thing.md", "x")
        write(self.root / "reference" / "cli" / "_draft.md", "x")
        self.assertEqual([], _pages.pages(self.root))

    def test_a_symbolic_link_under_docs_is_a_hard_failure(self):
        target = write(self.root / "guides" / "a-page" / "index.md", FRONT_MATTER)
        link_dir = self.root / "guides" / "linked"
        link_dir.mkdir(parents=True)
        (link_dir / "index.md").symlink_to(target)
        with self.assertRaises(_pages.PageError):
            _pages.pages(self.root)

    def test_front_matter_is_parsed_as_key_value_pairs(self):
        page = write(self.root / "p.md", FRONT_MATTER + "# A page\n")
        fields = _pages.front_matter(page)
        self.assertEqual("A page", fields["title"])
        self.assertEqual("guides", fields["section"])
        self.assertEqual("1", fields["order"])

    def test_a_quoted_value_has_its_quotes_stripped(self):
        page = write(self.root / "p.md", FRONT_MATTER + "# A page\n")
        self.assertEqual("0.1", _pages.front_matter(page)["appliesTo"])

    def test_a_page_with_no_front_matter_block_is_rejected(self):
        page = write(self.root / "p.md", "# A page\n")
        with self.assertRaises(_pages.PageError):
            _pages.front_matter(page)

    def test_a_front_matter_line_that_is_not_key_value_is_rejected(self):
        page = write(self.root / "p.md", "---\ntitle A page\n---\n")
        with self.assertRaises(_pages.PageError):
            _pages.front_matter(page)

    def test_body_is_the_text_after_the_front_matter_block(self):
        page = write(self.root / "p.md", FRONT_MATTER + "# A page\n\nHello.\n")
        self.assertEqual("# A page\n\nHello.\n", _pages.body(page))

    def test_body_is_the_whole_text_when_there_is_no_front_matter(self):
        page = write(self.root / "p.md", "# A page\n")
        self.assertEqual("# A page\n", _pages.body(page))


if __name__ == "__main__":
    unittest.main()

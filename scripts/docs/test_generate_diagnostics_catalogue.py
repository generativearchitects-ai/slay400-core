#!/usr/bin/env python3
# Apache License 2.0. Origin: slay400-core, https://github.com/generativearchitects-ai/slay400-core (decision 151).
"""Tests of generate_diagnostics_catalogue.py. Run with: python3 -m unittest discover -s scripts/docs"""
import unittest

import generate_diagnostics_catalogue as gen


class MessageTemplateTest(unittest.TestCase):

    def test_a_single_literal_is_returned_as_is(self):
        self.assertEqual("plain message", gen.message_template('"plain message", location)'))

    def test_concatenated_literals_with_a_value_between_them_get_a_placeholder(self):
        rest = '"the value \'" + value + "\' is wrong", location)'
        self.assertEqual("the value '<value>' is wrong", gen.message_template(rest))

    def test_a_message_built_entirely_from_a_value_has_no_literal_parts(self):
        self.assertEqual("(message built from a value, not literal text)", gen.message_template("value, location)"))

    def test_stops_at_the_first_top_level_comma(self):
        rest = '"message", location, extra)'
        self.assertEqual("message", gen.message_template(rest))

    def test_a_comma_inside_a_literal_does_not_end_the_scan(self):
        rest = '"a, b", location)'
        self.assertEqual("a, b", gen.message_template(rest))


class SeverityAndMessageStartTest(unittest.TestCase):

    def test_a_direct_new_diagnostic_call_finds_severity_right_after_the_code(self):
        text = 'new Diagnostic("OVL012", Severity.ERROR, "bad route", at)'
        code_start, code_end = text.index('"OVL012"'), text.index('"OVL012"') + len('"OVL012"')
        result = gen.severity_and_message_start(text, code_start, code_end)
        self.assertIsNotNone(result)
        severity, message_start = result
        self.assertEqual("ERROR", severity)
        self.assertEqual('"bad route", at)', text[message_start:])

    def test_a_same_file_helper_is_found_by_name_before_the_code(self):
        text = 'yaml.error("OVL012", "bad route", at);'
        code_start, code_end = text.index('"OVL012"'), text.index('"OVL012"') + len('"OVL012"')
        result = gen.severity_and_message_start(text, code_start, code_end)
        self.assertEqual("ERROR", result[0])
        self.assertEqual('"bad route", at);', text[result[1]:])

    def test_a_warning_helper_resolves_to_warning_severity(self):
        text = 'yaml.warning("OVL006", "no mapping", at);'
        code_start, code_end = text.index('"OVL006"'), text.index('"OVL006"') + len('"OVL006"')
        severity, _ = gen.severity_and_message_start(text, code_start, code_end)
        self.assertEqual("WARNING", severity)

    def test_a_problems_add_call_is_always_an_error(self):
        text = 'problems.add("VAL001", where, "bad value");'
        code_start, code_end = text.index('"VAL001"'), text.index('"VAL001"') + len('"VAL001"')
        severity, message_start = gen.severity_and_message_start(text, code_start, code_end)
        self.assertEqual("ERROR", severity)
        self.assertEqual('"bad value");', text[message_start:])

    def test_a_later_comparison_against_the_code_is_not_a_construction_site(self):
        text = 'if (d.code().equals("OVL012")) {'
        code_start, code_end = text.index('"OVL012"'), text.index('"OVL012"') + len('"OVL012"')
        self.assertIsNone(gen.severity_and_message_start(text, code_start, code_end))


class RenderTest(unittest.TestCase):

    def test_a_code_with_no_notes_file_is_reported_missing(self):
        codes = {"XYZ001": ("ERROR", "boom", "f.java:1")}
        rendered, missing = gen.render(codes)
        self.assertEqual(["XYZ001"], missing)
        self.assertIn("XYZ001", rendered)
        self.assertIn("boom", rendered)

    def test_rendering_is_sorted_by_code(self):
        codes = {"B002": ("ERROR", "b", "f.java:2"), "A001": ("WARNING", "a", "f.java:1")}
        rendered, _ = gen.render(codes)
        self.assertLess(rendered.index("## A001"), rendered.index("## B002"))


if __name__ == "__main__":
    unittest.main()

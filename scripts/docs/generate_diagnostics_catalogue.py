#!/usr/bin/env python3
# Apache License 2.0. Origin: slay400-core, https://github.com/generativearchitects-ai/slay400-core (decision 151).
"""Generates docs/reference/diagnostics/index.md: every diagnostic code the modules can produce, with severity,
the message as printed, and hand-written notes (meaning, what to do) from docs/reference/_notes/diagnostics/
(specs/documentation.md section 7). A code found in the source with no notes file fails the check.

There is no central registry of codes (checked directly): each is a string literal at its `new Diagnostic(code,
Severity.X, message, location)` call, or at a same-file `error(code, message, location)` / `warning(...)` /
`info(...)` helper that forwards to one. Both shapes are found by scanning every */src/main/java/**/*.java file.
Messages built by string concatenation (most of them) are rendered as a template, with each interpolated part
replaced by `<value>`: this is the message's shape, not a literal run's text, and said so on the page.

Usage: generate_diagnostics_catalogue.py [--check]

Needs Python 3 and nothing else. Exit code 0: written (or, with --check, already current and every code has
notes). 1: a code has no notes file, or (with --check) the committed file is stale.
"""
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
TARGET = REPO / "docs" / "reference" / "diagnostics" / "index.md"
NOTES = REPO / "docs" / "reference" / "_notes" / "diagnostics"

CODE = r'"([A-Z]{2,4}[0-9]{3})"'
# Every call that constructs a diagnostic names its code as the first string-literal argument; some do it directly
# (new Diagnostic("CODE", Severity.X, ...)), some through a one-line, same-file helper named error/warning/info,
# or named differently per module (there is no one convention) but still followed, within the same statement, by
# a literal Severity.X. Both shapes are covered the same way: a quoted code, then a Severity token close enough
# to be part of the same construction, not a later comparison like `d.code().equals("OVL012")`.
_CODE_LITERAL = re.compile(CODE)
_SEVERITY_NEARBY = re.compile(r"\s*,\s*(?:[A-Za-z_][A-Za-z0-9_.()\[\]\s]*?,\s*)?Severity\.(ERROR|WARNING|INFO)\s*,\s*")
_STRING_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')


def message_template(rest: str) -> str:
    """The message argument of a Diagnostic/helper call: the Java string literals it is built from, joined with
    <value> where the code concatenates something else (a variable, a method call, another literal's +)."""
    depth = 0
    i = 0
    parts = []
    saw_non_literal_gap = False
    while i < len(rest):
        ch = rest[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                break
            depth -= 1
        elif ch == "," and depth == 0:
            break
        if ch == '"':
            m = _STRING_LITERAL.match(rest, i)
            if m:
                if saw_non_literal_gap and parts:
                    parts.append("<value>")
                parts.append(m.group(1))
                i = m.end()
                saw_non_literal_gap = False
                continue
        elif not ch.isspace() and ch != "+":
            saw_non_literal_gap = True
        i += 1
    return "".join(parts) if parts else "(message built from a value, not literal text)"


_HELPER_NAME = re.compile(r"\b(error|warning|info)\s*\($")
_HELPER_SEVERITY = {"error": "ERROR", "warning": "WARNING", "info": "INFO"}
_ADD_CALL = re.compile(r"\.add\s*\($")


def severity_and_message_start(text: str, code_start: int, code_end: int) -> tuple[str, int] | None:
    """The severity a code literal's construction names, and where its message argument starts: either right
    after a Severity.X that follows the code, or right after the code's own comma for an error/warning/info
    helper (which takes no Severity argument, severity is the helper's own name). None if neither shape matches
    (the code was not constructing a diagnostic here, for example a later `d.code().equals("OVL012")`)."""
    after = _SEVERITY_NEARBY.match(text, code_end)
    if after:
        return after.group(1), after.end()
    before = text[max(0, code_start - 40):code_start]
    name = _HELPER_NAME.search(before)
    if name:
        comma = re.match(r"\s*,\s*", text[code_end:])
        return _HELPER_SEVERITY[name.group(1)], code_end + (comma.end() if comma else 0)
    # pcml-codec's own convention: problems.add("CODE", where, "message") -- a collection of value problems, always
    # reported as errors (ValueProblem itself carries no severity; see its javadoc for what each VAL/MCK/DSC/REQ
    # code means, which is where this module's codes are documented instead of at the call site).
    if _ADD_CALL.search(before):
        skip_one_arg = re.match(r"\s*,\s*[^,()]*\s*,\s*", text[code_end:])
        if skip_one_arg:
            return "ERROR", code_end + skip_one_arg.end()
    return None


def scan() -> dict[str, tuple[str, str, str]]:
    """code -> (severity, message template, file:line of the first call site found)."""
    found: dict[str, tuple[str, str, str]] = {}
    for java_file in sorted(REPO.glob("*/src/main/java/**/*.java")):
        text = java_file.read_text(encoding="utf-8")
        for m in _CODE_LITERAL.finditer(text):
            code = m.group(1)
            if code in found:
                continue
            resolved = severity_and_message_start(text, m.start(), m.end())
            if resolved is None:
                continue
            severity, message_start = resolved
            line = text.count("\n", 0, m.start()) + 1
            found[code] = (severity, message_template(text[message_start:]), f"{java_file.relative_to(REPO)}:{line}")
    return found


FRONT_MATTER = """---
title: Diagnostics catalogue
description: Every diagnostic code the generator can produce, its severity, the message as printed, what it means and what to do.
section: reference
slug: diagnostics
order: 30
appliesTo: "0.1"
---
"""


def render(codes: dict[str, tuple[str, str, str]]) -> tuple[str, list[str]]:
    missing = []
    lines = [FRONT_MATTER.rstrip("\n"), "",
              "<!-- Generated by scripts/docs/generate_diagnostics_catalogue.py from the source and docs/reference/_notes/diagnostics/. Do not edit by hand. -->",
              "", "# Diagnostics catalogue", "",
              "Every diagnostic code the generator can produce, with its severity, the message as printed (a value the code"
              " fills in at the point marked `<value>`), what it means and what to do.", ""]
    for code in sorted(codes):
        severity, message, location = codes[code]
        notes_file = NOTES / f"{code}.md"
        lines += [f"## {code}", "", f"Severity: **{severity.lower()}**. First seen at `{location}`.", "",
                  "It prints:", "", f"> {message}", ""]
        if notes_file.is_file():
            lines += [notes_file.read_text(encoding="utf-8").strip(), ""]
        else:
            missing.append(code)
    return "\n".join(lines) + "\n", missing


def main(argv):
    parser = argparse.ArgumentParser(description="Generates the diagnostics catalogue from the source and hand-written notes.")
    parser.add_argument("--check", action="store_true", help="fail if stale or a code has no notes, instead of writing it")
    args = parser.parse_args(argv)
    codes = scan()
    rendered, missing = render(codes)
    if missing:
        for code in missing:
            print(f"FAIL: {code} has no notes file at {NOTES / (code + '.md')}")
        print(f"{len(missing)} problem(s)")
        return 1
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else None
        if current != rendered:
            print(f"FAIL: {TARGET} is stale; run scripts/docs/generate_diagnostics_catalogue.py")
            return 1
        print(f"OK: the diagnostics catalogue is current, {len(codes)} codes")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(rendered, encoding="utf-8")
    print(f"Wrote {TARGET}, {len(codes)} codes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

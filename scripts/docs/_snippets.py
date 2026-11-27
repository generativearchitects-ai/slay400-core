# Apache License 2.0. Origin: slay400-core, https://github.com/generativearchitects-ai/slay400-core (decision 151).
"""Shared by docs:snippets and docs:examples: snippet markers in a page, and the source they name
(specs/documentation.md section 5).
"""
import re
from dataclasses import dataclass
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent.parent.parent / "docs" / "examples"

# <!-- snippet: examples/<example>/steps.sh[#<region>] -->, then a fenced code block.
_MARKER = re.compile(r"<!--\s*snippet:\s*(?P<source>examples/[^\s#]+)(?:#(?P<region>[^\s]+))?\s*-->\n```[^\n]*\n(?P<body>.*?)\n```", re.DOTALL)
_PLAIN_FENCE = re.compile(r"(?<!-->\n)```(?P<lang>[^\n]*)\n(?P<body>.*?)\n```", re.DOTALL)
_ANY_FENCE = re.compile(r"```[^\n]*\n.*?\n```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_REGION = re.compile(r"^#\s*region:\s*(?P<name>\S+)\s*$")
_ENDREGION = re.compile(r"^#\s*endregion\s*$")


@dataclass(frozen=True)
class Snippet:
    """One marked code block in a page: where it is (source, region), what it shows (body), and the body's
    character span in the page text (so a caller can replace it by position, not by content -- two snippets can
    legitimately show the same text, and content-based replacement would edit the wrong one)."""
    source: str  # "examples/<example>/<file>", relative to docs/
    region: str | None
    shown_body: str
    span: tuple[int, int]


def snippets_in(page_text: str) -> list[Snippet]:
    """Every marked snippet in a page's body, in order."""
    return [Snippet(m.group("source"), m.group("region"), m.group("body"), m.span("body")) for m in _MARKER.finditer(page_text)]


def unmarked_fences(page_text: str) -> list[str]:
    """Fenced code blocks with no snippet marker on the line before them (checked separately: text-language ones
    that show a shape, not a real output, are allowed if the sentence before says so -- not verified here)."""
    marked_spans = [(m.start(), m.end()) for m in _MARKER.finditer(page_text)]

    def covered(pos):
        return any(start <= pos < end for start, end in marked_spans)

    return [m.group("lang") for m in _PLAIN_FENCE.finditer(page_text) if not covered(m.start())]


def strip_code(page_text: str) -> str:
    """page_text with every fenced code block and every inline code span blanked out (spaces, same length, so
    line numbers and every other character's position are unchanged) -- for a check that must look only at
    prose, such as the no-raw-HTML rule (specs/documentation.md sections 4 and 7, kickoff 19)."""

    def blank(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    return _INLINE_CODE.sub(blank, _ANY_FENCE.sub(blank, page_text))


def regions_in(script_text: str) -> dict[str, list[str]]:
    """Every "# region: <name>" ... "# endregion" block in a script, name -> its lines (markers excluded)."""
    found: dict[str, list[str]] = {}
    current = None
    lines: list[str] = []
    for line in script_text.splitlines():
        start = _REGION.match(line)
        if start:
            current = start.group("name")
            lines = []
            continue
        if _ENDREGION.match(line) and current is not None:
            found[current] = lines
            current = None
            continue
        if current is not None:
            lines.append(line)
    return found


def resolve(source: str, region: str | None) -> str:
    """The text a snippet marker names: the whole file, or one of its regions, joined with newlines."""
    path = EXAMPLES.parent / source
    text = path.read_text(encoding="utf-8")
    if region is None:
        return text.rstrip("\n")
    found = regions_in(text)
    if region not in found:
        raise KeyError(f"{source} has no region {region!r}")
    return "\n".join(found[region])

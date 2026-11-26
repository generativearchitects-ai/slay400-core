# Apache License 2.0. Origin: slay400-core, https://github.com/generativearchitects-ai/slay400-core (decision 151).
"""Shared by the documentation checks: what counts as a page, and its front matter.

specs/documentation.md section 2: every .md file under docs/, except README.md files, everything under examples/
and assets/, and any file or folder whose name starts with "_". Section 4: the front matter is flat key: value
pairs (no nesting, no lists) -- simple enough to read without a YAML library, which no script in this repository
uses (all of scripts/*.py are standard library only; a front-matter-only reader keeps that true here too).
"""
import re
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent.parent / "docs"

REQUIRED_FIELDS = ["title", "description", "section", "slug", "order", "appliesTo"]
OPTIONAL_FIELDS = ["time"]
SECTIONS = ["get-started", "tutorials", "guides", "reference", "concepts"]

_FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9]*):[ \t]*(.*?)[ \t]*$")


class PageError(Exception):
    """A page or its front matter is malformed; args[0] is the message, args[1] the file."""


def is_excluded(path: Path, root: Path = DOCS) -> bool:
    """A folder or file name starting with "_", or a symbolic link, anywhere from root down to path."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    for part in relative.parts:
        if part.startswith("_"):
            return True
    return False


def pages(root: Path = DOCS) -> list[Path]:
    """Every page under root, in a stable order. Raises PageError on a symbolic link under root."""
    found = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise PageError(f"{path} is a symbolic link, not allowed under docs/", path)
        if not path.is_file() or path.suffix != ".md":
            continue
        if path.name == "README.md":
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            relative = path
        top = relative.parts[0] if relative.parts else ""
        if top in ("examples", "assets"):
            continue
        if is_excluded(path, root):
            continue
        found.append(path)
    return found


def front_matter(path: Path) -> dict[str, str]:
    """The front matter of a page, as a dict of strings (order and time are strings here; parse them to check ranges)."""
    text = path.read_text(encoding="utf-8")
    match = _FRONT_MATTER.match(text)
    if not match:
        raise PageError(f"{path}: no front matter block (--- ... ---) at the start of the file", path)
    fields = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        parsed = _LINE.match(line)
        if not parsed:
            raise PageError(f"{path}: front matter line is not 'key: value': {line!r}", path)
        key, value = parsed.group(1), parsed.group(2)
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
        fields[key] = value
    return fields


def body(path: Path) -> str:
    """The page's text after the front matter block."""
    text = path.read_text(encoding="utf-8")
    match = _FRONT_MATTER.match(text)
    return text[match.end():] if match else text

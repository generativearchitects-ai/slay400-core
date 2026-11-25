#!/usr/bin/env python3
"""The front matter and page-shape checks of specs/documentation.md sections 2 and 4 (kickoff 16).

Checked for every page (_pages.pages()):
  * front matter has every required field, with a valid value (title <= 60 chars and no product name, section one
    of the five, order an integer, appliesTo and description non-empty, time only for get-started/tutorials);
  * slugs are unique within their section (within this repository only: the gateway repository's pages are not
    visible here, so cross-repository uniqueness is not checked -- say so if it matters);
  * the page's first heading is one "#" heading equal to the title;
  * a get-started or tutorials page has a "Before you start" section;
  * every link is a site address (/docs/<section>/<slug>/), a full https:// address, or a same-page anchor --
    never a relative link to a repository file.

Needs Python 3 and nothing else. Exit code 0: no problem. 1: problems, one per line.
"""
import re
import sys
from pathlib import Path

import _pages

_HEADING = re.compile(r"^#\s+(.+?)\s*$")
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
_PRODUCT_NAME = re.compile(r"slay400", re.IGNORECASE)


def check_one(page) -> list[str]:
    problems = []
    try:
        fields = _pages.front_matter(page)
    except _pages.PageError as e:
        return [str(e)]

    for field in _pages.REQUIRED_FIELDS:
        if not fields.get(field):
            problems.append(f"{page}: front matter is missing '{field}'")
    if "title" in fields:
        if len(fields["title"]) > 60:
            problems.append(f"{page}: title is longer than 60 characters")
        if _PRODUCT_NAME.search(fields["title"]):
            problems.append(f"{page}: title names the product")
    if "section" in fields and fields["section"] not in _pages.SECTIONS:
        problems.append(f"{page}: section '{fields['section']}' is not one of {_pages.SECTIONS}")
    if "order" in fields and not re.fullmatch(r"-?\d+", fields["order"]):
        problems.append(f"{page}: order '{fields['order']}' is not an integer")
    if "time" in fields and fields.get("section") not in ("get-started", "tutorials"):
        problems.append(f"{page}: 'time' is only for get-started and tutorials pages")

    body = _pages.body(page)
    lines = [line for line in body.splitlines() if line.strip()]
    while lines and lines[0].startswith("<!--") and lines[0].rstrip().endswith("-->"):
        lines.pop(0)  # a generated page's "do not edit by hand" comment, which stands before its heading
    heading = _HEADING.match(lines[0]) if lines else None
    if not heading:
        problems.append(f"{page}: the page does not start with one '#' heading")
    elif "title" in fields and heading.group(1) != fields["title"]:
        problems.append(f"{page}: the '#' heading ({heading.group(1)!r}) does not equal the title ({fields['title']!r})")

    if fields.get("section") in ("get-started", "tutorials") and "Before you start" not in body:
        problems.append(f"{page}: a get-started or tutorials page needs a 'Before you start' section")

    for target in _LINK.findall(body):
        target = target.split(" ", 1)[0]  # drop a markdown link title, '"...": "title"'
        if target.startswith(("http://", "https://", "/docs/", "#")):
            continue
        problems.append(f"{page}: link to '{target}' is relative; link to another page as /docs/<section>/<slug>/"
                         " or to a repository file as a full https://github.com/... address")
    return problems


def check(root: Path | None = None) -> list[str]:
    problems = []
    try:
        all_pages = _pages.pages(root) if root is not None else _pages.pages()
    except _pages.PageError as e:
        return [str(e)]
    slugs: dict[tuple[str, str], list] = {}
    for page in all_pages:
        problems.extend(check_one(page))
        try:
            fields = _pages.front_matter(page)
        except _pages.PageError:
            continue
        if "section" in fields and "slug" in fields:
            slugs.setdefault((fields["section"], fields["slug"]), []).append(page)
    for (section, slug), pages_with_it in slugs.items():
        if len(pages_with_it) > 1:
            problems.append(f"slug '{slug}' in section '{section}' is used by more than one page: {pages_with_it}")
    return problems


def main(argv):
    problems = check()
    for problem in problems:
        print("FAIL: " + problem)
    if problems:
        print(f"{len(problems)} problem(s)")
        return 1
    print("OK: every page's front matter and shape is valid")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

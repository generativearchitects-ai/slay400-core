#!/usr/bin/env python3
"""Checks whether a tag can be released (kickoff 20, decision 155): main always carries a snapshot version, and a
release takes its own version only from the tag -- this is the one gate before anything is built or signed.

Usage: check_release_tag.py [--repo DIR] [--commit REF] [--main REF] TAG   (TAG, for example v0.1.0 or v0.1.0-alpha.2)

A tag can be released when:
  * it is "v" followed by a release version of the form MAJOR.MINOR.PATCH, with an optional pre-release part
    (-alpha.1, -rc.2), and that version is not itself a snapshot;
  * COMMIT (default: HEAD) is an ancestor of MAIN (default: origin/main) -- a tag on a commit that is not in main
    is never released;
  * its MAJOR.MINOR.PATCH is the line of the snapshot in the root pom.xml (v0.1.0-alpha.2 and v0.1.0 are accepted
    on 0.1.0-SNAPSHOT; v0.2.0 is refused, with a message to move main to 0.2.0-SNAPSHOT first);
  * every module, pcml-bom included, has that same snapshot version;
  * no tag of this exact name already exists at a different commit (one that already points at COMMIT is fine:
    that is this very release, made from GitHub's release page before the workflow ran, or checked again by hand);
  * the version is not already published on Maven Central -- checked for the root artifact, and only if Central's
    public search can be reached without credentials; a network problem is reported, never a reason to refuse.

The same shape of version (MAJOR.MINOR.PATCH, optionally with a pre-release part) is what install.sh / install.ps1
accept as an explicit version argument, after their own, separate check that it contains none of "/", "\\" or
"..": see the case statement in install.sh and the -notmatch check in install.ps1's Install-Slay400.

Needs Python 3, git on PATH, and, for the Central check only, a reachable network. Nothing is written or changed.
Exit code 0: the tag can be released; 1: problems, one per line.
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "{http://maven.apache.org/POM/4.0.0}"
BOM = "pcml-bom"
TAG = re.compile(r"^v(\d+\.\d+\.\d+)(-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?$")
CENTRAL_SEARCH = "https://search.maven.org/solrsearch/select"


def _text(element, *names):
    for name in names:
        element = None if element is None else element.find(NS + name)
    return element.text.strip() if element is not None and element.text else None


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def tag_commit(repo: Path, tag: str) -> str | None:
    """The commit TAG points at in repo, or None if no such tag exists."""
    result = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}")
    return result.stdout.strip() or None if result.returncode == 0 else None


def is_ancestor(repo: Path, commit: str, ref: str) -> bool:
    return _git(repo, "merge-base", "--is-ancestor", commit, ref).returncode == 0


def central_has_version(group_id: str, artifact_id: str, version: str, timeout: float = 10) -> bool | None:
    """True/False once Maven Central's public search answers; None if it could not be asked -- a network problem,
    never a reason to refuse a tag."""
    query = f'g:"{group_id}" AND a:"{artifact_id}" AND v:"{version}"'
    url = f"{CENTRAL_SEARCH}?{urllib.parse.urlencode({'q': query, 'core': 'gav', 'rows': '1', 'wt': 'json'})}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = json.loads(response.read())
        return data["response"]["numFound"] > 0
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError):
        return None


def check(tag: str, repo: Path, commit: str = "HEAD", main: str = "origin/main") -> tuple[list[str], list[str]]:
    """(problems, notes): problems that refuse the tag; notes that do not (a Central check that could not be
    made). Nothing is written or changed."""
    problems: list[str] = []
    notes: list[str] = []

    match = TAG.fullmatch(tag)
    line = version = None
    if not match:
        problems.append(f"the tag {tag!r} is not v<MAJOR.MINOR.PATCH>, optionally with a pre-release part"
                         " (for example v0.1.0 or v0.1.0-alpha.2)")
    else:
        line = match.group(1)
        version = line + (match.group(2) or "")
        if version.endswith("-SNAPSHOT"):
            problems.append(f"the version {version} is a snapshot: tag a release version, not a snapshot")

    resolved_commit = _git(repo, "rev-parse", "--verify", "--quiet", commit + "^{commit}").stdout.strip()
    if not resolved_commit:
        problems.append(f"{commit!r} does not resolve to a commit in {repo}")
    elif not is_ancestor(repo, resolved_commit, main):
        problems.append(f"the commit {resolved_commit} is not an ancestor of {main}: tag a commit that is in main")

    root = ET.parse(repo / "pom.xml").getroot()
    snapshot = _text(root, "version")
    if snapshot is None:
        problems.append("the root pom.xml has no version")
    else:
        if not snapshot.endswith("-SNAPSHOT"):
            problems.append(f"the project version {snapshot} is not a snapshot: main must always carry a snapshot version")
        elif line is not None:
            snapshot_line = snapshot[: -len("-SNAPSHOT")]
            if line != snapshot_line:
                problems.append(f"the tag {tag} is not on the line of the snapshot {snapshot}: move main to {line}-SNAPSHOT first")
        # Independent of whether the root itself is a valid snapshot: every module must still agree with it.
        for module in root.find(NS + "modules"):
            name = module.text.strip()
            pom = ET.parse(repo / name / "pom.xml").getroot()
            found = _text(pom, "version") if name == BOM else _text(pom, "parent", "version")
            if found != snapshot:
                problems.append(f"{name} has the version {found}, the project has the snapshot {snapshot}")

    if resolved_commit:
        existing = tag_commit(repo, tag)
        if existing is not None and existing != resolved_commit:
            problems.append(f"the tag {tag} already exists, at commit {existing}, not {resolved_commit}")

    if version is not None:
        group_id, artifact_id = _text(root, "groupId"), _text(root, "artifactId")
        if group_id and artifact_id:
            has = central_has_version(group_id, artifact_id, version)
            if has is True:
                problems.append(f"{group_id}:{artifact_id}:{version} already exists on Maven Central")
            elif has is None:
                notes.append("could not reach Maven Central's search to check whether the version is already published")

    return problems, notes


def main(argv):
    parser = argparse.ArgumentParser(description="Checks whether a tag can be released.")
    parser.add_argument("tag", help="the name of the tag, for example v0.1.0")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent, help="the repository root")
    parser.add_argument("--commit", default="HEAD", help="the commit the tag is for (default: HEAD)")
    parser.add_argument("--main", default="origin/main", help="the ref that the commit must be an ancestor of (default: origin/main)")
    args = parser.parse_args(argv)
    problems, notes = check(args.tag, args.repo, args.commit, args.main)
    for note in notes:
        print("NOTE: " + note)
    for problem in problems:
        print("FAIL: " + problem)
    if problems:
        return 1
    print(f"OK: the tag {args.tag} can be released")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

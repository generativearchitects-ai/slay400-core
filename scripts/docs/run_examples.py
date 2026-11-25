#!/usr/bin/env python3
"""docs:examples (specs/documentation.md section 5, kickoff 16): runs every example's steps.sh, region by region, in
a clean temporary folder, with the tool built from this commit, and compares what each region prints (stdout and
stderr merged, as a terminal shows them) with docs/examples/<example>/expected/<region>.out. Fails on an example
no page's snippet marker uses, and on a region no page shows.

A region whose lines include "# requires: ibmi" is never run (it needs a real IBM i); its recorded output, when
there is one, is committed by hand, not generated here.

One deliberate substitution, documented because it is the one place this runner does not run the literal page
text: a line that is exactly the real "curl ... install.sh | sh" command is run as the local, just-checked-out
install.sh instead of fetching it from GitHub -- so the test is of the tool built from *this* commit, matching
the rule above, not of whatever is on the default branch. The page still shows the real command; a reader who
pastes it gets the real download.

Usage: run_examples.py [--write]
--write captures each region's output into expected/<region>.out instead of comparing against it.

Needs Python 3, a POSIX shell (sh) and curl -- all already needed by install.sh itself, which some regions run
unmodified. Needs the archive pcml-launcher just built (pcml-launcher/target/pcml-launcher-*.tar.gz): run
./mvnw verify, or at least `./mvnw -pl pcml-launcher -am package -DskipTests`, first.

Exit code 0: every region's output matches (or was captured). 1: problems, one per line.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import _pages
import _snippets

REPO = Path(__file__).resolve().parent.parent.parent
EXAMPLES = REPO / "docs" / "examples"
INSTALL_LINE = re.compile(
    r"curl -fsSL https://raw\.githubusercontent\.com/generativearchitects-ai/slay400-core/main/install\.sh \| sh")
REQUIRES = re.compile(r"#\s*requires:\s*(\S+)")


def project_version() -> str:
    root = ET.parse(REPO / "pom.xml").getroot()
    return root.find("{http://maven.apache.org/POM/4.0.0}version").text


def example_dirs() -> list[Path]:
    return sorted(p for p in EXAMPLES.iterdir() if p.is_dir() and (p / "steps.sh").is_file())


def requires_ibmi(lines: list[str]) -> bool:
    return any(REQUIRES.match(line.strip()) and REQUIRES.match(line.strip()).group(1) == "ibmi" for line in lines)


def build_standin(standin: Path, version: str) -> None:
    """A local stand-in for GitHub Releases, serving the archive pcml-launcher just built, via file:// URLs."""
    archives = glob.glob(str(REPO / "pcml-launcher" / "target" / f"pcml-launcher-{version}.tar.gz"))
    if not archives:
        raise FileNotFoundError(
            f"pcml-launcher/target/pcml-launcher-{version}.tar.gz was not found; build it first (./mvnw verify)")
    download = standin / "download" / f"v{version}"
    download.mkdir(parents=True)
    archive = download / f"slay400-{version}.tar.gz"
    shutil.copyfile(archives[0], archive)
    import hashlib
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (download / f"{archive.name}.sha256").write_text(f"{digest}  {archive.name}\n")
    api = standin / "api"
    api.mkdir(parents=True)
    (api / "latest").write_text(json.dumps({"tag_name": f"v{version}"}))


_SENTINEL = "==EXAMPLE_REGION_END:{}=="
_SENTINEL_SPLIT = re.compile(r"\n?==EXAMPLE_REGION_END:(\S+)==\n?")


def instrument(steps_sh: Path) -> tuple[str, list[str]]:
    """The script text to actually run (sentinels inserted, ibmi-only regions removed) and the region order."""
    text = steps_sh.read_text(encoding="utf-8")
    regions = _snippets.regions_in(text)
    out_lines = []
    current = None
    current_lines: list[str] = []
    skip = False
    order: list[str] = []
    for line in text.splitlines():
        start = re.match(r"^#\s*region:\s*(\S+)\s*$", line)
        if start:
            current = start.group(1)
            current_lines = []
            skip = False
            continue
        if re.match(r"^#\s*endregion\s*$", line):
            if current is not None and not skip:
                for body_line in current_lines:
                    body_line = INSTALL_LINE.sub(f'sh "{REPO / "install.sh"}"', body_line)
                    out_lines.append(body_line)
                out_lines.append(f"echo '{_SENTINEL.format(current)}'")
                order.append(current)
            current = None
            continue
        if current is not None:
            current_lines.append(line)
            if requires_ibmi([line]):
                skip = True
            continue
        out_lines.append(line)  # outside any region: shebang, set -eu, comments
    return "\n".join(out_lines) + "\n", order


def run_example(example: Path, standin: Path, version: str) -> tuple[dict[str, str], str]:
    script, region_order = instrument(example / "steps.sh")
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        input_dir = example / "input"
        if input_dir.is_dir():
            shutil.copytree(input_dir, work, dirs_exist_ok=True)
        home = work / "_home"
        home.mkdir()
        script_file = work / f".instrumented-{uuid.uuid4().hex}.sh"
        script_file.write_text(script, encoding="utf-8")
        env = dict(os.environ)
        env["HOME"] = str(home)
        env["SLAY400_RELEASES_URL"] = f"file://{standin}"
        env["SLAY400_RELEASES_API"] = f"file://{standin}/api/latest"
        result = subprocess.run(["sh", str(script_file)], cwd=work, env=env, capture_output=True, text=True, timeout=120)
        combined = result.stdout + result.stderr
        parts = _SENTINEL_SPLIT.split(combined)
        # parts alternates: [chunk_0, name_0, chunk_1, name_1, ..., chunk_n, name_n, trailing]
        chunks, names = parts[0::2], parts[1::2]
        if names != region_order:
            raise RuntimeError(f"{example.name}: expected regions {region_order} in output, found {names}"
                                f" (script exit {result.returncode}); full output:\n{combined}")
        return dict(zip(region_order, chunks)), str(work)


def normalize(text: str, version: str, workdir: str) -> str:
    """The documented substitutions: the tool's own version, and the fresh temporary folder each run works in
    (its name is random, so install's "installed in ..." line would otherwise never match between two runs)."""
    return text.replace(workdir, "<workdir>").replace(version, "<version>")


def check(write: bool) -> list[str]:
    problems = []
    version = project_version()
    with tempfile.TemporaryDirectory() as standin_dir:
        standin = Path(standin_dir)
        try:
            build_standin(standin, version)
        except FileNotFoundError as e:
            return [str(e)]

        shown = set()
        for page in _pages.pages():
            for snippet in _snippets.snippets_in(page.read_text(encoding="utf-8")):
                if snippet.source.endswith("steps.sh"):
                    example = Path(snippet.source).parent.name
                    shown.add((example, snippet.region))

        existing_examples = {p.name for p in example_dirs()}
        for example in sorted(existing_examples):
            if not any(ex == example for ex, _ in shown):
                problems.append(f"docs/examples/{example}: no page shows any of its regions")

        for example_path in example_dirs():
            example = example_path.name
            regions = _snippets.regions_in((example_path / "steps.sh").read_text(encoding="utf-8"))
            runnable = [r for r in regions if not requires_ibmi(regions[r])]
            for region in regions:
                if (example, region) not in shown and not requires_ibmi(regions[region]):
                    problems.append(f"docs/examples/{example}#{region}: no page shows this region")
            if not runnable:
                continue
            captured, workdir = run_example(example_path, standin, version)
            expected_dir = example_path / "expected"
            if write:
                expected_dir.mkdir(exist_ok=True)
                for region, text in captured.items():
                    (expected_dir / f"{region}.out").write_text(normalize(text, version, workdir), encoding="utf-8")
                continue
            for region, text in captured.items():
                expected_file = expected_dir / f"{region}.out"
                if not expected_file.is_file():
                    problems.append(f"docs/examples/{example}#{region}: no expected/{region}.out (run with --write)")
                    continue
                actual = normalize(text, version, workdir)
                want = expected_file.read_text(encoding="utf-8")
                if actual != want:
                    problems.append(f"docs/examples/{example}#{region}: output does not match expected/{region}.out\n"
                                     f"  expected: {want!r}\n  actual:   {actual!r}")
    return problems


def main(argv):
    parser = argparse.ArgumentParser(description="Runs every example and checks its output.")
    parser.add_argument("--write", action="store_true", help="capture output into expected/ instead of comparing")
    args = parser.parse_args(argv)
    problems = check(args.write)
    for problem in problems:
        print("FAIL: " + problem)
    if problems:
        print(f"{len(problems)} problem(s)")
        return 1
    print("OK: every example's output matches" if not args.write else "OK: expected/ captured")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

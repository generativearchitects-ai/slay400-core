#!/usr/bin/env python3
# Apache License 2.0. Origin: slay400-core, https://github.com/generativearchitects-ai/slay400-core (decision 151).
"""docs:examples (specs/documentation.md section 5, kickoff 16; tools from a file, kickoff 18): runs every
example's steps.sh, region by region, in a clean temporary folder, with the tools built from this commit, and
compares what each region prints (stdout and stderr merged, as a terminal shows them) with
docs/examples/<example>/expected/<region>.out. Fails on an example no page's snippet marker uses, and on a region
no page shows.

Everything this script knows about a repository's tools -- archive, release file name, install command, local
script, environment variables, whether it is the repository's own tool -- comes from docs/examples/runner.json
(schema: docs/examples/runner.schema.json; both described in docs/examples/README.md). This script itself names
no repository, archive, URL or environment variable of a tool, so another repository can copy it unchanged and
write its own runner.json.

A region whose lines include "# requires: ibmi" is never run (it needs a real IBM i); its recorded output, when
there is one, is committed by hand, not generated here.

One deliberate substitution per tool, documented because it is the one place this runner does not run the literal
page text: a line that is exactly a tool's install command (runner.json) is run as the local script named in its
place instead of fetching it from the network -- so the test is of the tool built from *this* commit, not of
whatever is on the default branch. The page still shows the real command; a reader who pastes it gets the real
download.

Usage: run_examples.py [--write]
--write captures each region's output into expected/<region>.out instead of comparing against it.

Needs Python 3, a POSIX shell (sh) and curl -- all already needed by install.sh itself, which some regions run
unmodified. Needs each tool's archive to already exist (a local path) or its environment variable to already be
set (an archive obtained elsewhere) -- see docs/examples/runner.json and README.md.

Exit code 0: every region's output matches (or was captured). 1: problems, one per line.
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import _pages
import _snippets

REPO = Path(__file__).resolve().parent.parent.parent
EXAMPLES = REPO / "docs" / "examples"
RUNNER_JSON = EXAMPLES / "runner.json"
REQUIRES = re.compile(r"#\s*requires:\s*(\S+)")
_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TOOL_FIELDS = ["name", "archive", "releaseArchiveName", "installCommand", "localScript", "env", "own"]


class RunnerConfigError(Exception):
    """args[0] is a list of problem strings, one per line, meant for the caller to print and exit 1 -- never a
    stack trace, since runner.json is input a repository's maintainers write, not this script's own bug."""


@dataclass(frozen=True)
class Tool:
    name: str
    archive_path: str | None  # contains the literal "{version}"; mutually exclusive with archive_env
    archive_env: str | None
    release_archive_name: str  # contains the literal "{version}"
    install_command: str
    local_script: str
    releases_url_env: str
    releases_api_env: str
    own: bool


def _parse_tool(raw, index: int) -> tuple[Tool | None, list[str]]:
    where = f"{RUNNER_JSON}: tools[{index}]"
    if not isinstance(raw, dict):
        return None, [f"{where} is not an object"]
    problems = []
    unknown = sorted(set(raw) - set(_TOOL_FIELDS))
    if unknown:
        problems.append(f"{where}: unknown field(s) {unknown}")
    missing = [f for f in _TOOL_FIELDS if f not in raw]
    if missing:
        problems.append(f"{where}: missing field(s) {missing}")
        return None, problems  # nothing left that can be checked meaningfully

    name = raw["name"]
    if not isinstance(name, str) or not _NAME.match(name):
        problems.append(f"{where}.name must match {_NAME.pattern}")

    archive = raw["archive"]
    archive_path = archive_env = None
    if not isinstance(archive, dict):
        problems.append(f"{where}.archive must be an object")
    elif set(archive) == {"path"}:
        archive_path = archive["path"]
        if not isinstance(archive_path, str) or "{version}" not in archive_path:
            problems.append(f"{where}.archive.path must be a string containing '{{version}}'")
    elif set(archive) == {"env"}:
        archive_env = archive["env"]
        if not isinstance(archive_env, str) or not _ENV_NAME.match(archive_env):
            problems.append(f"{where}.archive.env must be an environment variable name")
    else:
        problems.append(f"{where}.archive must have exactly one of \"path\" or \"env\"")

    release_archive_name = raw["releaseArchiveName"]
    if not isinstance(release_archive_name, str) or "{version}" not in release_archive_name:
        problems.append(f"{where}.releaseArchiveName must be a string containing '{{version}}'")

    install_command = raw["installCommand"]
    if not isinstance(install_command, str) or not install_command:
        problems.append(f"{where}.installCommand must be a non-empty string")

    local_script = raw["localScript"]
    if not isinstance(local_script, str) or not local_script:
        problems.append(f"{where}.localScript must be a non-empty string")
    else:
        resolved = (REPO / local_script).resolve()
        try:
            resolved.relative_to(REPO)
        except ValueError:
            problems.append(f"{where}.localScript must stay inside the repository")
        else:
            if not resolved.is_file():
                problems.append(f"{where}.localScript names {local_script}, which does not exist")

    env = raw["env"]
    releases_url_env = releases_api_env = None
    if not isinstance(env, dict):
        problems.append(f"{where}.env must be an object")
    else:
        unknown_env = sorted(set(env) - {"releasesUrl", "releasesApi"})
        if unknown_env:
            problems.append(f"{where}.env: unknown field(s) {unknown_env}")
        missing_env = [f for f in ("releasesUrl", "releasesApi") if f not in env]
        if missing_env:
            problems.append(f"{where}.env: missing field(s) {missing_env}")
        releases_url_env = env.get("releasesUrl")
        releases_api_env = env.get("releasesApi")
        for field, value in [("releasesUrl", releases_url_env), ("releasesApi", releases_api_env)]:
            if value is not None and (not isinstance(value, str) or not _ENV_NAME.match(value)):
                problems.append(f"{where}.env.{field} must be an environment variable name")

    own = raw["own"]
    if not isinstance(own, bool):
        problems.append(f"{where}.own must be true or false")

    if problems:
        return None, problems
    return Tool(name=name, archive_path=archive_path, archive_env=archive_env,
                release_archive_name=release_archive_name, install_command=install_command,
                local_script=local_script, releases_url_env=releases_url_env, releases_api_env=releases_api_env,
                own=own), []


def load_tools() -> list[Tool]:
    if not RUNNER_JSON.is_file():
        raise RunnerConfigError([f"{RUNNER_JSON} does not exist"])
    try:
        data = json.loads(RUNNER_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RunnerConfigError([f"{RUNNER_JSON} is not valid JSON: {e}"]) from None
    if not isinstance(data, dict) or not isinstance(data.get("tools"), list) or not data["tools"]:
        raise RunnerConfigError([f"{RUNNER_JSON}: no non-empty top-level \"tools\" array"])

    tools = []
    problems = []
    for i, raw in enumerate(data["tools"]):
        tool, tool_problems = _parse_tool(raw, i)
        problems.extend(tool_problems)
        if tool is not None:
            tools.append(tool)
    if problems:
        raise RunnerConfigError(problems)
    return tools


def project_version() -> str:
    root = ET.parse(REPO / "pom.xml").getroot()
    return root.find("{http://maven.apache.org/POM/4.0.0}version").text


def _version_from_name(filename: str, template: str, tool_name: str) -> str:
    pattern = "^" + "".join(re.escape(part) if part != "{version}" else "(.+)"
                             for part in re.split(r"(\{version\})", template)) + "$"
    m = re.match(pattern, filename)
    if not m:
        raise RunnerConfigError([f"{tool_name}: {filename!r} does not match releaseArchiveName {template!r}"])
    return m.group(1)


def resolve_archive(tool: Tool) -> tuple[Path, str]:
    """The tool's already-built archive and its version, from wherever runner.json says to look."""
    if tool.archive_path is not None:
        version = project_version()
        path = REPO / tool.archive_path.format(version=version)
        if not path.is_file():
            raise RunnerConfigError([f"{tool.name}: {path} was not found; build it first"])
        return path, version
    raw = os.environ.get(tool.archive_env)
    if not raw:
        raise RunnerConfigError([f"{tool.name}: environment variable {tool.archive_env} is not set"])
    path = Path(raw)
    if not path.is_file():
        raise RunnerConfigError([f"{tool.name}: {tool.archive_env} names {path}, which was not found"])
    version = _version_from_name(path.name, tool.release_archive_name, tool.name)
    return path, version


def example_dirs() -> list[Path]:
    return sorted(p for p in EXAMPLES.iterdir() if p.is_dir() and (p / "steps.sh").is_file())


def requires_ibmi(lines: list[str]) -> bool:
    return any(REQUIRES.match(line.strip()) and REQUIRES.match(line.strip()).group(1) == "ibmi" for line in lines)


def build_standin(standin: Path, tool: Tool, archive_path: Path, version: str) -> None:
    """A local stand-in for one tool's releases, serving its already-built archive, via file:// URLs."""
    download = standin / "download" / f"v{version}"
    download.mkdir(parents=True)
    archive = download / tool.release_archive_name.format(version=version)
    shutil.copyfile(archive_path, archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (download / f"{archive.name}.sha256").write_text(f"{digest}  {archive.name}\n")
    api = standin / "api"
    api.mkdir(parents=True)
    (api / "latest").write_text(json.dumps({"tag_name": f"v{version}"}))


_SENTINEL = "==EXAMPLE_REGION_END:{}=="
_SENTINEL_SPLIT = re.compile(r"\n?==EXAMPLE_REGION_END:(\S+)==\n?")


def instrument(steps_sh: Path, tools: list[Tool]) -> tuple[str, list[str]]:
    """The script text to actually run (sentinels inserted, ibmi-only regions removed, each tool's install
    command replaced by its local script) and the region order."""
    text = steps_sh.read_text(encoding="utf-8")
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
                    for tool in tools:
                        if body_line == tool.install_command:
                            body_line = "sh " + shlex.quote(str(REPO / tool.local_script))
                            break
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


def run_example(example: Path, standins: dict[str, Path], tools: list[Tool]) -> tuple[dict[str, str], str]:
    script, region_order = instrument(example / "steps.sh", tools)
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
        for tool in tools:
            standin = standins[tool.name]
            env[tool.releases_url_env] = f"file://{standin}"
            env[tool.releases_api_env] = f"file://{standin}/api/latest"
        result = subprocess.run(["sh", str(script_file)], cwd=work, env=env, capture_output=True, text=True, timeout=120)
        combined = result.stdout + result.stderr
        parts = _SENTINEL_SPLIT.split(combined)
        # parts alternates: [chunk_0, name_0, chunk_1, name_1, ..., chunk_n, name_n, trailing]
        chunks, names = parts[0::2], parts[1::2]
        if names != region_order:
            raise RuntimeError(f"{example.name}: expected regions {region_order} in output, found {names}"
                                f" (script exit {result.returncode}); full output:\n{combined}")
        return dict(zip(region_order, chunks)), str(work)


def normalize(text: str, tool_versions: list[tuple[Tool, str]], workdir: str) -> str:
    """The documented substitutions: the fresh temporary folder each run works in (its name is random, so
    install's "installed in ..." line would otherwise never match between two runs), and each tool's own version --
    the repository's own tool as the literal "<version>", any other tool as "<name version>", so that two
    versions in one output stay apart. Longest version first, so one being a substring of another cannot leave a
    partial replacement."""
    text = text.replace(workdir, "<workdir>")
    for tool, version in sorted(tool_versions, key=lambda tv: -len(tv[1])):
        marker = "<version>" if tool.own else f"<{tool.name} version>"
        text = text.replace(version, marker)
    return text


def check(write: bool) -> list[str]:
    try:
        tools = load_tools()
    except RunnerConfigError as e:
        return list(e.args[0])

    archives: dict[str, tuple[Path, str]] = {}
    problems: list[str] = []
    for tool in tools:
        try:
            archives[tool.name] = resolve_archive(tool)
        except RunnerConfigError as e:
            problems.extend(e.args[0])
    if problems:
        return problems
    tool_versions = [(tool, archives[tool.name][1]) for tool in tools]

    with tempfile.TemporaryDirectory() as root_dir:
        root = Path(root_dir)
        standins = {}
        for tool in tools:
            standin = root / tool.name
            standin.mkdir()
            path, version = archives[tool.name]
            build_standin(standin, tool, path, version)
            standins[tool.name] = standin

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
            captured, workdir = run_example(example_path, standins, tools)
            expected_dir = example_path / "expected"
            if write:
                expected_dir.mkdir(exist_ok=True)
                for region, text in captured.items():
                    (expected_dir / f"{region}.out").write_text(normalize(text, tool_versions, workdir), encoding="utf-8")
                continue
            for region, text in captured.items():
                expected_file = expected_dir / f"{region}.out"
                if not expected_file.is_file():
                    problems.append(f"docs/examples/{example}#{region}: no expected/{region}.out (run with --write)")
                    continue
                actual = normalize(text, tool_versions, workdir)
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

#!/usr/bin/env python3
# Apache License 2.0. Origin: slay400-core, https://github.com/generativearchitects-ai/slay400-core (decision 151).
"""Tests of run_examples.py's pure helpers: load_tools() (valid runner.json and each kind of invalid one),
resolve_archive(), instrument(), requires_ibmi() and normalize(), including a run with two tools at once. The
end-to-end check() -- building a stand-in release, running every example's steps.sh as a real subprocess and
comparing output -- is proven by actually running it against this repository (see the kickoff 18 pull request
description for how), not re-created here with fixtures: it needs a real built archive and a real POSIX shell,
which would make this file an integration test rather than a unit test.

Run with: python3 -m unittest discover -s scripts/docs
"""
import json
import tempfile
import unittest
from pathlib import Path

import run_examples as run

GOOD_TOOL = {
    "name": "slay400",
    "archive": {"path": "pcml-launcher/target/pcml-launcher-{version}.tar.gz"},
    "releaseArchiveName": "slay400-{version}.tar.gz",
    "installCommand": "curl -fsSL https://example.invalid/install.sh | sh",
    "localScript": "install.sh",
    "env": {"releasesUrl": "SLAY400_RELEASES_URL", "releasesApi": "SLAY400_RELEASES_API"},
    "own": True,
}


def make_tool(**overrides):
    defaults = dict(name="slay400", archive_path="pcml-launcher/target/pcml-launcher-{version}.tar.gz",
                     archive_env=None, release_archive_name="slay400-{version}.tar.gz",
                     install_command="curl -fsSL https://example.invalid/install.sh | sh",
                     local_script="install.sh", releases_url_env="SLAY400_RELEASES_URL",
                     releases_api_env="SLAY400_RELEASES_API", own=True)
    defaults.update(overrides)
    return run.Tool(**defaults)


class RequiresIbmiTest(unittest.TestCase):

    def test_a_requires_ibmi_comment_is_detected(self):
        self.assertTrue(run.requires_ibmi(["# requires: ibmi", "CRTBNDRPG ..."]))

    def test_a_requires_comment_for_something_else_is_not_ibmi(self):
        self.assertFalse(run.requires_ibmi(["# requires: curl"]))

    def test_no_requires_comment_at_all(self):
        self.assertFalse(run.requires_ibmi(["echo hello"]))


class InstrumentTest(unittest.TestCase):

    def write_steps(self, tmp, text):
        path = Path(tmp) / "steps.sh"
        path.write_text(text, encoding="utf-8")
        return path

    def test_each_region_gets_a_sentinel_after_it_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            steps = self.write_steps(tmp,
                                      "#!/bin/sh\n# region: a\necho one\n# endregion\n\n# region: b\necho two\n# endregion\n")
            script, order = run.instrument(steps, [])
        self.assertEqual(["a", "b"], order)
        self.assertIn("echo one", script)
        self.assertIn("==EXAMPLE_REGION_END:a==", script)
        self.assertIn("==EXAMPLE_REGION_END:b==", script)
        self.assertLess(script.index("==EXAMPLE_REGION_END:a=="), script.index("echo two"))

    def test_a_requires_ibmi_region_is_dropped_entirely(self):
        with tempfile.TemporaryDirectory() as tmp:
            steps = self.write_steps(tmp,
                                      "#!/bin/sh\n# region: a\n# requires: ibmi\nCRTBNDRPG FOO\n# endregion\n\n"
                                      "# region: b\necho two\n# endregion\n")
            script, order = run.instrument(steps, [])
        self.assertEqual(["b"], order)
        self.assertNotIn("CRTBNDRPG", script)
        self.assertNotIn("==EXAMPLE_REGION_END:a==", script)

    def test_a_tools_install_command_is_run_locally_instead_of_from_the_network(self):
        tool = make_tool()
        with tempfile.TemporaryDirectory() as tmp:
            steps = self.write_steps(tmp, "#!/bin/sh\n# region: install\n" + tool.install_command + "\n# endregion\n")
            script, _ = run.instrument(steps, [tool])
        self.assertNotIn("example.invalid", script)
        self.assertIn("install.sh", script)

    def test_a_line_that_is_not_exactly_an_install_command_is_left_alone(self):
        tool = make_tool()
        with tempfile.TemporaryDirectory() as tmp:
            steps = self.write_steps(tmp, "#!/bin/sh\n# region: a\necho " + tool.install_command + " extra\n# endregion\n")
            script, _ = run.instrument(steps, [tool])
        self.assertIn(tool.install_command, script)  # not an exact line match, so not replaced

    def test_two_tools_in_one_run_each_get_their_own_install_command_replaced(self):
        core = make_tool(name="slay400", install_command="install core", local_script="install.sh")
        gateway = make_tool(name="slay400-gateway", install_command="install gateway", local_script="install.sh",
                             own=False)
        with tempfile.TemporaryDirectory() as tmp:
            steps = self.write_steps(tmp, "#!/bin/sh\n# region: a\ninstall core\ninstall gateway\n# endregion\n")
            script, _ = run.instrument(steps, [core, gateway])
        self.assertNotIn("install core", script)
        self.assertNotIn("install gateway", script)
        self.assertEqual(2, script.count("install.sh"))

    def test_lines_outside_any_region_are_kept_without_a_sentinel(self):
        with tempfile.TemporaryDirectory() as tmp:
            steps = self.write_steps(tmp, "#!/bin/sh\nset -eu\n# region: a\necho one\n# endregion\n")
            script, _ = run.instrument(steps, [])
        self.assertIn("set -eu", script)


class NormalizeTest(unittest.TestCase):

    def test_the_own_tools_version_is_replaced_with_the_plain_marker(self):
        tool = make_tool(own=True)
        text = "slay400 0.1.0-alpha.1"
        self.assertEqual("slay400 <version>", run.normalize(text, [(tool, "0.1.0-alpha.1")], "/nonexistent"))

    def test_a_tool_that_is_not_its_own_gets_a_marker_carrying_its_name(self):
        tool = make_tool(name="slay400-gateway", own=False)
        text = "slay400-gateway 2.0.0 installed"
        self.assertEqual("slay400-gateway <slay400-gateway version> installed",
                          run.normalize(text, [(tool, "2.0.0")], "/nonexistent"))

    def test_the_workdir_is_replaced(self):
        tool = make_tool(own=True)
        text = "installed in /tmp/abc123/_home/.slay400/0.1.0"
        self.assertEqual("installed in <workdir>/_home/.slay400/<version>",
                          run.normalize(text, [(tool, "0.1.0")], "/tmp/abc123"))

    def test_two_tools_in_one_run_each_get_their_own_version_marker(self):
        core = make_tool(name="slay400", own=True)
        gateway = make_tool(name="slay400-gateway", own=False)
        text = "slay400 1.0.0 talking to slay400-gateway 2.0.0"
        actual = run.normalize(text, [(core, "1.0.0"), (gateway, "2.0.0")], "/nonexistent")
        self.assertEqual("slay400 <version> talking to slay400-gateway <slay400-gateway version>", actual)

    def test_a_longer_version_that_contains_a_shorter_one_is_not_left_partially_replaced(self):
        core = make_tool(name="slay400", own=True)
        gateway = make_tool(name="slay400-gateway", own=False)
        text = "slay400 1.0.0 and slay400-gateway 1.0.0-beta"
        actual = run.normalize(text, [(core, "1.0.0"), (gateway, "1.0.0-beta")], "/nonexistent")
        self.assertEqual("slay400 <version> and slay400-gateway <slay400-gateway version>", actual)


class VersionFromNameTest(unittest.TestCase):

    def test_the_version_is_read_back_from_a_matching_file_name(self):
        self.assertEqual("1.2.3", run._version_from_name("slay400-1.2.3.tar.gz", "slay400-{version}.tar.gz", "slay400"))

    def test_a_non_matching_file_name_is_a_runner_config_error(self):
        with self.assertRaises(run.RunnerConfigError):
            run._version_from_name("something-else.tar.gz", "slay400-{version}.tar.gz", "slay400")


class ResolveArchiveTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self._real_repo = run.REPO
        run.REPO = self.repo
        self.addCleanup(self._restore)

    def _restore(self):
        run.REPO = self._real_repo

    def write_pom(self, version):
        (self.repo / "pom.xml").write_text(
            '<project xmlns="http://maven.apache.org/POM/4.0.0"><version>' + version + "</version></project>",
            encoding="utf-8")

    def test_a_path_archive_is_found_from_the_project_version(self):
        self.write_pom("1.0.0")
        target = self.repo / "pcml-launcher" / "target"
        target.mkdir(parents=True)
        (target / "pcml-launcher-1.0.0.tar.gz").write_bytes(b"data")
        tool = make_tool()
        path, version = run.resolve_archive(tool)
        self.assertEqual("1.0.0", version)
        self.assertEqual(target / "pcml-launcher-1.0.0.tar.gz", path)

    def test_a_missing_path_archive_is_a_runner_config_error(self):
        self.write_pom("1.0.0")
        tool = make_tool()
        with self.assertRaises(run.RunnerConfigError):
            run.resolve_archive(tool)

    def test_an_env_archive_is_found_and_its_version_read_from_its_name(self):
        archive = self.repo / "elsewhere" / "slay400-gateway-2.0.0.tar.gz"
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b"data")
        env_name = "SLAY400_GATEWAY_TEST_ARCHIVE"
        import os
        os.environ[env_name] = str(archive)
        self.addCleanup(lambda: os.environ.pop(env_name, None))
        tool = make_tool(name="slay400-gateway", archive_path=None, archive_env=env_name,
                          release_archive_name="slay400-gateway-{version}.tar.gz", own=False)
        path, version = run.resolve_archive(tool)
        self.assertEqual("2.0.0", version)
        self.assertEqual(archive, path)

    def test_an_unset_env_archive_is_a_runner_config_error(self):
        import os
        env_name = "SLAY400_TEST_ARCHIVE_NOT_SET"
        os.environ.pop(env_name, None)
        tool = make_tool(archive_path=None, archive_env=env_name)
        with self.assertRaises(run.RunnerConfigError):
            run.resolve_archive(tool)


class LoadToolsTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        (self.repo / "install.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        self._real_repo = run.REPO
        self._real_runner_json = run.RUNNER_JSON
        run.REPO = self.repo
        self.addCleanup(self._restore)

    def _restore(self):
        run.REPO = self._real_repo
        run.RUNNER_JSON = self._real_runner_json

    def write_runner(self, data):
        run.RUNNER_JSON = self.repo / "runner.json"
        run.RUNNER_JSON.write_text(json.dumps(data), encoding="utf-8")

    def write_runner_text(self, text):
        run.RUNNER_JSON = self.repo / "runner.json"
        run.RUNNER_JSON.write_text(text, encoding="utf-8")

    def test_a_valid_file_with_one_tool_is_read(self):
        self.write_runner({"tools": [GOOD_TOOL]})
        tools = run.load_tools()
        self.assertEqual(1, len(tools))
        self.assertEqual("slay400", tools[0].name)
        self.assertTrue(tools[0].own)

    def test_a_valid_file_with_two_tools_is_read(self):
        second = dict(GOOD_TOOL, name="slay400-gateway", own=False,
                      archive={"env": "SLAY400_GATEWAY_ARCHIVE"},
                      releaseArchiveName="slay400-gateway-{version}.tar.gz")
        self.write_runner({"tools": [GOOD_TOOL, second]})
        tools = run.load_tools()
        self.assertEqual(["slay400", "slay400-gateway"], [t.name for t in tools])
        self.assertFalse(tools[1].own)
        self.assertEqual("SLAY400_GATEWAY_ARCHIVE", tools[1].archive_env)

    def test_a_missing_file_is_a_runner_config_error(self):
        run.RUNNER_JSON = self.repo / "does-not-exist.json"
        with self.assertRaises(run.RunnerConfigError):
            run.load_tools()

    def test_invalid_json_is_a_runner_config_error(self):
        self.write_runner_text("{not json")
        with self.assertRaises(run.RunnerConfigError):
            run.load_tools()

    def test_a_missing_tools_array_is_a_runner_config_error(self):
        self.write_runner({"not-tools": []})
        with self.assertRaises(run.RunnerConfigError):
            run.load_tools()

    def test_an_empty_tools_array_is_a_runner_config_error(self):
        self.write_runner({"tools": []})
        with self.assertRaises(run.RunnerConfigError):
            run.load_tools()

    def test_a_tool_missing_a_field_is_a_runner_config_error(self):
        bad = dict(GOOD_TOOL)
        del bad["own"]
        self.write_runner({"tools": [bad]})
        with self.assertRaises(run.RunnerConfigError) as ctx:
            run.load_tools()
        self.assertTrue(any("own" in p for p in ctx.exception.args[0]))

    def test_a_tool_with_an_unknown_field_is_a_runner_config_error(self):
        bad = dict(GOOD_TOOL, extra="surprise")
        self.write_runner({"tools": [bad]})
        with self.assertRaises(run.RunnerConfigError):
            run.load_tools()

    def test_an_archive_with_both_path_and_env_is_a_runner_config_error(self):
        bad = dict(GOOD_TOOL, archive={"path": "x/{version}.tar.gz", "env": "X"})
        self.write_runner({"tools": [bad]})
        with self.assertRaises(run.RunnerConfigError):
            run.load_tools()

    def test_an_archive_with_neither_path_nor_env_is_a_runner_config_error(self):
        bad = dict(GOOD_TOOL, archive={})
        self.write_runner({"tools": [bad]})
        with self.assertRaises(run.RunnerConfigError):
            run.load_tools()

    def test_an_archive_path_without_a_version_marker_is_a_runner_config_error(self):
        bad = dict(GOOD_TOOL, archive={"path": "pcml-launcher/target/pcml-launcher.tar.gz"})
        self.write_runner({"tools": [bad]})
        with self.assertRaises(run.RunnerConfigError):
            run.load_tools()

    def test_a_release_archive_name_without_a_version_marker_is_a_runner_config_error(self):
        bad = dict(GOOD_TOOL, releaseArchiveName="slay400.tar.gz")
        self.write_runner({"tools": [bad]})
        with self.assertRaises(run.RunnerConfigError):
            run.load_tools()

    def test_a_local_script_outside_the_repository_is_a_runner_config_error(self):
        bad = dict(GOOD_TOOL, localScript="../outside.sh")
        self.write_runner({"tools": [bad]})
        with self.assertRaises(run.RunnerConfigError):
            run.load_tools()

    def test_a_local_script_that_does_not_exist_is_a_runner_config_error(self):
        bad = dict(GOOD_TOOL, localScript="no-such-script.sh")
        self.write_runner({"tools": [bad]})
        with self.assertRaises(run.RunnerConfigError):
            run.load_tools()

    def test_env_missing_a_name_is_a_runner_config_error(self):
        bad = dict(GOOD_TOOL, env={"releasesUrl": "X"})
        self.write_runner({"tools": [bad]})
        with self.assertRaises(run.RunnerConfigError):
            run.load_tools()

    def test_own_that_is_not_a_boolean_is_a_runner_config_error(self):
        bad = dict(GOOD_TOOL, own="true")
        self.write_runner({"tools": [bad]})
        with self.assertRaises(run.RunnerConfigError):
            run.load_tools()

    def test_every_problem_across_two_bad_tools_is_reported_not_only_the_first(self):
        bad1 = dict(GOOD_TOOL)
        del bad1["own"]
        bad2 = dict(GOOD_TOOL, name="x", own="not-a-bool")
        self.write_runner({"tools": [bad1, bad2]})
        with self.assertRaises(run.RunnerConfigError) as ctx:
            run.load_tools()
        self.assertEqual(2, len(ctx.exception.args[0]))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests of check_release_tag.py, on a small real git repository made for each test, and on this repository.
Needs Python 3 and git on PATH; run with: python3 -m unittest discover -s scripts"""
import subprocess
import tempfile
import unittest
from pathlib import Path

import check_release_tag as checker

REPO = Path(__file__).resolve().parent.parent
POM = '<project xmlns="http://maven.apache.org/POM/4.0.0">{body}</project>'


def write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(POM.format(body=body))


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


class ReleaseTagTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "test@example.com")
        git(self.repo, "config", "user.name", "Test")
        self.make("0.1.0-SNAPSHOT")
        self.commit()
        # Real network calls to Maven Central are not part of a unit test; tests that care about that path
        # override central_has_version directly (CentralCheckTest below).
        self._real_central = checker.central_has_version
        checker.central_has_version = lambda *a, **k: False
        self.addCleanup(self._restore_central)

    def _restore_central(self):
        checker.central_has_version = self._real_central

    def make(self, version, module_version=None, bom_version=None):
        write(self.repo / "pom.xml",
              f"<groupId>g</groupId><artifactId>a</artifactId><version>{version}</version>"
              f"<modules><module>pcml-a</module><module>pcml-bom</module></modules>")
        write(self.repo / "pcml-a/pom.xml", f"<parent><version>{module_version or version}</version></parent>")
        write(self.repo / "pcml-bom/pom.xml", f"<version>{bom_version or version}</version>")

    def commit(self, message="x"):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", message)
        return git(self.repo, "rev-parse", "HEAD")

    def check(self, tag, **kwargs):
        kwargs.setdefault("main", "main")
        return checker.check(tag, self.repo, **kwargs)

    # ---- tag shape

    def test_a_tag_of_the_snapshots_line_can_be_released(self):
        self.assertEqual([], self.check("v0.1.0")[0])

    def test_a_prerelease_tag_of_the_snapshots_line_can_be_released(self):
        self.assertEqual([], self.check("v0.1.0-alpha.2")[0])

    def test_a_tag_with_no_v_is_refused(self):
        problems, _ = self.check("0.1.0")
        self.assertTrue(any("is not v<MAJOR.MINOR.PATCH>" in p for p in problems))

    def test_a_tag_with_four_numbers_is_refused(self):
        problems, _ = self.check("v0.1.0.1")
        self.assertTrue(any("is not v<MAJOR.MINOR.PATCH>" in p for p in problems))

    def test_a_tag_with_a_build_part_is_refused(self):
        # MAJOR.MINOR.PATCH-prerelease+build is not accepted: only a pre-release part.
        problems, _ = self.check("v0.1.0+build.5")
        self.assertTrue(any("is not v<MAJOR.MINOR.PATCH>" in p for p in problems))

    def test_a_snapshot_tag_is_refused(self):
        problems, _ = self.check("v0.1.0-SNAPSHOT")
        self.assertTrue(any("is a snapshot" in p for p in problems))

    # ---- the commit must be in main

    def test_the_head_commit_is_accepted(self):
        self.assertEqual([], self.check("v0.1.0", commit="HEAD")[0])

    def test_a_commit_not_on_main_is_refused(self):
        git(self.repo, "checkout", "-q", "-b", "other")
        write(self.repo / "pcml-a/pom.xml", "<parent><version>0.1.0-SNAPSHOT</version></parent><!-- x -->")
        other = self.commit("on another branch")
        problems, _ = self.check("v0.1.0", commit=other)
        self.assertTrue(any("is not an ancestor of main" in p for p in problems))

    def test_a_commit_that_does_not_resolve_is_refused(self):
        problems, _ = self.check("v0.1.0", commit="not-a-real-ref")
        self.assertTrue(any("does not resolve to a commit" in p for p in problems))

    # ---- the line of the snapshot

    def test_a_tag_on_another_line_is_refused_with_a_message_to_move_main(self):
        problems, _ = self.check("v0.2.0")
        self.assertEqual(["the tag v0.2.0 is not on the line of the snapshot 0.1.0-SNAPSHOT: move main to 0.2.0-SNAPSHOT first"],
                          problems)

    def test_the_root_pom_not_being_a_snapshot_is_refused(self):
        self.make("0.1.0")
        self.commit()
        problems, _ = self.check("v0.1.0")
        self.assertTrue(any("main must always carry a snapshot version" in p for p in problems))

    # ---- every module has the snapshot version

    def test_a_module_with_another_version_is_refused(self):
        self.make("0.1.0-SNAPSHOT", module_version="0.0.9-SNAPSHOT")
        self.commit()
        problems, _ = self.check("v0.1.0")
        self.assertTrue(any("pcml-a has the version 0.0.9-SNAPSHOT" in p for p in problems))

    def test_the_bom_with_another_version_is_refused(self):
        self.make("0.1.0-SNAPSHOT", bom_version="0.1.1-SNAPSHOT")
        self.commit()
        problems, _ = self.check("v0.1.0")
        self.assertTrue(any("pcml-bom has the version 0.1.1-SNAPSHOT" in p for p in problems))

    # ---- no tag of this name at a different commit

    def test_no_existing_tag_of_this_name_is_fine(self):
        self.assertEqual([], self.check("v0.1.0")[0])

    def test_a_tag_already_at_the_same_commit_is_fine(self):
        # Made by hand on GitHub's release page before the workflow ran, or checked again after tagging.
        head = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "tag", "v0.1.0", head)
        self.assertEqual([], self.check("v0.1.0", commit=head)[0])

    def test_a_tag_already_at_a_different_commit_is_refused(self):
        first = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "tag", "v0.1.0", first)
        write(self.repo / "pcml-a/pom.xml", "<parent><version>0.1.0-SNAPSHOT</version></parent><!-- y -->")
        second = self.commit("second")
        problems, _ = self.check("v0.1.0", commit=second)
        self.assertTrue(any(f"already exists, at commit {first}" in p for p in problems))

    # ---- every problem is reported, not only the first

    def test_every_problem_is_reported_not_only_the_first(self):
        self.make("0.1.0", module_version="0.0.9", bom_version="0.0.8")
        self.commit()
        problems, _ = self.check("v9")
        # tag shape, not-a-snapshot root, pcml-a mismatch, pcml-bom mismatch: 4
        self.assertEqual(4, len(problems))

    def test_the_command_line_exit_code_follows_the_problems(self):
        self.assertEqual(0, checker.main(["--repo", str(self.repo), "--main", "main", "v0.1.0"]))
        self.assertEqual(1, checker.main(["--repo", str(self.repo), "--main", "main", "v9"]))


class CentralCheckTest(unittest.TestCase):
    """central_has_version() itself: True, False and "could not ask" each produce the right problem or note,
    without a real network call."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "test@example.com")
        git(self.repo, "config", "user.name", "Test")
        write(self.repo / "pom.xml",
              "<groupId>g</groupId><artifactId>a</artifactId><version>0.1.0-SNAPSHOT</version>"
              "<modules><module>pcml-bom</module></modules>")
        write(self.repo / "pcml-bom/pom.xml", "<version>0.1.0-SNAPSHOT</version>")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "x")
        self._real_central = checker.central_has_version
        self.addCleanup(self._restore)

    def _restore(self):
        checker.central_has_version = self._real_central

    def test_a_version_already_on_central_is_refused(self):
        checker.central_has_version = lambda *a, **k: True
        problems, notes = checker.check("v0.1.0", self.repo, main="main")
        self.assertTrue(any("already exists on Maven Central" in p for p in problems))
        self.assertEqual([], notes)

    def test_a_version_not_on_central_has_no_problem(self):
        checker.central_has_version = lambda *a, **k: False
        problems, _ = checker.check("v0.1.0", self.repo, main="main")
        self.assertEqual([], problems)

    def test_central_unreachable_is_a_note_not_a_problem(self):
        checker.central_has_version = lambda *a, **k: None
        problems, notes = checker.check("v0.1.0", self.repo, main="main")
        self.assertEqual([], problems)
        self.assertEqual(1, len(notes))
        self.assertIn("could not reach Maven Central", notes[0])


class RealRepositoryTest(unittest.TestCase):
    """This repository's own main: every module shares the root's snapshot version, and HEAD is (trivially) its
    own ancestor, so the shape/line/module checks can be run against the real thing."""

    def setUp(self):
        self._real_central = checker.central_has_version
        checker.central_has_version = lambda *a, **k: False
        self.addCleanup(self._restore)

    def _restore(self):
        checker.central_has_version = self._real_central

    def test_every_module_of_this_repository_has_the_snapshot_version_of_the_root_pom(self):
        root = checker.ET.parse(REPO / "pom.xml").getroot()
        snapshot = checker._text(root, "version")
        self.assertTrue(snapshot.endswith("-SNAPSHOT"), f"expected main to carry a snapshot version, got {snapshot}")
        line = snapshot[: -len("-SNAPSHOT")]
        problems, _ = checker.check(f"v{line}", REPO, commit="HEAD", main="HEAD")
        self.assertEqual([], [p for p in problems if "has the version" in p or "is not on the line" in p])


if __name__ == "__main__":
    unittest.main()

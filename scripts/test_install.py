#!/usr/bin/env python3
"""Tests of install.sh and install.ps1 against a local stand-in for GitHub Releases: a small HTTP server on
127.0.0.1 serves fixture archives, a fixture "latest release" and, for one test, a response that is cut off
half-way. Neither script ever reaches the real network here (both read SLAY400_RELEASES_URL/SLAY400_RELEASES_API).

install.sh is tested with sh, on every OS but Windows (no POSIX shell there by default). install.ps1 is tested
with pwsh, which every GitHub Actions runner (including ubuntu-latest and macos-latest) has preinstalled; locally,
the ps1 tests are skipped if pwsh is not on PATH.

Needs Python 3 and nothing else (pwsh only for the ps1 tests). Run with: python3 -m unittest discover -s scripts
"""
import hashlib
import http.server
import io
import json
import platform
import shutil
import subprocess
import tarfile
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO / "install.sh"
INSTALL_PS1 = REPO / "install.ps1"


def build_tar_gz(version):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        base = f"slay400-{version}"
        for name, content, mode in [
            (f"{base}/VERSION", f"{version}\n".encode(), 0o644),
            (f"{base}/bin/slay400", f"#!/bin/sh\necho stub-{version}\n".encode(), 0o755),
            (f"{base}/bin/slay400.cmd", b"@echo off\r\necho stub\r\n", 0o644),
            (f"{base}/lib/pcml-cli-{version}.jar", b"not a real jar, just a stand-in", 0o644),
        ]:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = mode
            tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def build_zip(version):
    buffer = io.BytesIO()
    base = f"slay400-{version}"
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(f"{base}/VERSION", f"{version}\n")
        zf.writestr(f"{base}/bin/slay400.cmd", "@echo off\r\necho stub\r\n")
        zf.writestr(f"{base}/lib/pcml-cli-{version}.jar", "not a real jar, just a stand-in")
    return buffer.getvalue()


def sha256_line(data, name):
    return f"{hashlib.sha256(data).hexdigest()}  {name}\n".encode()


class ReleaseStandIn(http.server.ThreadingHTTPServer):
    """files: path -> bytes. latest: the version /api/latest reports, or None for a 404 (no stable release, the
    real GitHub behaviour when every release is a draft or a pre-release). releases: the list /api reports, in the
    order given (GitHub's own list is newest-created-first; a test adds them in that order). error_path: a path
    that answers 500 instead of its normal response, to test that any API failure other than a 404 keeps the
    existing message. truncate: a path whose response is cut short."""

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.files = {}
        self.latest = None
        self.releases = []
        self.error_path = None
        self.truncate = None

    @property
    def releases_url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"

    @property
    def releases_api(self):
        return f"{self.releases_url}/api/latest"

    @property
    def releases_api_list(self):
        return f"{self.releases_url}/api"

    def add_version(self, version, ext, data):
        archive = f"/download/v{version}/slay400-{version}.{ext}"
        self.files[archive] = data
        self.files[archive + ".sha256"] = sha256_line(data, f"slay400-{version}.{ext}")
        return archive

    def add_release(self, tag, draft=False):
        self.releases.append({"tag_name": tag, "draft": draft})


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.server.error_path is not None and self.path == self.server.error_path:
            self.send_response(500)
            self.end_headers()
            return
        if self.path == "/api/latest":
            if self.server.latest is None:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps({"tag_name": f"v{self.server.latest}"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api":
            body = json.dumps(self.server.releases).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        data = self.server.files.get(self.path)
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        if self.path == self.server.truncate:
            half = data[: len(data) // 2]
            self.send_response(200)
            self.send_header("Content-Length", str(len(data) + 4096))  # promises more than it sends
            self.end_headers()
            self.wfile.write(half)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class InstallScriptTestMixin:
    """FLAVOR and EXT are set by the concrete subclasses below."""

    FLAVOR = None
    EXT = None

    @classmethod
    def setUpClass(cls):
        if cls.FLAVOR == "sh" and platform.system() == "Windows":
            raise unittest.SkipTest("install.sh needs a POSIX shell; install.ps1 is its Windows counterpart")
        if cls.FLAVOR == "ps1" and shutil.which("pwsh") is None:
            raise unittest.SkipTest("pwsh is not on PATH (every GitHub Actions runner has it; this machine may not)")

    def setUp(self):
        self.server = ReleaseStandIn()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "install"

    def build(self, version):
        return build_tar_gz(version) if self.EXT == "tar.gz" else build_zip(version)

    def run_install(self, *args):
        env = {
            "SLAY400_RELEASES_URL": self.server.releases_url,
            "SLAY400_RELEASES_API": self.server.releases_api,
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(self.tmp.name),
        }
        if self.FLAVOR == "sh":
            command = ["sh", str(INSTALL_SH), *args]
        else:
            command = [shutil.which("pwsh"), "-NoProfile", "-File", str(INSTALL_PS1), *args]
            env = {**env, "SystemRoot": __import__("os").environ.get("SystemRoot", "")}
        result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=60)
        return result.returncode, result.stdout, result.stderr

    def install_args(self, version=None, folder=None, uninstall=False):
        folder = str(folder if folder is not None else self.folder)
        if self.FLAVOR == "sh":
            if uninstall:
                return ["uninstall", folder]
            return [version or "", folder]
        if uninstall:
            return ["-Uninstall", "-Folder", folder]
        args = ["-Folder", folder]
        if version:
            args = ["-Version", version] + args
        return args

    def launcher_name(self):
        return "slay400" if self.FLAVOR == "sh" else "slay400.cmd"

    # ---- tests, shared by both flavors

    def test_a_clean_install_unpacks_and_points_bin_slay400_at_it(self):
        self.server.add_version("1.0.0", self.EXT, self.build("1.0.0"))
        code, out, err = self.run_install(*self.install_args(version="1.0.0"))
        self.assertEqual(0, code, err)
        self.assertTrue((self.folder / "1.0.0" / "VERSION").is_file())
        self.assertTrue((self.folder / "bin" / self.launcher_name()).exists())
        self.assertIn("1.0.0", out)

    def test_a_second_version_installs_beside_the_first(self):
        self.server.add_version("1.0.0", self.EXT, self.build("1.0.0"))
        self.server.add_version("2.0.0", self.EXT, self.build("2.0.0"))
        self.run_install(*self.install_args(version="1.0.0"))
        code, out, err = self.run_install(*self.install_args(version="2.0.0"))
        self.assertEqual(0, code, err)
        self.assertTrue((self.folder / "1.0.0" / "VERSION").is_file())
        self.assertTrue((self.folder / "2.0.0" / "VERSION").is_file())

    def test_reinstalling_the_same_version_is_idempotent(self):
        self.server.add_version("1.0.0", self.EXT, self.build("1.0.0"))
        first = self.run_install(*self.install_args(version="1.0.0"))
        second = self.run_install(*self.install_args(version="1.0.0"))
        self.assertEqual(0, first[0])
        self.assertEqual(0, second[0], second[2])
        self.assertTrue((self.folder / "1.0.0" / "VERSION").is_file())

    def test_a_wrong_checksum_is_refused_and_leaves_the_previous_install_untouched(self):
        self.server.add_version("1.0.0", self.EXT, self.build("1.0.0"))
        self.run_install(*self.install_args(version="1.0.0"))
        archive = self.server.add_version("2.0.0", self.EXT, self.build("2.0.0"))
        self.server.files[archive + ".sha256"] = sha256_line(b"not the archive", f"slay400-2.0.0.{self.EXT}")
        code, out, err = self.run_install(*self.install_args(version="2.0.0"))
        self.assertNotEqual(0, code)
        self.assertFalse((self.folder / "2.0.0").exists())
        self.assertTrue((self.folder / "1.0.0" / "VERSION").is_file())

    def test_a_download_cut_off_half_way_is_refused_and_leaves_the_previous_install_untouched(self):
        self.server.add_version("1.0.0", self.EXT, self.build("1.0.0"))
        self.run_install(*self.install_args(version="1.0.0"))
        archive = self.server.add_version("2.0.0", self.EXT, self.build("2.0.0"))
        self.server.truncate = archive
        code, out, err = self.run_install(*self.install_args(version="2.0.0"))
        self.assertNotEqual(0, code)
        self.assertFalse((self.folder / "2.0.0").exists())
        self.assertTrue((self.folder / "1.0.0" / "VERSION").is_file())

    def test_the_latest_version_is_used_when_none_is_given(self):
        self.server.add_version("1.0.0", self.EXT, self.build("1.0.0"))
        self.server.latest = "1.0.0"
        code, out, err = self.run_install(*self.install_args())
        self.assertEqual(0, code, err)
        self.assertTrue((self.folder / "1.0.0" / "VERSION").is_file())

    def test_only_a_prerelease_exists_and_is_installed_with_a_notice(self):
        # The defect: GitHub's "latest release" endpoint excludes pre-releases, and 404s when there is no stable
        # release at all. With only a pre-release published, install must still work, from the releases list, and
        # say so.
        self.server.add_version("0.2.0-beta.1", self.EXT, self.build("0.2.0-beta.1"))
        self.server.add_release("v0.2.0-beta.1", draft=False)
        code, out, err = self.run_install(*self.install_args())
        self.assertEqual(0, code, err)
        self.assertTrue((self.folder / "0.2.0-beta.1" / "VERSION").is_file())
        self.assertIn("pre-release", out + err)
        self.assertIn("0.2.0-beta.1", out + err)

    def test_a_stable_release_wins_over_a_newer_prerelease(self):
        # /api/latest already answers with the stable release directly (GitHub's own behaviour); the newer
        # pre-release in the list must not be preferred, and the list must not even need to be reachable.
        self.server.add_version("1.0.0", self.EXT, self.build("1.0.0"))
        self.server.latest = "1.0.0"
        self.server.add_release("v2.0.0-beta.1", draft=False)  # newer, but not stable: must lose
        code, out, err = self.run_install(*self.install_args())
        self.assertEqual(0, code, err)
        self.assertTrue((self.folder / "1.0.0" / "VERSION").is_file())
        self.assertFalse((self.folder / "2.0.0-beta.1").exists())
        self.assertNotIn("pre-release", out + err)

    def test_a_draft_release_is_not_installed_even_as_a_fallback(self):
        # Only a draft exists (no stable release, and the one pre-release is still a draft): nothing to install.
        self.server.add_release("v0.3.0-beta.1", draft=True)
        code, out, err = self.run_install(*self.install_args())
        self.assertNotEqual(0, code)
        self.assertFalse((self.folder / "0.3.0-beta.1").exists())

    def test_no_release_at_all_is_a_clear_failure(self):
        # /api/latest 404s and the list is empty: nothing has ever been released.
        code, out, err = self.run_install(*self.install_args())
        self.assertNotEqual(0, code)
        self.assertFalse((self.folder).exists())

    def test_the_latest_endpoint_failing_with_something_other_than_404_keeps_todays_message(self):
        self.server.error_path = "/api/latest"
        code, out, err = self.run_install(*self.install_args())
        self.assertNotEqual(0, code)
        self.assertIn("could not reach", err)
        self.assertNotIn("pre-release", out + err)

    def test_the_releases_list_failing_after_a_404_keeps_todays_message(self):
        self.server.error_path = "/api"  # /api/latest answers 404 (its default), then the fallback list 500s
        code, out, err = self.run_install(*self.install_args())
        self.assertNotEqual(0, code)
        self.assertIn("could not reach", err)

    def test_uninstall_removes_only_what_it_created(self):
        self.server.add_version("1.0.0", self.EXT, self.build("1.0.0"))
        self.run_install(*self.install_args(version="1.0.0"))
        (self.folder / "not-mine.txt").write_text("leave me alone")
        code, out, err = self.run_install(*self.install_args(uninstall=True))
        self.assertEqual(0, code, err)
        self.assertFalse((self.folder / "1.0.0").exists())
        self.assertFalse((self.folder / "bin" / self.launcher_name()).exists())
        self.assertTrue((self.folder / "not-mine.txt").is_file())

    def test_uninstall_does_not_touch_a_foreign_folder_with_a_version_file(self):
        # Review point 2: "has a file named VERSION" is not enough; a foreign folder must survive, even one that
        # merely looks the part (its own name matches its own VERSION file's content) but lacks the rest of the shape.
        self.server.add_version("1.0.0", self.EXT, self.build("1.0.0"))
        self.run_install(*self.install_args(version="1.0.0"))
        foreign = self.folder / "my-project"
        foreign.mkdir()
        (foreign / "VERSION").write_text("1.2.3")  # an unrelated project's own convention; does not match its folder name
        lookalike = self.folder / "2.0.0"  # name matches its VERSION content, but it is not a real install (no bin/, no lib/)
        lookalike.mkdir()
        (lookalike / "VERSION").write_text("2.0.0")
        code, out, err = self.run_install(*self.install_args(uninstall=True))
        self.assertEqual(0, code, err)
        self.assertTrue((self.folder / "my-project" / "VERSION").is_file())
        self.assertTrue((self.folder / "2.0.0" / "VERSION").is_file())
        self.assertFalse((self.folder / "1.0.0").exists())

    def test_a_version_that_does_not_look_like_a_version_is_refused(self):
        # Review point 4: a version argument (or one read from the releases API) must look like a version before it
        # is used to build a download address or a path -- not a value with "/" or ".." in it.
        self.server.add_version("1.0.0", self.EXT, self.build("1.0.0"))
        self.run_install(*self.install_args(version="1.0.0"))
        code, out, err = self.run_install(*self.install_args(version="../evil"))
        self.assertNotEqual(0, code)
        self.assertIn("does not look like a version", err)
        self.assertFalse((self.folder.parent / "evil").exists())
        self.assertTrue((self.folder / "1.0.0" / "VERSION").is_file())


class InstallShTest(InstallScriptTestMixin, unittest.TestCase):
    FLAVOR = "sh"
    EXT = "tar.gz"


class InstallPs1Test(InstallScriptTestMixin, unittest.TestCase):
    FLAVOR = "ps1"
    EXT = "zip"


if __name__ == "__main__":
    unittest.main()

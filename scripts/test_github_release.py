#!/usr/bin/env python3
"""Tests of github_release.py against a local stand-in for the GitHub API: no release; a draft; a published
pre-release; a release that already has one of the files (kickoff 20, point 4). Neither the real GitHub API nor
the real network is reached: both SLAY400_GITHUB_API and SLAY400_GITHUB_UPLOADS point at the stand-in.

Needs Python 3 and nothing else. Run with: python3 -m unittest discover -s scripts"""
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import github_release as gr

REPO = "generativearchitects-ai/slay400-core"


class GithubStandIn(ThreadingHTTPServer):
    """releases: tag_name -> release dict (id, tag_name, draft, prerelease, assets: [{id, name}]).
    asset_bytes: asset id -> the bytes it was last uploaded with."""

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.releases: dict[str, dict] = {}
        self.asset_bytes: dict[int, bytes] = {}
        self.next_id = 1

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def add_release(self, tag, draft=True, prerelease=False, asset_names=()) -> dict:
        release = {"id": self.next_id, "tag_name": tag, "draft": draft, "prerelease": prerelease, "assets": []}
        self.next_id += 1
        for name in asset_names:
            asset = {"id": self.next_id, "name": name}
            self.next_id += 1
            release["assets"].append(asset)
            self.asset_bytes[asset["id"]] = b"old content"
        self.releases[tag] = release
        return release

    def release_by_asset_id(self, asset_id):
        for release in self.releases.values():
            for asset in release["assets"]:
                if asset["id"] == asset_id:
                    return release
        return None


class _Handler(BaseHTTPRequestHandler):
    def _json(self, status, body):
        data = json.dumps(body).encode() if body is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def do_GET(self):
        prefix = f"/repos/{REPO}/releases/tags/"
        if self.path.startswith(prefix):
            tag = self.path[len(prefix):]
            release = self.server.releases.get(tag)
            self._json(200, release) if release else self._json(404, {"message": "Not Found"})
            return
        self._json(404, {"message": "Not Found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        if self.path == f"/repos/{REPO}/releases":
            payload = json.loads(body)
            tag = payload["tag_name"]
            if tag in self.server.releases:
                self._json(422, {"message": "already_exists"})
                return
            release = {"id": self.server.next_id, "tag_name": tag, "draft": payload.get("draft", True),
                       "prerelease": payload.get("prerelease", False), "assets": []}
            self.server.next_id += 1
            self.server.releases[tag] = release
            self._json(201, release)
            return
        import re
        m = re.fullmatch(rf"/repos/{re.escape(REPO)}/releases/(\d+)/assets", self.path.split("?")[0])
        if m and self.path.split("?name=")[-1] != self.path:
            release_id = int(m.group(1))
            name = self.path.split("?name=", 1)[1]
            release = next((r for r in self.server.releases.values() if r["id"] == release_id), None)
            if release is None:
                self._json(404, {"message": "Not Found"})
                return
            asset = {"id": self.server.next_id, "name": name}
            self.server.next_id += 1
            self.server.asset_bytes[asset["id"]] = body
            release["assets"].append(asset)
            self._json(201, asset)
            return
        self._json(404, {"message": "Not Found"})

    def do_DELETE(self):
        import re
        m = re.fullmatch(rf"/repos/{re.escape(REPO)}/releases/assets/(\d+)", self.path)
        if m:
            asset_id = int(m.group(1))
            release = self.server.release_by_asset_id(asset_id)
            if release is None:
                self._json(404, {"message": "Not Found"})
                return
            release["assets"] = [a for a in release["assets"] if a["id"] != asset_id]
            self.server.asset_bytes.pop(asset_id, None)
            self.send_response(204)
            self.end_headers()
            return
        self._json(404, {"message": "Not Found"})

    def log_message(self, *args):
        pass


class GithubReleaseTest(unittest.TestCase):

    def setUp(self):
        self.server = GithubStandIn()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)
        self._real_api, self._real_uploads = gr.API, gr.UPLOADS
        gr.API = self.server.base_url
        gr.UPLOADS = self.server.base_url
        self.addCleanup(self._restore)
        os.environ["GH_TOKEN"] = "test-token"
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file_a = self._write("slay400-0.1.0.tar.gz", b"new tar.gz content")
        self.file_b = self._write("slay400-0.1.0.zip", b"new zip content")

    def _restore(self):
        gr.API, gr.UPLOADS = self._real_api, self._real_uploads

    def _write(self, name, content):
        path = Path(self.tmp.name) / name
        path.write_bytes(content)
        return path

    def asset_names(self, tag):
        return sorted(a["name"] for a in self.server.releases[tag]["assets"])

    # ---- no release exists

    def test_no_release_creates_a_draft_and_attaches_the_files(self):
        release, created = gr.find_or_create(REPO, "v0.1.0", prerelease=False)
        gr.attach(REPO, release, [self.file_a, self.file_b])
        self.assertTrue(created)
        self.assertTrue(self.server.releases["v0.1.0"]["draft"])
        self.assertFalse(self.server.releases["v0.1.0"]["prerelease"])
        self.assertEqual(["slay400-0.1.0.tar.gz", "slay400-0.1.0.zip"], self.asset_names("v0.1.0"))

    def test_no_release_with_prerelease_creates_a_prerelease(self):
        release, created = gr.find_or_create(REPO, "v0.1.0-alpha.1", prerelease=True)
        self.assertTrue(created)
        self.assertTrue(self.server.releases["v0.1.0-alpha.1"]["prerelease"])

    # ---- a draft already exists (made by hand before the workflow ran)

    def test_an_existing_draft_is_found_not_recreated_and_gets_its_files(self):
        self.server.add_release("v0.1.0", draft=True, prerelease=False)
        release, created = gr.find_or_create(REPO, "v0.1.0", prerelease=False)
        gr.attach(REPO, release, [self.file_a, self.file_b])
        self.assertFalse(created)
        self.assertTrue(self.server.releases["v0.1.0"]["draft"])  # untouched
        self.assertEqual(["slay400-0.1.0.tar.gz", "slay400-0.1.0.zip"], self.asset_names("v0.1.0"))

    def test_prerelease_flag_is_ignored_for_an_existing_release(self):
        self.server.add_release("v0.1.0", draft=True, prerelease=False)
        gr.find_or_create(REPO, "v0.1.0", prerelease=True)  # asking for a pre-release must not flip an existing one
        self.assertFalse(self.server.releases["v0.1.0"]["prerelease"])

    # ---- a published pre-release already exists

    def test_a_published_prerelease_is_found_and_stays_published_and_a_prerelease(self):
        self.server.add_release("v0.1.0-alpha.1", draft=False, prerelease=True)
        release, created = gr.find_or_create(REPO, "v0.1.0-alpha.1", prerelease=False)
        gr.attach(REPO, release, [self.file_a])
        self.assertFalse(created)
        self.assertFalse(self.server.releases["v0.1.0-alpha.1"]["draft"])
        self.assertTrue(self.server.releases["v0.1.0-alpha.1"]["prerelease"])
        self.assertEqual(["slay400-0.1.0.tar.gz"], self.asset_names("v0.1.0-alpha.1"))

    # ---- a release already has one of the files

    def test_an_existing_asset_of_the_same_name_is_replaced_not_duplicated(self):
        self.server.add_release("v0.1.0", asset_names=["slay400-0.1.0.tar.gz"])
        release, _ = gr.find_or_create(REPO, "v0.1.0", prerelease=False)
        gr.attach(REPO, release, [self.file_a, self.file_b])
        self.assertEqual(["slay400-0.1.0.tar.gz", "slay400-0.1.0.zip"], self.asset_names("v0.1.0"))
        new_asset_id = next(a["id"] for a in self.server.releases["v0.1.0"]["assets"] if a["name"] == "slay400-0.1.0.tar.gz")
        self.assertEqual(b"new tar.gz content", self.server.asset_bytes[new_asset_id])

    # ---- the command line

    def test_main_reports_a_missing_file_with_no_stack_trace(self):
        missing = Path(self.tmp.name) / "does-not-exist.tar.gz"
        code = gr.main(["--repo", REPO, "--tag", "v0.1.0", str(missing)])
        self.assertEqual(1, code)

    def test_main_end_to_end(self):
        code = gr.main(["--repo", REPO, "--tag", "v0.1.0", str(self.file_a), str(self.file_b)])
        self.assertEqual(0, code)
        self.assertEqual(["slay400-0.1.0.tar.gz", "slay400-0.1.0.zip"], self.asset_names("v0.1.0"))

    def test_without_gh_token_it_fails_clearly(self):
        del os.environ["GH_TOKEN"]
        os.environ.pop("GITHUB_TOKEN", None)
        code = gr.main(["--repo", REPO, "--tag", "v0.1.0", str(self.file_a)])
        self.assertEqual(1, code)


if __name__ == "__main__":
    unittest.main()

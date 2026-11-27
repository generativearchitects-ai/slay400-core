#!/usr/bin/env python3
"""Finds or creates the GitHub Release for a tag, and attaches files to it, replacing any file of the same name
(kickoff 20, point 4, decision 155): a release made by hand in GitHub's page before the workflow ran gets its
files too, and the workflow never creates a second one. Never changes whether an existing release is a draft,
a pre-release or the latest; only a release this script creates is marked a pre-release, from --prerelease.

Usage: github_release.py --repo OWNER/NAME --tag TAG [--prerelease] FILE [FILE ...]

Needs GH_TOKEN (or GITHUB_TOKEN) in the environment, and Python 3 (urllib) only. Reads SLAY400_GITHUB_API and
SLAY400_GITHUB_UPLOADS only to let tests point at a local stand-in instead of the real GitHub endpoints; leave
both unset for real use.

Exit code 0: the release was found or created, and every file attached. 1: one problem, printed with no stack
trace (never a token).
"""
import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("SLAY400_GITHUB_API", "https://api.github.com")
UPLOADS = os.environ.get("SLAY400_GITHUB_UPLOADS", "https://uploads.github.com")


class ReleaseError(Exception):
    """args[0] is one line meant for a person to read; never a token, never a stack trace."""


def _token() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ReleaseError("GH_TOKEN (or GITHUB_TOKEN) is not set")
    return token


def _request(url: str, method: str = "GET", data: bytes | None = None, headers: dict | None = None):
    all_headers = {"Authorization": f"Bearer {_token()}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28", **(headers or {})}
    request = urllib.request.Request(url, data=data, headers=all_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
            return response.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as error:
        body = error.read()
        return error.code, (json.loads(body) if body else None)


def find_release(repo: str, tag: str) -> dict | None:
    """The release for tag, or None if there is none yet."""
    status, body = _request(f"{API}/repos/{repo}/releases/tags/{tag}")
    if status == 404:
        return None
    if status != 200:
        raise ReleaseError(f"GET releases/tags/{tag} answered {status}: {body}")
    return body


def create_release(repo: str, tag: str, prerelease: bool) -> dict:
    payload = json.dumps({
        "tag_name": tag, "name": tag, "draft": True, "prerelease": prerelease,
        "body": f"Draft release of {tag}. Review the attached archives and the deployment in the Central Portal,"
                " then publish both by hand.",
    }).encode()
    status, body = _request(f"{API}/repos/{repo}/releases", method="POST", data=payload,
                             headers={"Content-Type": "application/json"})
    if status not in (200, 201):
        raise ReleaseError(f"POST releases answered {status}: {body}")
    return body


def delete_asset(repo: str, asset_id: int) -> None:
    status, body = _request(f"{API}/repos/{repo}/releases/assets/{asset_id}", method="DELETE")
    if status != 204:
        raise ReleaseError(f"DELETE releases/assets/{asset_id} answered {status}: {body}")


def upload_asset(repo: str, release_id: int, path: Path) -> dict:
    data = path.read_bytes()
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    status, body = _request(f"{UPLOADS}/repos/{repo}/releases/{release_id}/assets?name={path.name}",
                             method="POST", data=data, headers={"Content-Type": content_type})
    if status not in (200, 201):
        raise ReleaseError(f"POST releases/{release_id}/assets?name={path.name} answered {status}: {body}")
    return body


def attach(repo: str, release: dict, paths: list[Path]) -> None:
    """Uploads every path to release, deleting first any existing asset of the same name -- GitHub refuses to
    upload over one, and this is how a release already holding one of the files gets it replaced, not doubled."""
    existing_by_name = {asset["name"]: asset["id"] for asset in release.get("assets", [])}
    for path in paths:
        if path.name in existing_by_name:
            delete_asset(repo, existing_by_name[path.name])
        upload_asset(repo, release["id"], path)


def find_or_create(repo: str, tag: str, prerelease: bool) -> tuple[dict, bool]:
    """(release, created): created is True only when this call made a new one."""
    release = find_release(repo, tag)
    if release is not None:
        return release, False
    return create_release(repo, tag, prerelease), True


def main(argv):
    parser = argparse.ArgumentParser(description="Finds or creates the GitHub Release for a tag and attaches files to it.")
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--prerelease", action="store_true", help="mark a release this call creates as a pre-release")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)
    for path in args.files:
        if not path.is_file():
            print(f"FAIL: {path} does not exist")
            return 1
    try:
        release, created = find_or_create(args.repo, args.tag, args.prerelease)
        attach(args.repo, release, args.files)
    except ReleaseError as e:
        print(f"FAIL: {e}")
        return 1
    names = ", ".join(p.name for p in args.files)
    print(f"OK: {args.tag} ({'created' if created else 'found'}) now has: {names}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

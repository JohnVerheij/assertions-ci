"""Checks that a release runs on a signed, annotated tag of a commit on the default branch.

Runs before anything is published, through the GitHub REST API:
- refs/tags/v<version> must point to an annotated tag object (a lightweight tag carries no signature);
- GitHub must report the tag's signature as verified;
- the tag must point to the commit the run built (GITHUB_SHA), so it was not moved after the build;
- that commit must be on the default branch.

Environment:
  GITHUB_REPOSITORY  owner/name
  GITHUB_REF         refs/tags/v<version>
  GITHUB_SHA         the commit the run built
  GITHUB_TOKEN       optional, token for the API (read access is enough)
  EXPECTED_VERSION   optional; when set, the tag must be v<EXPECTED_VERSION>
  GITHUB_API_URL     optional, default https://api.github.com
Exit code 1 when a check fails.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

Fetch = Callable[[str], dict]
TAG_PREFIX = "refs/tags/"
ON_DEFAULT_BRANCH = ("identical", "behind")


def api_fetcher(api_url: str, token: str) -> Fetch:
    def fetch(path: str) -> dict:
        request = urllib.request.Request(api_url.rstrip("/") + path)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise ValueError(f"GitHub API {path} returned HTTP {error.code}") from error

    return fetch


def tag_name(ref: str, expected_version: str) -> str:
    if not ref.startswith(TAG_PREFIX):
        raise ValueError(f"A release must run on a tag, got ref {ref!r}")
    tag = ref[len(TAG_PREFIX):]
    if not tag.startswith("v"):
        raise ValueError(f"Release tags start with 'v', got {tag!r}")
    if expected_version and tag != f"v{expected_version}":
        raise ValueError(f"Tag {tag} does not match the built version {expected_version}")
    return tag


def check(repo: str, ref: str, sha: str, expected_version: str, fetch: Fetch) -> list[str]:
    tag = tag_name(ref, expected_version)
    quoted = urllib.parse.quote(tag, safe="")
    target = fetch(f"/repos/{repo}/git/ref/tags/{quoted}")["object"]
    if target["type"] != "tag":
        raise ValueError(f"{tag} is a lightweight tag; release tags must be annotated and signed (git tag -s)")

    tag_object = fetch(f"/repos/{repo}/git/tags/{target['sha']}")
    verification = tag_object.get("verification") or {}
    if not verification.get("verified"):
        raise ValueError(f"GitHub does not verify the signature of {tag} (reason: {verification.get('reason')})")
    if tag_object["object"]["type"] != "commit":
        raise ValueError(f"{tag} points to a {tag_object['object']['type']}, not to a commit")
    commit = tag_object["object"]["sha"]
    if sha not in (commit, target["sha"]):
        raise ValueError(f"{tag} now points to {commit}, but this run built {sha}")

    default_branch = fetch(f"/repos/{repo}")["default_branch"]
    status = fetch(f"/repos/{repo}/compare/{urllib.parse.quote(default_branch, safe='')}...{commit}")["status"]
    if status not in ON_DEFAULT_BRANCH:
        raise ValueError(f"{tag} points to {commit}, which is not on {default_branch} (compare status: {status})")

    tagger = tag_object.get("tagger") or {}
    return [
        f"{tag}: annotated tag, signature verified ({verification.get('reason')})",
        f"tagger: {tagger.get('name')} at {tagger.get('date')}",
        f"commit {commit} is on {default_branch}",
    ]


def main(fetch: Fetch | None = None) -> int:
    try:
        repo = os.environ["GITHUB_REPOSITORY"]
        ref = os.environ["GITHUB_REF"]
        sha = os.environ["GITHUB_SHA"]
        if fetch is None:
            fetch = api_fetcher(os.environ.get("GITHUB_API_URL", "https://api.github.com"),
                                os.environ.get("GITHUB_TOKEN", ""))
        lines = check(repo, ref, sha, os.environ.get("EXPECTED_VERSION", ""), fetch)
    except (KeyError, OSError, ValueError) as error:
        print(f"::error::{error}")
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Unit tests for verify_tag.py. Run with: python -m unittest discover -s scripts -v"""

from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

import verify_tag as verify

REPO = "owner/LogAssertions.TUnit"
TAG_SHA = "a" * 40
COMMIT = "c" * 40


def api(*, ref_type="tag", verified=True, reason="valid", object_type="commit", commit=COMMIT,
        default_branch="main", status="behind") -> dict:
    return {
        f"/repos/{REPO}/git/ref/tags/v0.13.0": {"object": {"type": ref_type, "sha": TAG_SHA}},
        f"/repos/{REPO}/git/tags/{TAG_SHA}": {
            "verification": {"verified": verified, "reason": reason},
            "object": {"type": object_type, "sha": commit},
            "tagger": {"name": "Maintainer", "date": "2026-11-02T10:00:00Z"},
        },
        f"/repos/{REPO}": {"default_branch": default_branch},
        f"/repos/{REPO}/compare/{default_branch}...{commit}": {"status": status},
    }


def fetcher(responses: dict):
    def fetch(path: str) -> dict:
        if path not in responses:
            raise ValueError(f"GitHub API {path} returned HTTP 404")
        return responses[path]

    return fetch


def run_check(responses: dict, *, ref="refs/tags/v0.13.0", sha=COMMIT, expected="0.13.0") -> list[str]:
    return verify.check(REPO, ref, sha, expected, fetcher(responses))


class TagNameTests(unittest.TestCase):
    def test_returns_the_tag(self):
        self.assertEqual(verify.tag_name("refs/tags/v1.2.3", "1.2.3"), "v1.2.3")

    def test_expected_version_is_optional(self):
        self.assertEqual(verify.tag_name("refs/tags/v1.2.3-rc.1", ""), "v1.2.3-rc.1")

    def test_branch_ref_fails(self):
        with self.assertRaisesRegex(ValueError, "must run on a tag"):
            verify.tag_name("refs/heads/main", "")

    def test_tag_without_v_fails(self):
        with self.assertRaisesRegex(ValueError, "start with 'v'"):
            verify.tag_name("refs/tags/1.2.3", "")

    def test_tag_that_differs_from_the_built_version_fails(self):
        with self.assertRaisesRegex(ValueError, "does not match the built version 1.2.4"):
            verify.tag_name("refs/tags/v1.2.3", "1.2.4")


class CheckTests(unittest.TestCase):
    def test_signed_annotated_tag_on_main_passes(self):
        lines = run_check(api())
        self.assertIn("signature verified (valid)", lines[0])
        self.assertIn("is on main", lines[2])

    def test_commit_identical_to_the_default_branch_passes(self):
        run_check(api(status="identical"))

    def test_run_sha_equal_to_the_tag_object_is_accepted(self):
        run_check(api(), sha=TAG_SHA)

    def test_lightweight_tag_fails(self):
        with self.assertRaisesRegex(ValueError, "lightweight tag"):
            run_check(api(ref_type="commit"))

    def test_unverified_signature_fails_with_the_reason(self):
        with self.assertRaisesRegex(ValueError, "reason: unsigned"):
            run_check(api(verified=False, reason="unsigned"))

    def test_missing_verification_fails(self):
        responses = api()
        del responses[f"/repos/{REPO}/git/tags/{TAG_SHA}"]["verification"]
        with self.assertRaisesRegex(ValueError, "does not verify"):
            run_check(responses)

    def test_tag_of_a_tag_fails(self):
        with self.assertRaisesRegex(ValueError, "points to a tag, not to a commit"):
            run_check(api(object_type="tag"))

    def test_moved_tag_fails(self):
        with self.assertRaisesRegex(ValueError, "but this run built"):
            run_check(api(), sha="d" * 40)

    def test_commit_ahead_of_the_default_branch_fails(self):
        with self.assertRaisesRegex(ValueError, "not on main .*ahead"):
            run_check(api(status="ahead"))

    def test_diverged_commit_fails(self):
        with self.assertRaisesRegex(ValueError, "diverged"):
            run_check(api(status="diverged"))

    def test_other_default_branch_name_is_used(self):
        lines = run_check(api(default_branch="trunk"))
        self.assertIn("is on trunk", lines[2])

    def test_missing_tag_fails(self):
        with self.assertRaisesRegex(ValueError, "HTTP 404"):
            run_check({})


class MainTests(unittest.TestCase):
    ENV = {"GITHUB_REPOSITORY": REPO, "GITHUB_REF": "refs/tags/v0.13.0", "GITHUB_SHA": COMMIT,
           "EXPECTED_VERSION": "0.13.0"}

    def run_main(self, responses: dict, **env: str) -> tuple[int, str]:
        stdout = io.StringIO()
        with mock.patch.dict(os.environ, {**self.ENV, **env}, clear=True), redirect_stdout(stdout):
            code = verify.main(fetcher(responses))
        return code, stdout.getvalue()

    def test_passing_check_prints_the_details(self):
        code, stdout = self.run_main(api())
        self.assertEqual(code, 0)
        self.assertIn("tagger: Maintainer", stdout)

    def test_failing_check_returns_1_with_an_error_annotation(self):
        code, stdout = self.run_main(api(verified=False, reason="unsigned"))
        self.assertEqual(code, 1)
        self.assertTrue(stdout.startswith("::error::"))

    def test_missing_environment_returns_1(self):
        stdout = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), redirect_stdout(stdout):
            self.assertEqual(verify.main(fetcher(api())), 1)
        self.assertIn("GITHUB_REPOSITORY", stdout.getvalue())


class ApiFetcherTests(unittest.TestCase):
    def test_sends_the_token_and_parses_json(self):
        response = mock.MagicMock()
        response.__enter__.return_value = io.BytesIO(b'{"default_branch": "main"}')
        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            result = verify.api_fetcher("https://api.example.test/", "secret")(f"/repos/{REPO}")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, f"https://api.example.test/repos/{REPO}")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(result, {"default_branch": "main"})

    def test_no_token_sends_no_authorization(self):
        response = mock.MagicMock()
        response.__enter__.return_value = io.BytesIO(b"{}")
        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            verify.api_fetcher("https://api.example.test", "")("/x")
        self.assertIsNone(urlopen.call_args.args[0].get_header("Authorization"))

    def test_http_error_becomes_value_error(self):
        error = verify.urllib.error.HTTPError("https://api.example.test/x", 404, "Not Found", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(ValueError, "HTTP 404"):
                verify.api_fetcher("https://api.example.test", "")("/x")


if __name__ == "__main__":
    unittest.main()

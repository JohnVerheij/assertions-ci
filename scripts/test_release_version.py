"""Unit tests for release_version.py. Run with: python -m unittest discover -s scripts -v"""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import release_version as gate


def write_project(root: str, project: str, version_xml: str) -> None:
    folder = os.path.join(root, "src", project)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"{project}.csproj"), "w", encoding="utf-8") as handle:
        handle.write(f'<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>{version_xml}</PropertyGroup></Project>')


class RepoTestCase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.root = self._dir.name

    def tearDown(self):
        self._dir.cleanup()

    def projects(self, core: str | None, adapter: str) -> None:
        if core is not None:
            write_project(self.root, "LogAssertions", f"<Version>{core}</Version>")
        write_project(self.root, "LogAssertions.TUnit", f"<Version>{adapter}</Version>")


class ParseFlagTests(unittest.TestCase):
    def test_accepts_true_and_false(self):
        self.assertTrue(gate.parse_flag("X", "true"))
        self.assertFalse(gate.parse_flag("X", "false"))

    def test_rejects_anything_else(self):
        for value in ("True", "1", "", "yes"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                gate.parse_flag("X", value)


class ReadVersionTests(RepoTestCase):
    def test_reads_the_single_version(self):
        write_project(self.root, "A", "<Version> 1.2.3 </Version><PackageId>A</PackageId>")
        self.assertEqual(gate.read_version(os.path.join(self.root, "src", "A", "A.csproj")), "1.2.3")

    def test_missing_version_fails(self):
        write_project(self.root, "A", "<PackageId>A</PackageId>")
        with self.assertRaisesRegex(ValueError, "found 0"):
            gate.read_version(os.path.join(self.root, "src", "A", "A.csproj"))

    def test_two_versions_fail(self):
        write_project(self.root, "A", "<Version>1.0.0</Version><Version>2.0.0</Version>")
        with self.assertRaisesRegex(ValueError, "found 2"):
            gate.read_version(os.path.join(self.root, "src", "A", "A.csproj"))


class TagVersionTests(unittest.TestCase):
    def test_strips_the_tag_prefix(self):
        self.assertEqual(gate.tag_version("refs/tags/v0.12.0"), "0.12.0")

    def test_branch_ref_fails(self):
        with self.assertRaisesRegex(ValueError, "tag"):
            gate.tag_version("refs/heads/main")

    def test_tag_without_v_fails(self):
        with self.assertRaises(ValueError):
            gate.tag_version("refs/tags/0.12.0")


class ResolveTests(RepoTestCase):
    def test_release_with_core_returns_the_tag_version(self):
        self.projects("0.13.0", "0.13.0")
        self.assertEqual(gate.resolve("LogAssertions", True, False, "refs/tags/v0.13.0", self.root), "0.13.0")

    def test_prerelease_tag_is_accepted(self):
        self.projects("1.0.0-beta.1", "1.0.0-beta.1")
        self.assertEqual(gate.resolve("LogAssertions", True, False, "refs/tags/v1.0.0-beta.1", self.root), "1.0.0-beta.1")

    def test_tag_that_differs_from_both_projects_fails(self):
        self.projects("0.13.0", "0.13.0")
        with self.assertRaisesRegex(ValueError, "expected 0.13.1"):
            gate.resolve("LogAssertions", True, False, "refs/tags/v0.13.1", self.root)

    def test_core_that_differs_from_the_tag_fails(self):
        self.projects("0.12.0", "0.13.0")
        with self.assertRaisesRegex(ValueError, r"LogAssertions\.csproj declares 0\.12\.0"):
            gate.resolve("LogAssertions", True, False, "refs/tags/v0.13.0", self.root)

    def test_without_core_only_the_adapter_is_read(self):
        self.projects(None, "0.6.2")
        self.assertEqual(gate.resolve("LogAssertions", False, False, "refs/tags/v0.6.2", self.root), "0.6.2")

    def test_missing_core_project_fails_when_has_core(self):
        self.projects(None, "0.6.2")
        with self.assertRaises(OSError):
            gate.resolve("LogAssertions", True, False, "refs/tags/v0.6.2", self.root)

    def test_dry_run_uses_the_declared_version_and_ignores_the_ref(self):
        self.projects("0.13.0", "0.13.0")
        self.assertEqual(gate.resolve("LogAssertions", True, True, "refs/heads/main", self.root), "0.13.0")

    def test_dry_run_still_requires_core_and_adapter_to_agree(self):
        self.projects("0.12.0", "0.13.0")
        with self.assertRaisesRegex(ValueError, "mismatch"):
            gate.resolve("LogAssertions", True, True, "refs/heads/main", self.root)

    def test_version_that_is_not_semantic_fails(self):
        self.projects("1.0", "1.0")
        with self.assertRaisesRegex(ValueError, "semantic"):
            gate.resolve("LogAssertions", True, False, "refs/tags/v1.0", self.root)


class MainTests(RepoTestCase):
    def run_main(self, **env: str) -> tuple[int, str, str]:
        output = os.path.join(self.root, "github_output")
        values = {"PACKAGE": "LogAssertions", "GITHUB_OUTPUT": output, **env}
        stdout = io.StringIO()
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with mock.patch.dict(os.environ, values, clear=True), redirect_stdout(stdout):
                code = gate.main()
        finally:
            os.chdir(cwd)
        written = ""
        if os.path.exists(output):
            with open(output, encoding="utf-8") as handle:
                written = handle.read()
        return code, stdout.getvalue(), written

    def test_release_writes_version_and_prerelease_outputs(self):
        self.projects("0.13.0", "0.13.0")
        code, _, written = self.run_main(GITHUB_REF="refs/tags/v0.13.0")
        self.assertEqual(code, 0)
        self.assertEqual(written, "version=0.13.0\nprerelease=false\n")

    def test_prerelease_version_sets_prerelease_true(self):
        self.projects("1.0.0-rc.1", "1.0.0-rc.1")
        code, _, written = self.run_main(GITHUB_REF="refs/tags/v1.0.0-rc.1")
        self.assertEqual(code, 0)
        self.assertIn("prerelease=true", written)

    def test_mismatch_returns_1_with_an_error_annotation_and_no_outputs(self):
        self.projects("0.12.0", "0.13.0")
        code, stdout, written = self.run_main(GITHUB_REF="refs/tags/v0.13.0")
        self.assertEqual(code, 1)
        self.assertTrue(stdout.startswith("::error::"))
        self.assertEqual(written, "")

    def test_invalid_flag_returns_1(self):
        self.projects("0.13.0", "0.13.0")
        code, stdout, _ = self.run_main(GITHUB_REF="refs/tags/v0.13.0", DRY_RUN="yes")
        self.assertEqual(code, 1)
        self.assertIn("DRY_RUN", stdout)

    def test_missing_package_returns_1(self):
        with mock.patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(gate.main(), 1)
        self.assertIn("PACKAGE", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()

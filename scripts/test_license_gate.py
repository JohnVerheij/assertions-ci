"""Unit tests for license_gate.py. Run with: python -m unittest discover -s scripts -v"""

from __future__ import annotations

import io
import json
import os
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import license_gate as gate


def nuspec(license_xml: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">'
        f"<metadata><id>X</id><version>1.0.0</version>{license_xml}</metadata></package>"
    )


class ParseAllowlistTests(unittest.TestCase):
    def test_empty_text_gives_empty_allowlist(self):
        self.assertEqual(gate.parse_allowlist(""), {})

    def test_entries_are_case_insensitive_and_skip_comments_and_blank_lines(self):
        allow = gate.parse_allowlist("# reviewed\n\nGrpc.Core.Api = Apache-2.0\n")
        self.assertEqual(allow, {"grpc.core.api": "Apache-2.0"})

    def test_entry_without_separator_is_rejected(self):
        with self.assertRaises(ValueError):
            gate.parse_allowlist("Grpc.Core.Api")

    def test_entry_without_license_is_rejected(self):
        with self.assertRaises(ValueError):
            gate.parse_allowlist("Grpc.Core.Api=")


class ExpressionAcceptedTests(unittest.TestCase):
    def test_mit_is_accepted(self):
        self.assertTrue(gate.expression_accepted("MIT", None))

    def test_apache_is_rejected_without_allowlist(self):
        self.assertFalse(gate.expression_accepted("Apache-2.0", None))

    def test_apache_is_accepted_when_allowlisted(self):
        self.assertTrue(gate.expression_accepted("Apache-2.0", "Apache-2.0"))

    def test_or_expression_with_mit_alternative_is_accepted(self):
        self.assertTrue(gate.expression_accepted("Apache-2.0 OR MIT", None))

    def test_and_expression_needs_every_part(self):
        self.assertFalse(gate.expression_accepted("MIT AND Apache-2.0", None))
        self.assertTrue(gate.expression_accepted("MIT AND Apache-2.0", "Apache-2.0"))

    def test_parenthesized_expression_is_handled(self):
        self.assertTrue(gate.expression_accepted("(MIT OR GPL-3.0-only)", None))


class ReadLicenseTests(unittest.TestCase):
    def read(self, license_xml: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.nuspec")
            with open(path, "w", encoding="utf-8") as f:
                f.write(nuspec(license_xml))
            return gate.read_license(path)

    def test_expression(self):
        self.assertEqual(self.read('<license type="expression">MIT</license>'), ("expression", "MIT"))

    def test_file(self):
        self.assertEqual(self.read('<license type="file">OsmfEula.txt</license>'), ("file", "OsmfEula.txt"))

    def test_url_only(self):
        self.assertEqual(self.read("<licenseUrl>https://example.org/license</licenseUrl>"),
                         ("url", "https://example.org/license"))

    def test_no_license(self):
        self.assertEqual(self.read(""), ("none", ""))


def assets_document() -> dict:
    """A minimal project.assets.json: one shipped dependency with a transitive child, one analyzer."""
    return {
        "version": 4,
        "project": {"frameworks": {"net10.0": {"dependencies": {
            "Shipped.Lib": {"target": "Package", "version": "[1.0.0, )"},
            "Some.Analyzer": {"target": "Package", "version": "[2.0.0, )", "suppressParent": "All"},
        }}}},
        "targets": {"net10.0": {
            "Shipped.Lib/1.0.0": {"type": "package", "dependencies": {"Transitive.Lib": "1.2.0"}},
            "Transitive.Lib/1.2.0": {"type": "package"},
            "Some.Analyzer/2.0.0": {"type": "package", "dependencies": {"Analyzer.Only": "3.0.0"}},
            "Analyzer.Only/3.0.0": {"type": "package"},
            "My.Core/1.0.0": {"type": "project"},
        }},
        "libraries": {
            "Shipped.Lib/1.0.0": {"path": "shipped.lib/1.0.0"},
            "Transitive.Lib/1.2.0": {"path": "transitive.lib/1.2.0"},
            "Some.Analyzer/2.0.0": {"path": "some.analyzer/2.0.0"},
            "Analyzer.Only/3.0.0": {"path": "analyzer.only/3.0.0"},
        },
    }


class ShippedPackagesTests(unittest.TestCase):
    def test_follows_shipped_dependencies_and_skips_private_assets(self):
        self.assertEqual(gate.shipped_packages(assets_document()),
                         {"Shipped.Lib/1.0.0", "Transitive.Lib/1.2.0"})


class MainTests(unittest.TestCase):
    def run_gate(self, transitive_license: str, allowlist: str = "") -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            packages = os.path.join(tmp, "packages")
            for name, version, lic in (("shipped.lib", "1.0.0", '<license type="expression">MIT</license>'),
                                       ("transitive.lib", "1.2.0", transitive_license)):
                folder = os.path.join(packages, name, version)
                os.makedirs(folder)
                with open(os.path.join(folder, name + ".nuspec"), "w", encoding="utf-8") as f:
                    f.write(nuspec(lic))
            document = assets_document()
            document["packageFolders"] = {packages: {}}
            obj = os.path.join(tmp, "repo", "src", "My.Package", "obj")
            os.makedirs(obj)
            with open(os.path.join(obj, "project.assets.json"), "w", encoding="utf-8") as f:
                json.dump(document, f)
            cwd = os.getcwd()
            out = io.StringIO()
            try:
                os.chdir(os.path.join(tmp, "repo"))
                env = {"LICENSE_ALLOWLIST": allowlist}
                with mock.patch.dict(os.environ, env, clear=False), redirect_stdout(out):
                    os.environ.pop("GITHUB_STEP_SUMMARY", None)
                    code = gate.main()
            finally:
                os.chdir(cwd)
            return code, out.getvalue()

    def test_all_mit_passes(self):
        code, out = self.run_gate('<license type="expression">MIT</license>')
        self.assertEqual(code, 0, out)
        self.assertIn("Checked 2 shipped package(s); 0 not accepted.", out)

    def test_apache_fails_without_allowlist(self):
        code, out = self.run_gate('<license type="expression">Apache-2.0</license>')
        self.assertEqual(code, 1)
        self.assertIn("::error::Transitive.Lib 1.2.0 has license 'Apache-2.0'", out)

    def test_apache_passes_with_allowlist(self):
        code, out = self.run_gate('<license type="expression">Apache-2.0</license>', "Transitive.Lib=Apache-2.0")
        self.assertEqual(code, 0, out)

    def test_license_file_fails_unless_allowlisted_as_file(self):
        code, _ = self.run_gate('<license type="file">OsmfEula.txt</license>')
        self.assertEqual(code, 1)
        code, out = self.run_gate('<license type="file">OsmfEula.txt</license>', "Transitive.Lib=file")
        self.assertEqual(code, 0, out)

    def test_missing_restore_output_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            out = io.StringIO()
            try:
                os.chdir(tmp)
                with redirect_stdout(out):
                    code = gate.main()
            finally:
                os.chdir(cwd)
        self.assertEqual(code, 1)
        self.assertIn("No src/*/obj/project.assets.json found", out.getvalue())


class RepoMainTests(unittest.TestCase):
    """Runs main() against a throwaway repository with several projects and package folders."""

    def build_repo(self, projects: dict[str, dict], licenses: dict[str, str], folders: int = 1) -> str:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        package_folders = [os.path.join(tmp.name, f"packages{index}") for index in range(folders)]
        for name, lic in licenses.items():
            folder = os.path.join(package_folders[-1], name.lower(), "1.0.0")
            os.makedirs(folder)
            with open(os.path.join(folder, name.lower() + ".nuspec"), "w", encoding="utf-8") as f:
                f.write(nuspec(lic))
        repo = os.path.join(tmp.name, "repo")
        for project, document in projects.items():
            document["packageFolders"] = {folder: {} for folder in package_folders}
            obj = os.path.join(repo, "src", project, "obj")
            os.makedirs(obj)
            with open(os.path.join(obj, "project.assets.json"), "w", encoding="utf-8") as f:
                json.dump(document, f)
        return repo

    def run_gate(self, repo: str, **env: str) -> tuple[int, str]:
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(repo)
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"LICENSE_ALLOWLIST": "", **env}, clear=False), redirect_stdout(out):
            if "GITHUB_STEP_SUMMARY" not in env:
                os.environ.pop("GITHUB_STEP_SUMMARY", None)
            code = gate.main()
        return code, out.getvalue()

    @staticmethod
    def single_package_assets(name: str = "Only.Lib") -> dict:
        return {
            "project": {"frameworks": {"net10.0": {"dependencies": {name: {"target": "Package"}}}}},
            "targets": {"net10.0": {f"{name}/1.0.0": {"type": "package"}}},
            "libraries": {f"{name}/1.0.0": {"path": f"{name.lower()}/1.0.0"}},
        }

    def test_package_seen_in_two_projects_is_checked_once(self):
        repo = self.build_repo({"First": self.single_package_assets(), "Second": self.single_package_assets()},
                               {"Only.Lib": '<license type="expression">MIT</license>'})
        code, out = self.run_gate(repo)
        self.assertEqual(code, 0, out)
        self.assertIn("Checked 1 shipped package(s); 0 not accepted.", out)

    def test_dependency_missing_from_the_targets_is_skipped(self):
        document = self.single_package_assets()
        document["project"]["frameworks"]["net10.0"]["dependencies"]["Ghost.Lib"] = {"target": "Package"}
        repo = self.build_repo({"First": document}, {"Only.Lib": '<license type="expression">MIT</license>'})
        code, out = self.run_gate(repo)
        self.assertEqual(code, 0, out)
        self.assertIn("Checked 1 shipped package(s); 0 not accepted.", out)
        self.assertNotIn("Ghost.Lib", out)

    def test_package_without_a_nuspec_in_any_folder_fails(self):
        repo = self.build_repo({"First": self.single_package_assets()}, {}, folders=2)
        code, out = self.run_gate(repo)
        self.assertEqual(code, 1)
        self.assertIn("FAIL  Only.Lib  1.0.0         nuspec not found", out)
        self.assertIn("Checked 1 shipped package(s); 1 not accepted.", out)

    def test_nuspec_is_found_in_a_later_package_folder(self):
        repo = self.build_repo({"First": self.single_package_assets()},
                               {"Only.Lib": '<license type="expression">MIT</license>'}, folders=2)
        code, out = self.run_gate(repo)
        self.assertEqual(code, 0, out)
        self.assertIn("ok    Only.Lib  1.0.0         MIT", out)

    def test_license_url_only_fails_and_shows_the_url(self):
        repo = self.build_repo({"First": self.single_package_assets()},
                               {"Only.Lib": "<licenseUrl>https://example.org/license</licenseUrl>"})
        code, out = self.run_gate(repo)
        self.assertEqual(code, 1)
        self.assertIn("::error::Only.Lib 1.0.0 has license 'url: https://example.org/license'", out)

    def test_package_without_any_license_fails_and_shows_none(self):
        repo = self.build_repo({"First": self.single_package_assets()}, {"Only.Lib": ""})
        code, out = self.run_gate(repo)
        self.assertEqual(code, 1)
        self.assertIn("::error::Only.Lib 1.0.0 has license 'none'", out)

    def test_step_summary_receives_a_table_of_every_package(self):
        repo = self.build_repo({"First": self.single_package_assets()},
                               {"Only.Lib": '<license type="expression">Apache-2.0</license>'})
        summary = os.path.join(os.path.dirname(repo), "summary.md")
        code, _ = self.run_gate(repo, GITHUB_STEP_SUMMARY=summary)
        self.assertEqual(code, 1)
        with open(summary, encoding="utf-8") as f:
            self.assertEqual(
                f.read(),
                "### License gate\n\n| Package | Version | License | Verdict |\n|---|---|---|---|\n"
                "| Only.Lib | 1.0.0 | Apache-2.0 | FAIL |\n\n1 shipped package(s) checked; 1 not accepted.\n")

    def test_runs_as_a_program(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            self.addCleanup(os.chdir, cwd)
            os.chdir(tmp)
            with mock.patch.object(sys, "argv", ["license_gate.py"]), \
                    redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit) as raised:
                runpy.run_path(gate.__file__, run_name="__main__")
            os.chdir(cwd)
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("No src/*/obj/project.assets.json found", out.getvalue())


if __name__ == "__main__":
    unittest.main()

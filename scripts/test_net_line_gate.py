"""Tests for net_line_gate.py."""

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

import net_line_gate as gate

DOTNET = "https://github.com/dotnet/dotnet"


def nuspec(repository: str | None) -> str:
    element = f'<repository type="git" url="{repository}" />' if repository is not None else ""
    return ('<?xml version="1.0"?><package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">'
            f"<metadata><id>x</id>{element}</metadata></package>")


class Fixture(unittest.TestCase):
    """A restore output with a package folder; each package is (name, version, repository or None for no nuspec)."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.packages = os.path.join(self._td.name, "packages")

    def assets(self, frameworks: dict[str, list[tuple[str, str, str | None]]], private: tuple[str, ...] = ()) -> dict:
        document = {"project": {"frameworks": {}}, "targets": {}, "libraries": {},
                    "packageFolders": {self.packages: {}}}
        for alias, packages in frameworks.items():
            dependencies = {}
            targets = {}
            for name, version, repo in packages:
                dependency = {"target": "Package", "version": f"[{version}, )"}
                if name in private:
                    dependency["suppressParent"] = "All"
                dependencies[name] = dependency
                key = f"{name}/{version}"
                targets[key] = {"type": "package"}
                document["libraries"][key] = {"path": f"{name.lower()}/{version}"}
                if repo is not None:
                    folder = os.path.join(self.packages, name.lower(), version)
                    os.makedirs(folder, exist_ok=True)
                    with open(os.path.join(folder, name.lower() + ".nuspec"), "w", encoding="utf-8") as f:
                        f.write(nuspec(repo or None))
            document["project"]["frameworks"][alias] = {"dependencies": dependencies}
            document["targets"][alias] = targets
        return document


class RepositoryTests(Fixture):
    def write(self, repository):
        os.makedirs(self.packages)
        path = os.path.join(self.packages, "a.nuspec")
        with open(path, "w", encoding="utf-8") as f:
            f.write(nuspec(repository))
        return gate.repository(path)

    def test_url_is_reduced_to_host_and_path(self):
        self.assertEqual(self.write("https://github.com/dotnet/dotnet"), "github.com/dotnet/dotnet")

    def test_case_trailing_slash_and_git_suffix_are_dropped(self):
        self.assertEqual(self.write("HTTPS://GitHub.com/Dotnet/Runtime.git/"), "github.com/dotnet/runtime")

    def test_nuspec_without_repository_gives_empty(self):
        self.assertEqual(self.write(None), "")


class ReleaseTests(unittest.TestCase):
    def test_net_framework_alias_gives_its_release(self):
        self.assertEqual(gate.framework_release("net10.0"), 10)
        self.assertEqual(gate.framework_release("net11.0-windows"), 11)

    def test_other_frameworks_give_none(self):
        self.assertIsNone(gate.framework_release("netstandard2.0"))
        self.assertIsNone(gate.framework_release("net472"))


class CheckTests(Fixture):
    def test_package_of_a_newer_release_is_a_violation(self):
        violations, missing, checked = gate.check(self.assets({"net10.0": [
            ("Microsoft.Extensions.Logging", "11.0.0", DOTNET)]}))
        self.assertEqual(missing, [])
        self.assertEqual(checked, 1)
        self.assertEqual(len(violations), 1)
        self.assertIn("net10.0 ships Microsoft.Extensions.Logging 11.0.0, a package of .NET 11", violations[0])
        self.assertIn("Take the .NET 10 version for net10.0", violations[0])

    def test_package_of_the_same_or_an_older_release_passes(self):
        violations, _, checked = gate.check(self.assets({
            "net10.0": [("System.Numerics.Tensors", "10.0.15", DOTNET),
                        ("Microsoft.Extensions.TimeProvider.Testing", "10.11.0", "https://github.com/dotnet/extensions")],
            "net11.0": [("Microsoft.Extensions.Logging", "11.0.0", DOTNET),
                        ("Microsoft.Bcl.AsyncInterfaces", "10.0.0", "https://github.com/dotnet/runtime")],
        }))
        self.assertEqual((violations, checked), ([], 4))

    def test_prerelease_of_a_newer_release_is_a_violation(self):
        violations, _, _ = gate.check(self.assets({"net10.0": [("System.Text.Json", "11.0.0-preview.5", DOTNET)]}))
        self.assertEqual(len(violations), 1)

    def test_other_packages_of_the_dotnet_repositories_are_not_checked(self):
        violations, _, checked = gate.check(self.assets({"net10.0": [("Microsoft.Build", "18.0.0", DOTNET)]}))
        self.assertEqual((violations, checked), ([], 0))

    def test_runtime_names_from_other_repositories_are_not_checked(self):
        violations, _, checked = gate.check(self.assets({"net10.0": [
            ("System.IO.Abstractions", "22.0.0", "https://github.com/TestableIO/System.IO.Abstractions")]}))
        self.assertEqual((violations, checked), ([], 0))

    def test_package_without_repository_is_not_checked(self):
        violations, _, checked = gate.check(self.assets({"net10.0": [("System.Memory", "11.0.0", "")]}))
        self.assertEqual((violations, checked), ([], 0))

    def test_build_only_package_does_not_reach_consumers(self):
        violations, _, checked = gate.check(self.assets(
            {"net10.0": [("System.IO.Hashing", "11.0.0", DOTNET)]}, private=("System.IO.Hashing",)))
        self.assertEqual((violations, checked), ([], 0))

    def test_framework_without_a_net_release_is_skipped(self):
        violations, _, checked = gate.check(self.assets({"netstandard2.0": [("System.Memory", "11.0.0", DOTNET)]}))
        self.assertEqual((violations, checked), ([], 0))

    def test_package_without_a_nuspec_is_reported(self):
        violations, missing, _ = gate.check(self.assets({"net10.0": [("System.Memory", "10.0.0", None)]}))
        self.assertEqual((violations, missing), ([], ["System.Memory/10.0.0"]))


class MainTests(Fixture):
    def run_main(self, frameworks) -> tuple[int, str]:
        repo = os.path.join(self._td.name, "repo")
        if frameworks is not None:
            obj = os.path.join(repo, "src", "My.Package", "obj")
            os.makedirs(obj)
            with open(os.path.join(obj, "project.assets.json"), "w", encoding="utf-8") as f:
                json.dump(self.assets(frameworks), f)
        else:
            os.makedirs(repo)
        cwd = os.getcwd()
        out = io.StringIO()
        try:
            os.chdir(repo)
            with redirect_stdout(out):
                code = gate.main()
        finally:
            os.chdir(cwd)
        return code, out.getvalue()

    def test_missing_restore_output_fails(self):
        code, out = self.run_main(None)
        self.assertEqual(code, 1)
        self.assertIn("::error::No src/*/obj/project.assets.json found", out)

    def test_clean_repository_passes(self):
        code, out = self.run_main({"net10.0": [("System.Numerics.Tensors", "10.0.15", DOTNET)]})
        self.assertEqual(code, 0)
        self.assertIn("Checked 1 shipped .NET package(s) against their target frameworks; 0 problem(s).", out)

    def test_violation_and_missing_nuspec_fail_with_errors(self):
        code, out = self.run_main({"net10.0": [("System.Numerics.Tensors", "11.0.0", DOTNET),
                                               ("System.Memory", "10.0.0", None)]})
        self.assertEqual(code, 1)
        self.assertIn("::error::src/My.Package: net10.0 ships System.Numerics.Tensors 11.0.0", out)
        self.assertIn("::error::src/My.Package: no .nuspec found for System.Memory/10.0.0", out)
        self.assertIn("2 problem(s).", out)

    def test_runs_as_a_program(self):
        repo = os.path.join(self._td.name, "empty")
        os.makedirs(repo)
        cwd = os.getcwd()
        try:
            os.chdir(repo)
            with mock.patch.object(sys, "argv", ["net_line_gate.py"]), redirect_stdout(io.StringIO()), \
                    self.assertRaises(SystemExit) as raised:
                runpy.run_path(gate.__file__, run_name="__main__")
        finally:
            os.chdir(cwd)
        self.assertEqual(raised.exception.code, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

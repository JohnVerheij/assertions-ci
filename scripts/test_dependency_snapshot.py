"""Unit tests for dependency_snapshot.py. Run with: python -m unittest discover -s scripts -v"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import dependency_snapshot as snap

ROOT = os.path.abspath(os.sep + "repo")


def assets(project: str, direct: dict, targets: dict, frameworks: tuple[str, ...] = ("net10.0",)) -> dict:
    return {
        "targets": {framework: targets.get(framework, targets.get("*", {})) for framework in frameworks},
        "project": {
            "restore": {"projectPath": os.path.join(ROOT, *project.split("/"))},
            "frameworks": {framework: {"dependencies": direct} for framework in frameworks},
        },
    }


def package(*children: str) -> dict:
    return {"type": "package", "dependencies": {child: "[1.0.0, )" for child in children}}


LIBRARY_TARGETS = {"*": {
    "Runtime.Lib/1.0.0": package("Runtime.Child"),
    "Runtime.Child/2.0.0": package(),
    "Some.Analyzer/3.0.0": package("Analyzer.Child"),
    "Analyzer.Child/4.0.0": package(),
    "Other.Project/1.0.0": {"type": "project"},
}}
LIBRARY_DIRECT = {
    "Runtime.Lib": {"target": "Package", "version": "[1.0.0, )"},
    "Some.Analyzer": {"target": "Package", "version": "[3.0.0, )", "suppressParent": "All"},
}


class ManifestTests(unittest.TestCase):
    def test_src_project_scopes_and_relationships(self):
        entry = snap.manifest(assets("src/Lib/Lib.csproj", LIBRARY_DIRECT, LIBRARY_TARGETS), ROOT)
        self.assertEqual(entry["name"], "src/Lib/Lib.csproj")
        self.assertEqual(entry["file"], {"source_location": "src/Lib/Lib.csproj"})
        resolved = entry["resolved"]
        self.assertEqual(resolved["pkg:nuget/Runtime.Lib@1.0.0"],
                         {"package_url": "pkg:nuget/Runtime.Lib@1.0.0", "relationship": "direct", "scope": "runtime",
                          "dependencies": ["pkg:nuget/Runtime.Child@2.0.0"]})
        self.assertEqual(resolved["pkg:nuget/Runtime.Child@2.0.0"]["relationship"], "indirect")
        self.assertEqual(resolved["pkg:nuget/Runtime.Child@2.0.0"]["scope"], "runtime")
        self.assertEqual(resolved["pkg:nuget/Some.Analyzer@3.0.0"]["scope"], "development")
        self.assertEqual(resolved["pkg:nuget/Analyzer.Child@4.0.0"]["scope"], "development")
        self.assertEqual(resolved["pkg:nuget/Analyzer.Child@4.0.0"]["relationship"], "indirect")

    def test_project_references_are_not_packages(self):
        entry = snap.manifest(assets("src/Lib/Lib.csproj", LIBRARY_DIRECT, LIBRARY_TARGETS), ROOT)
        self.assertNotIn("pkg:nuget/Other.Project@1.0.0", entry["resolved"])

    def test_test_project_packages_are_all_development(self):
        entry = snap.manifest(assets("tests/Lib.Tests/Lib.Tests.csproj", LIBRARY_DIRECT, LIBRARY_TARGETS), ROOT)
        self.assertEqual({p["scope"] for p in entry["resolved"].values()}, {"development"})
        self.assertEqual(entry["resolved"]["pkg:nuget/Runtime.Lib@1.0.0"]["relationship"], "direct")

    def test_dependency_resolution_is_case_insensitive(self):
        targets = {"*": {"Parent/1.0.0": package("child"), "Child/5.0.0": package()}}
        entry = snap.manifest(assets("src/Lib/Lib.csproj", {"parent": {"target": "Package"}}, targets), ROOT)
        self.assertEqual(entry["resolved"]["pkg:nuget/Parent@1.0.0"]["dependencies"], ["pkg:nuget/Child@5.0.0"])
        self.assertEqual(entry["resolved"]["pkg:nuget/Parent@1.0.0"]["relationship"], "direct")

    def test_dependency_on_a_project_reference_is_left_out(self):
        targets = {"*": {"Parent/1.0.0": package("Other.Project"), "Other.Project/1.0.0": {"type": "project"}}}
        entry = snap.manifest(assets("src/Lib/Lib.csproj", {"Parent": {"target": "Package"}}, targets), ROOT)
        self.assertEqual(entry["resolved"]["pkg:nuget/Parent@1.0.0"]["dependencies"], [])

    def test_unresolvable_dependency_is_left_out(self):
        targets = {"*": {"Parent/1.0.0": package("Missing")}}
        entry = snap.manifest(assets("src/Lib/Lib.csproj", {"Parent": {"target": "Package"}}, targets), ROOT)
        self.assertEqual(entry["resolved"]["pkg:nuget/Parent@1.0.0"]["dependencies"], [])

    def test_frameworks_merge_direct_runtime_and_dependencies(self):
        targets = {
            "net9.0": {"Shared/1.0.0": package("A"), "A/1.0.0": package()},
            "net10.0": {"Shared/1.0.0": package("B"), "B/1.0.0": package(), "Extra/2.0.0": package()},
        }
        data = assets("src/Lib/Lib.csproj", {}, targets, frameworks=("net9.0", "net10.0"))
        data["project"]["frameworks"]["net9.0"]["dependencies"] = {"Shared": {"target": "Package"}}
        data["project"]["frameworks"]["net10.0"]["dependencies"] = {"Extra": {"target": "Package"}}
        resolved = snap.manifest(data, ROOT)["resolved"]
        shared = resolved["pkg:nuget/Shared@1.0.0"]
        self.assertEqual(shared["relationship"], "direct")
        self.assertEqual(shared["scope"], "runtime")
        self.assertEqual(shared["dependencies"], ["pkg:nuget/A@1.0.0", "pkg:nuget/B@1.0.0"])

    def test_direct_and_runtime_survive_a_later_framework_that_sees_neither(self):
        targets = {"net9.0": {"Shared/1.0.0": package()}, "net10.0": {"Shared/1.0.0": package()}}
        data = assets("src/Lib/Lib.csproj", {}, targets, frameworks=("net9.0", "net10.0"))
        data["project"]["frameworks"]["net9.0"]["dependencies"] = {"Shared": {"target": "Package"}}
        shared = snap.manifest(data, ROOT)["resolved"]["pkg:nuget/Shared@1.0.0"]
        self.assertEqual((shared["relationship"], shared["scope"]), ("direct", "runtime"))

    def test_resolved_entries_are_sorted(self):
        entry = snap.manifest(assets("src/Lib/Lib.csproj", LIBRARY_DIRECT, LIBRARY_TARGETS), ROOT)
        self.assertEqual(list(entry["resolved"]), sorted(entry["resolved"]))


class SnapshotTests(unittest.TestCase):
    ENV = {"GITHUB_SHA": "a" * 40, "GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ID": "42",
           "GITHUB_REPOSITORY": "owner/Repo", "DETECTOR_VERSION": "b" * 40}

    def test_request_body_fields(self):
        body = snap.snapshot({"m": {}}, self.ENV, "2026-11-01T10:00:00Z")
        self.assertEqual(body["version"], 0)
        self.assertEqual((body["sha"], body["ref"], body["scanned"]), ("a" * 40, "refs/heads/main", "2026-11-01T10:00:00Z"))
        self.assertEqual(body["job"], {"correlator": snap.CORRELATOR, "id": "42",
                                       "html_url": "https://github.com/owner/Repo/actions/runs/42"})
        self.assertEqual(body["detector"], {"name": "assertions-ci", "version": "b" * 40, "url": snap.DETECTOR_URL})
        self.assertEqual(body["manifests"], {"m": {}})

    def test_detector_version_defaults_to_local(self):
        env = {k: v for k, v in self.ENV.items() if k != "DETECTOR_VERSION"}
        self.assertEqual(snap.snapshot({}, env, "t")["detector"]["version"], "local")

    def test_missing_sha_raises(self):
        env = {k: v for k, v in self.ENV.items() if k != "GITHUB_SHA"}
        with self.assertRaises(KeyError):
            snap.snapshot({}, env, "t")


class MainTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.root = self._dir.name
        self.output = os.path.join(self.root, "snapshot.json")

    def tearDown(self):
        self._dir.cleanup()

    def write_assets(self, project: str, data: dict) -> None:
        folder = os.path.join(self.root, *os.path.dirname(project).split("/"), "obj")
        os.makedirs(folder, exist_ok=True)
        data["project"]["restore"]["projectPath"] = os.path.join(self.root, *project.split("/"))
        with open(os.path.join(folder, "project.assets.json"), "w", encoding="utf-8") as handle:
            json.dump(data, handle)

    def run_main(self, env: dict | None = None) -> tuple[int, str]:
        stdout = io.StringIO()
        with mock.patch.dict(os.environ, env if env is not None else SnapshotTests.ENV, clear=True), redirect_stdout(stdout):
            code = snap.main(["dependency_snapshot.py", self.output], self.root)
        return code, stdout.getvalue()

    def test_writes_one_manifest_per_src_and_tests_project(self):
        self.write_assets("src/Lib/Lib.csproj", assets("src/Lib/Lib.csproj", LIBRARY_DIRECT, LIBRARY_TARGETS))
        self.write_assets("tests/Lib.Tests/Lib.Tests.csproj", assets("x", LIBRARY_DIRECT, LIBRARY_TARGETS))
        self.write_assets("other/Tool/Tool.csproj", assets("x", LIBRARY_DIRECT, LIBRARY_TARGETS))
        code, stdout = self.run_main()
        self.assertEqual(code, 0)
        with open(self.output, encoding="utf-8") as handle:
            body = json.load(handle)
        self.assertEqual(list(body["manifests"]), ["src/Lib/Lib.csproj", "tests/Lib.Tests/Lib.Tests.csproj"])
        self.assertRegex(body["scanned"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertIn("src/Lib/Lib.csproj: 4 packages (2 runtime)", stdout)

    def test_no_restore_output_returns_1(self):
        code, stdout = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("dotnet restore", stdout)
        self.assertFalse(os.path.exists(self.output))

    def test_missing_environment_returns_1(self):
        self.write_assets("src/Lib/Lib.csproj", assets("x", LIBRARY_DIRECT, LIBRARY_TARGETS))
        code, stdout = self.run_main(env={})
        self.assertEqual(code, 1)
        self.assertIn("GITHUB_SHA", stdout)

    def test_wrong_argument_count_returns_1(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(snap.main(["dependency_snapshot.py"], self.root), 1)
        self.assertIn("usage", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()

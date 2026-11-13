"""Unit tests for family_sync.py. Run with: python -m unittest discover -s scripts -v"""

import contextlib
import io
import json
import os
import runpy
import sys
import tempfile
import unittest
from unittest import mock

import family_lint
import family_sync as fs

PIN = "0123456789abcdef0123456789abcdef01234567 # v9.9.9"
CI = f"jobs:\n  ci:\n    uses: JohnVerheij/assertions-ci/.github/workflows/package-ci.yml@{PIN}\n"
TOOLS = {"version": 1, "isRoot": True, "tools": {tool: {"version": "1.0.0", "commands": [tool]}
                                                  for tool in fs.REQUIRED_TOOLS}}


def _write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _read(root, rel):
    with open(os.path.join(root, *rel.split("/")), encoding="utf-8") as handle:
        return handle.read()


def _template(rel):
    with open(fs.template_path(rel), encoding="utf-8") as handle:
        return handle.read()


class _Repo(unittest.TestCase):
    """A repository of the package DemoAssertions that matches the family templates."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = self._td.name
        self.addCleanup(self._td.cleanup)
        _write(self.root, "src/DemoAssertions.TUnit/DemoAssertions.TUnit.csproj", "<Project />")
        _write(self.root, "src/DemoAssertions/DemoAssertions.csproj", "<Project />")
        _write(self.root, ".github/workflows/ci.yml", CI)
        _write(self.root, ".config/dotnet-tools.json", json.dumps(TOOLS))
        for rel in fs.template_files():
            _write(self.root, rel, fs.render(_template(rel), "DemoAssertions", True, PIN))

    def check(self):
        return fs.check(self.root, "DemoAssertions")


class TemplateTests(unittest.TestCase):
    def test_templates_include_the_shared_files(self):
        files = fs.template_files()
        for rel in (".gitignore", ".github/renovate.json", ".github/workflows/family-lint.yml", "docs/docfx.json"):
            self.assertIn(rel, files)

    def test_templates_are_american_english(self):
        for rel in fs.template_files():
            self.assertEqual(family_lint.british_spellings(_template(rel), rel), [], rel)

    def test_templates_have_no_typographic_unicode(self):
        typographic = set("\u2010\u2011\u2012\u2013\u2014\u2015\u2018\u2019\u201c\u201d\u2026\u2192\u00d7")
        for rel in fs.template_files():
            self.assertFalse(typographic & set(_template(rel)), rel)

    def test_workflow_templates_carry_the_suffix(self):
        workflows = [rel for rel in fs.template_files() if rel.startswith(".github/workflows/")]
        self.assertTrue(workflows)
        for rel in workflows:
            self.assertFalse(rel.endswith(fs.TEMPLATE_SUFFIX), rel)
            self.assertTrue(os.path.isfile(os.path.join(fs.TEMPLATES, rel + fs.TEMPLATE_SUFFIX)), rel)
            self.assertFalse(os.path.exists(os.path.join(fs.TEMPLATES, rel)), rel)

    def test_template_path_of_a_plain_and_a_suffixed_template(self):
        self.assertEqual(fs.template_path("LICENSE"), os.path.join(fs.TEMPLATES, "LICENSE"))
        self.assertEqual(fs.template_path(".github/workflows/zizmor.yml"),
                         os.path.join(fs.TEMPLATES, ".github/workflows/zizmor.yml") + fs.TEMPLATE_SUFFIX)


class RenderTests(unittest.TestCase):
    def test_placeholders_filled(self):
        text = fs.render("{{Package}} at https://{{domain}}/ uses @{{assertions-ci}}", "LogAssertions", True, PIN)
        self.assertEqual(text, f"LogAssertions at https://logassertions.dev/ uses @{PIN}")

    def test_core_line_kept_with_a_core(self):
        self.assertEqual(fs.render("a\n{{core}}b\nc", "X", True, None), "a\nb\nc")

    def test_core_line_dropped_without_a_core(self):
        self.assertEqual(fs.render("a\n{{core}}b\nc", "X", False, None), "a\nc")

    def test_missing_pin_raises(self):
        with self.assertRaises(ValueError):
            fs.render("uses: x@{{assertions-ci}}", "X", True, None)

    def test_text_without_pin_placeholder_needs_no_pin(self):
        self.assertEqual(fs.render("plain", "X", True, None), "plain")


class PinTests(unittest.TestCase):
    def test_pins_are_not_compared(self):
        a = "uses: actions/checkout@" + "a" * 40 + " # v1"
        b = "uses: actions/checkout@" + "b" * 40 + " # v2"
        self.assertEqual(fs._without_pins(a), fs._without_pins(b))

    def test_existing_pins_kept_on_write(self):
        rendered = "uses: actions/checkout@" + "a" * 40 + " # v1\nuses: other/action@" + "c" * 40 + " # v3"
        existing = "uses: actions/checkout@" + "b" * 40 + " # v2"
        kept = fs._keep_pins(rendered, existing)
        self.assertIn("b" * 40 + " # v2", kept)
        self.assertIn("c" * 40 + " # v3", kept)

    def test_assertions_ci_pins_are_compared(self):
        a = "uses: JohnVerheij/assertions-ci/.github/workflows/package-lint.yml@" + "a" * 40 + " # v1.4.0"
        b = "uses: JohnVerheij/assertions-ci/.github/workflows/package-lint.yml@" + "b" * 40 + " # v1.5.0"
        self.assertNotEqual(fs._without_pins(a), fs._without_pins(b))
        self.assertEqual(fs._keep_pins(a, b), a)

    def test_first_difference_line(self):
        self.assertEqual(fs._first_difference("a\nb\nc", "a\nB\nc"), 2)
        self.assertEqual(fs._first_difference("same", "same"), 0)


class RepositoryInfoTests(_Repo):
    def test_package_name_found(self):
        self.assertEqual(fs.package_name(self.root), "DemoAssertions")

    def test_package_name_absent(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertIsNone(fs.package_name(empty))

    def test_core_detected(self):
        self.assertTrue(fs.has_core(self.root, "DemoAssertions"))
        os.remove(os.path.join(self.root, "src", "DemoAssertions", "DemoAssertions.csproj"))
        self.assertFalse(fs.has_core(self.root, "DemoAssertions"))

    def test_pin_read_from_ci_yml(self):
        self.assertEqual(fs.assertions_ci_pin(self.root), PIN)

    def test_pin_absent_without_ci_yml(self):
        os.remove(os.path.join(self.root, ".github", "workflows", "ci.yml"))
        self.assertIsNone(fs.assertions_ci_pin(self.root))

    def test_pin_absent_when_ci_yml_does_not_call_package_ci(self):
        _write(self.root, ".github/workflows/ci.yml", "jobs: {}\n")
        self.assertIsNone(fs.assertions_ci_pin(self.root))


class CheckTests(_Repo):
    def test_conforming_repository_has_no_issues(self):
        self.assertEqual(self.check(), [])

    def test_crlf_line_endings_do_not_count(self):
        path = os.path.join(self.root, ".gitignore")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8", newline="\r\n") as handle:
            handle.write(text)
        self.assertEqual(self.check(), [])

    def test_missing_file_reported(self):
        os.remove(os.path.join(self.root, "LICENSE"))
        self.assertEqual(self.check(), ["LICENSE: missing (family template)"])

    def test_changed_file_reported_with_line(self):
        _write(self.root, ".gitignore", _read(self.root, ".gitignore").replace("bld/", "build/"))
        issues = self.check()
        self.assertEqual(len(issues), 1)
        self.assertIn(".gitignore: differs from the family template (first difference at line", issues[0])

    def test_newer_action_pin_is_not_drift(self):
        rel = ".github/workflows/scorecard.yml"
        text = _read(self.root, rel)
        _write(self.root, rel, fs.ACTION_PIN_RE.sub(lambda m: m.group(1) + "f" * 40 + " # v99", text))
        self.assertEqual(self.check(), [])

    def test_stale_assertions_ci_pin_in_a_caller_is_drift(self):
        rel = ".github/workflows/family-lint.yml"
        _write(self.root, rel, _read(self.root, rel).replace(PIN, "f" * 40 + " # v1.3.0"))
        issues = self.check()
        self.assertEqual(len(issues), 1)
        self.assertIn(rel + ": differs from the family template", issues[0])

    def test_obsolete_file_reported(self):
        _write(self.root, ".github/family-lint.py", "# old copy")
        self.assertEqual(self.check(), [".github/family-lint.py: obsolete, now shared from assertions-ci"])

    def test_missing_pin_reported_per_caller(self):
        os.remove(os.path.join(self.root, ".github", "workflows", "ci.yml"))
        issues = self.check()
        self.assertTrue(issues)
        self.assertTrue(all("cannot render the family template: no assertions-ci pin" in issue for issue in issues))

    def test_missing_tool_reported(self):
        tools = json.loads(json.dumps(TOOLS))
        del tools["tools"]["docfx"]
        _write(self.root, ".config/dotnet-tools.json", json.dumps(tools))
        self.assertEqual(self.check(), [".config/dotnet-tools.json: missing the local tool docfx "
                                        "(add it: dotnet tool install --local docfx)"])

    def test_missing_tool_manifest_reported(self):
        os.remove(os.path.join(self.root, ".config", "dotnet-tools.json"))
        self.assertEqual(len(self.check()), 1)
        self.assertIn("dotnet new tool-manifest", self.check()[0])


class WriteTests(_Repo):
    def test_nothing_to_write_when_conforming(self):
        self.assertEqual(fs.write(self.root, "DemoAssertions"), [])

    def test_writes_missing_and_changed_files_and_deletes_obsolete_ones(self):
        os.remove(os.path.join(self.root, "LICENSE"))
        _write(self.root, ".gitignore", "changed\n")
        _write(self.root, ".github/docs-linkcheck.py", "# old copy")
        changed = fs.write(self.root, "DemoAssertions")
        self.assertEqual(sorted(changed), ["deleted .github/docs-linkcheck.py", "wrote .gitignore", "wrote LICENSE"])
        self.assertEqual(self.check(), [])

    def test_write_keeps_the_repository_pins(self):
        rel = ".github/workflows/scorecard.yml"
        text = fs.ACTION_PIN_RE.sub(lambda m: m.group(1) + "f" * 40 + " # v99", _read(self.root, rel))
        _write(self.root, rel, text.replace("name: Scorecard", "name: Old scorecard", 1))
        fs.write(self.root, "DemoAssertions")
        written = _read(self.root, rel)
        self.assertNotIn("Old scorecard", written)
        self.assertIn("f" * 40 + " # v99", written)

    def test_write_replaces_a_stale_assertions_ci_pin(self):
        rel = ".github/workflows/family-lint.yml"
        _write(self.root, rel, _read(self.root, rel).replace(PIN, "f" * 40 + " # v1.3.0"))
        self.assertEqual(fs.write(self.root, "DemoAssertions"), ["wrote " + rel])
        self.assertIn(PIN, _read(self.root, rel))
        self.assertEqual(self.check(), [])

    def test_write_refuses_without_a_pin(self):
        os.remove(os.path.join(self.root, ".github", "workflows", "ci.yml"))
        with self.assertRaises(ValueError):
            fs.write(self.root, "DemoAssertions")


class MainTests(_Repo):
    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = fs.main(["family_sync.py", *args])
        return code, out.getvalue()

    def test_check_ok(self):
        self.assertEqual(self.run_main(self.root), (0, "OK  the repository matches the family templates\n"))

    def test_check_fail(self):
        os.remove(os.path.join(self.root, "LICENSE"))
        code, out = self.run_main(self.root)
        self.assertEqual(code, 1)
        self.assertIn("LICENSE: missing", out)

    def test_write_reports_changes(self):
        os.remove(os.path.join(self.root, "LICENSE"))
        self.assertEqual(self.run_main("--write", self.root), (0, "wrote LICENSE\n"))

    def test_write_reports_nothing_to_do(self):
        code, out = self.run_main("--write", self.root)
        self.assertEqual(code, 0)
        self.assertIn("Nothing to write", out)

    def test_write_lists_the_missing_tools_it_cannot_add(self):
        tools = json.loads(json.dumps(TOOLS))
        del tools["tools"]["docfx"]
        _write(self.root, ".config/dotnet-tools.json", json.dumps(tools))
        os.remove(os.path.join(self.root, "LICENSE"))
        code, out = self.run_main("--write", self.root)
        self.assertEqual(code, 1)
        self.assertEqual(out, "wrote LICENSE\nFAIL (1 issue(s)) left to fix by hand:\n"
                              "  - .config/dotnet-tools.json: missing the local tool docfx "
                              "(add it: dotnet tool install --local docfx)\n")
        self.assertTrue(os.path.isfile(os.path.join(self.root, "LICENSE")))

    def test_write_error_exits_one(self):
        os.remove(os.path.join(self.root, ".github", "workflows", "ci.yml"))
        code, out = self.run_main("--write", self.root)
        self.assertEqual(code, 1)
        self.assertIn("::error::", out)

    def test_no_package_exits_one(self):
        with tempfile.TemporaryDirectory() as empty:
            code, out = self.run_main(empty)
        self.assertEqual(code, 1)
        self.assertIn("has no src/<Package>.TUnit", out)

    def test_default_root_is_the_current_directory(self):
        cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)
        self.assertEqual(self.run_main()[0], 0)

    def test_runs_as_a_program(self):
        with mock.patch.object(sys, "argv", ["family_sync.py", self.root]), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            runpy.run_path(fs.__file__, run_name="__main__")
        self.assertEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

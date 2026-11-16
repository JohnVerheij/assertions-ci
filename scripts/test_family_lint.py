#!/usr/bin/env python3
"""Tests for the family lint gate. Stdlib unittest only; run with: python -m unittest discover -s scripts -v"""
import contextlib
import io
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import family_lint as fl

# A minimal, fully-conforming changelog. Every invalid fixture below is a single
# mutation of this baseline, so a test failure points at exactly one rule.
VALID = """\
# Changelog

## [Unreleased]

## [1.1.0] - 2026-06-02: second release
### Added
- `Thing.New()` does a thing.
### Fixed
- `Thing.Old()` no longer misbehaves.

## [1.0.0] - 2026-06-01: first release
### Added
- `Thing.Old()` does a thing.

[unreleased]: https://example.com/compare/v1.1.0...HEAD
[1.1.0]: https://example.com/compare/v1.0.0...v1.1.0
[1.0.0]: https://example.com/releases/tag/v1.0.0
"""


def _matches(issues, needle):
    return any(needle in issue for issue in issues)


class _Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.dir = self._td.name
        self.addCleanup(self._td.cleanup)

    def changelog(self, text):
        path = os.path.join(self.dir, "CHANGELOG.md")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        return fl.lint_changelog(path)

    def csproj(self, name, tags):
        path = os.path.join(self.dir, name)
        body = tags if tags is None else f"<Project><PropertyGroup><PackageTags>{tags}</PackageTags></PropertyGroup></Project>"
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(body or "<Project></Project>")
        return fl.lint_tags(path)


class ChangelogTests(_Base):
    def test_valid_changelog_has_no_issues(self):
        self.assertEqual(self.changelog(VALID), [])

    def test_missing_unreleased_section_flagged(self):
        text = VALID.replace("## [Unreleased]\n\n", "")
        self.assertTrue(_matches(self.changelog(text), "missing '## [Unreleased]' section"))

    def test_missing_unreleased_footer_flagged(self):
        text = VALID.replace("[unreleased]: https://example.com/compare/v1.1.0...HEAD\n", "")
        self.assertTrue(_matches(self.changelog(text), "missing '[unreleased]:' footer link"))

    def test_first_section_must_be_unreleased(self):
        text = VALID.replace("## [Unreleased]\n\n", "")
        self.assertTrue(_matches(self.changelog(text), "first section must be '## [Unreleased]'"))

    def test_sub_header_deeper_than_h3_flagged(self):
        text = VALID.replace("### Added\n- `Thing.New()`", "### Added\n#### Nested\n- `Thing.New()`", 1)
        self.assertTrue(_matches(self.changelog(text), "sub-header deeper than '###'"))

    def test_non_standard_section_flagged(self):
        text = VALID.replace("### Added\n- `Thing.New()`", "### Notes\n- `Thing.New()`", 1)
        self.assertTrue(_matches(self.changelog(text), "non-standard section '### Notes'"))

    def test_out_of_order_sections_flagged(self):
        # Fixed (index 4) before Added (index 0) under the same version.
        text = VALID.replace(
            "### Added\n- `Thing.New()` does a thing.\n### Fixed\n- `Thing.Old()` no longer misbehaves.",
            "### Fixed\n- `Thing.Old()` no longer misbehaves.\n### Added\n- `Thing.New()` does a thing.",
        )
        self.assertTrue(_matches(self.changelog(text), "out of order"))

    def test_duplicate_section_flagged(self):
        # Two '### Added' blocks under one version (same rank) must be flagged.
        text = VALID.replace(
            "### Added\n- `Thing.New()` does a thing.\n### Fixed",
            "### Added\n- `Thing.New()` does a thing.\n### Added\n- `Thing.Extra()` also.\n### Fixed",
            1,
        )
        self.assertTrue(_matches(self.changelog(text), "duplicate '### Added'"))

    def test_duplicate_unreleased_flagged(self):
        text = VALID.replace("## [Unreleased]\n\n", "## [Unreleased]\n\n## [Unreleased]\n\n", 1)
        self.assertTrue(_matches(self.changelog(text), "duplicate '## [Unreleased]'"))

    def test_footer_missing_space_flagged(self):
        # '[1.0.0]:https://...' must get a targeted spacing error, not fall
        # through to a generic 'has no footer link'.
        text = VALID.replace(
            "[1.0.0]: https://example.com/releases/tag/v1.0.0",
            "[1.0.0]:https://example.com/releases/tag/v1.0.0",
        )
        issues = self.changelog(text)
        self.assertTrue(_matches(issues, "needs exactly one space after ':'"))
        self.assertFalse(_matches(issues, "has no footer link"))

    def test_unreleased_footer_missing_space_flagged(self):
        text = VALID.replace(
            "[unreleased]: https://example.com/compare/v1.1.0...HEAD",
            "[unreleased]:https://example.com/compare/v1.1.0...HEAD",
        )
        self.assertTrue(_matches(self.changelog(text), "needs exactly one space after ':'"))

    def test_version_header_without_summary_flagged(self):
        text = VALID.replace("## [1.0.0] - 2026-06-01: first release", "## [1.0.0] - 2026-06-01")
        self.assertTrue(_matches(self.changelog(text), "version header not"))

    def test_malformed_version_header_flagged(self):
        # A '## [' header that is neither '## [Unreleased]' nor a valid 'x.y.z'
        # must be flagged, not silently skipped.
        for bad in ("## [1.0]", "## [v1.0.0]", "## [abc]"):
            with self.subTest(header=bad):
                text = VALID.replace("## [1.0.0] - 2026-06-01: first release", f"{bad} - 2026-06-01: first release")
                self.assertTrue(_matches(self.changelog(text), "malformed version header"))

    def test_ascending_version_order_flagged(self):
        text = VALID.replace(
            "## [1.1.0] - 2026-06-02: second release", "## [0.9.0] - 2026-06-02: second release"
        ).replace("[1.1.0]: https://example.com/compare/v1.0.0...v1.1.0",
                  "[0.9.0]: https://example.com/compare/v1.0.0...v0.9.0")
        self.assertTrue(_matches(self.changelog(text), "newest-first"))

    def test_footer_wrong_target_flagged(self):
        text = VALID.replace(
            "[1.0.0]: https://example.com/releases/tag/v1.0.0",
            "[1.0.0]: https://example.com/releases/tag/v9.9.9",
        )
        self.assertTrue(_matches(self.changelog(text), "should target 'v1.0.0'"))

    def test_unreleased_footer_wrong_target_flagged(self):
        text = VALID.replace(
            "[unreleased]: https://example.com/compare/v1.1.0...HEAD",
            "[unreleased]: https://example.com/compare/v1.1.0...main",
        )
        self.assertTrue(_matches(self.changelog(text), "should target 'HEAD'"))

    def test_version_section_without_footer_flagged(self):
        text = VALID.replace("[1.0.0]: https://example.com/releases/tag/v1.0.0\n", "")
        self.assertTrue(_matches(self.changelog(text), "[1.0.0] version section has no footer link"))

    def test_footer_without_version_section_flagged(self):
        text = VALID.replace(
            "[1.0.0]: https://example.com/releases/tag/v1.0.0",
            "[1.0.0]: https://example.com/releases/tag/v1.0.0\n[0.5.0]: https://example.com/releases/tag/v0.5.0",
        )
        self.assertTrue(_matches(self.changelog(text), "[0.5.0] footer link has no version section"))


class TagTests(_Base):
    ADAPTER = "Foo.TUnit.csproj"
    CORE = "Foo.csproj"

    def test_valid_adapter_tags(self):
        self.assertEqual(self.csproj(self.ADAPTER, "tunit;assertions;testing;logging;dotnet;aot"), [])

    def test_valid_core_tags(self):
        self.assertEqual(self.csproj(self.CORE, "assertions;testing;logging;dotnet;aot"), [])

    def test_adapter_wrong_lead_flagged(self):
        issues = self.csproj(self.ADAPTER, "assertions;tunit;testing;dotnet;aot")
        self.assertTrue(_matches(issues, "must start with 'tunit;assertions;testing'"))

    def test_core_wrong_lead_flagged(self):
        issues = self.csproj(self.CORE, "testing;assertions;logging;dotnet;aot")
        self.assertTrue(_matches(issues, "must start with 'assertions;testing'"))

    def test_core_containing_tunit_flagged(self):
        issues = self.csproj(self.CORE, "assertions;testing;tunit;dotnet;aot")
        self.assertTrue(_matches(issues, "must not contain 'tunit'"))

    def test_wrong_trailer_flagged(self):
        issues = self.csproj(self.CORE, "assertions;testing;logging;aot;dotnet")
        self.assertTrue(_matches(issues, "must end with 'dotnet;aot'"))

    def test_csproj_without_tags_is_ignored(self):
        self.assertEqual(self.csproj(self.CORE, None), [])



def _write(root, name, text):
    path = os.path.join(root, *name.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return name


class SpellingTests(_Base):
    def test_prose_british_spelling_flagged(self):
        issues = fl.british_spellings("The behaviour is documented.", "README.md")
        self.assertEqual(issues, ["README.md:1: British spelling 'behaviour' (use American English)"])

    def test_every_stem_flagged(self):
        text = "initialise behaviour recognised artefact honours normalised cancelled serialised colour favour licence"
        self.assertEqual(len(fl.british_spellings(text, "x.md")), 11)

    def test_every_ise_stem_and_suffix_flagged(self):
        words = ("organise synchronised customising optimisation utilises prioritised summariser categorisations "
                 "serialisable initialisers centre")
        issues = fl.british_spellings(words, "x.md")
        self.assertEqual(len(issues), 11, issues)

    def test_ise_stem_without_an_ise_ending_is_not_flagged(self):
        self.assertEqual(fl.british_spellings("an organism, a realistic test, an initialism", "x.md"), [])

    def test_analyse_forms_flagged(self):
        issues = fl.british_spellings("analyse analysed analysing analyser analysers", "x.md")
        self.assertEqual(len(issues), 5, issues)

    def test_analysis_and_its_plural_pass(self):
        self.assertEqual(fl.british_spellings("one analysis, two analyses, analyzed", "x.md"), [])

    def test_lowercase_inside_a_word_flagged(self):
        self.assertTrue(_matches(fl.british_spellings("no misbehaviour here", "x.md"), "'behaviour'"))

    def test_sentence_start_capital_flagged(self):
        self.assertTrue(_matches(fl.british_spellings("Done. Cancelled runs stop.", "x.md"), "'Cancelled'"))

    def test_camel_case_identifier_exempt(self):
        self.assertEqual(fl.british_spellings("call `IsCancelled()` first", "x.md"), [])

    def test_function_call_exempt(self):
        self.assertEqual(fl.british_spellings("if: ${{ !cancelled() }}", "ci.yml"), [])

    def test_word_before_a_space_and_parenthesis_is_prose(self):
        self.assertTrue(_matches(fl.british_spellings("runs are cancelled (rarely)", "x.md"), "'cancelled'"))

    def test_member_access_identifier_exempt(self):
        self.assertEqual(fl.british_spellings("StatusCode.Cancelled maps to 1", "x.md"), [])

    def test_underscore_joined_names_exempt(self):
        text = "Status_Cancelled_Fails, cancelled_runs and run_cancelled"
        self.assertEqual(fl.british_spellings(text, "x.md"), [])

    def test_capital_after_a_digit_exempt(self):
        self.assertEqual(fl.british_spellings("use Utf8Serialiser here", "x.md"), [])

    def test_capitalized_word_in_csharp_exempt(self):
        self.assertEqual(fl.british_spellings('Assert.That(state).IsEqualTo("Cancelled");', "Tests.cs"), [])

    def test_capitalized_prose_word_outside_csharp_flagged(self):
        self.assertTrue(_matches(fl.british_spellings('state: "Cancelled"', "x.md"), "'Cancelled'"))

    def test_lowercase_word_in_csharp_flagged(self):
        self.assertTrue(_matches(fl.british_spellings("// the run is cancelled", "Tests.cs"), "'cancelled'"))

    def test_line_numbers_reported(self):
        issues = fl.british_spellings("fine\nfine\ncolour", "x.md")
        self.assertTrue(_matches(issues, "x.md:3:"))

    def test_lint_spelling_skips_history_baselines_and_binaries(self):
        files = [
            _write(self.dir, "CHANGELOG.md", "behaviour"),
            _write(self.dir, "tests/P.Tests/Snapshots/Api.expected.txt", "behaviour"),
            _write(self.dir, "tests/P.Tests/Api.verified.txt", "behaviour"),
            _write(self.dir, "LICENSE", "licence"),
            _write(self.dir, "src/P/packages.lock.json", "colour"),
            _write(self.dir, "image.png", "behaviour"),
        ]
        self.assertEqual(fl.lint_spelling(self.dir, files), [])

    def test_lint_spelling_checks_dotfiles_and_sources(self):
        files = [_write(self.dir, ".editorconfig", "# artefact"), _write(self.dir, "src/P/A.cs", "// colour")]
        self.assertEqual(len(fl.lint_spelling(self.dir, files)), 2)

    def test_lint_spelling_skips_missing_and_undecodable_files(self):
        path = os.path.join(self.dir, "bad.md")
        with open(path, "wb") as handle:
            handle.write(b"\xff\xfe\xfa behaviour")
        self.assertEqual(fl.lint_spelling(self.dir, ["bad.md", "gone.md"]), [])

    def test_tracked_files_without_git_walks_the_folder(self):
        _write(self.dir, "a/b.md", "x")
        self.assertIn("a/b.md", fl._tracked_files(self.dir))

    def test_folder_walk_skips_git_and_the_shared_clone(self):
        _write(self.dir, "a/b.md", "x")
        _write(self.dir, ".git/HEAD.md", "x")
        _write(self.dir, ".assertions-ci/scripts/family_lint.py", "x")
        with mock.patch.object(fl.subprocess, "run", side_effect=OSError):
            self.assertEqual(fl._tracked_files(self.dir), ["a/b.md"])


ADAPTER_CSPROJ = "<Project><PropertyGroup><Version>0.4.2</Version></PropertyGroup></Project>"
PROPS = '<Project><ItemGroup><PackageVersion Include="TUnit" Version="1.83.0" /></ItemGroup></Project>'
FAMILY_LIST = "\n".join(f"- {name}.TUnit" for name in fl.FAMILY)
SECURITY = """# Security

## Supported versions

| Version line | Status | Receives security fixes |
|---|---|---|
| `0.4.x` | **Current** | Yes |
| `0.3.x` | Previous stable | Yes |
"""


class ReadmeFactsTests(_Base):
    def repo(self, root_readme="**Requirements:** TUnit 1.83.0 or later.", adapter_readme=None, security=SECURITY,
             props=PROPS):
        _write(self.dir, "src/GrpcAssertions.TUnit/GrpcAssertions.TUnit.csproj", ADAPTER_CSPROJ)
        if props is not None:
            _write(self.dir, "Directory.Packages.props", props)
        if root_readme is not None:
            _write(self.dir, "README.md", root_readme)
        if adapter_readme is None:
            adapter_readme = "**Requirements:** TUnit 1.83.0 or later.\n" + FAMILY_LIST
        _write(self.dir, "src/GrpcAssertions.TUnit/README.md", adapter_readme)
        if security is not None:
            _write(self.dir, "SECURITY.md", security)
        return fl.lint_readme_facts(self.dir, "GrpcAssertions")

    def test_conforming_repo_has_no_issues(self):
        self.assertEqual(self.repo(), [])

    def test_adapter_package_found(self):
        self.repo()
        self.assertEqual(fl.adapter_package(self.dir), "GrpcAssertions")

    def test_adapter_package_absent(self):
        self.assertIsNone(fl.adapter_package(self.dir))

    def test_floor_mismatch_flagged(self):
        issues = self.repo(root_readme="TUnit 1.81.10 or later")
        self.assertEqual(issues, ["README.md: TUnit minimum 1.81.10 differs from the central TUnit version 1.83.0"])

    def test_core_readme_floor_checked_when_present(self):
        _write(self.dir, "src/GrpcAssertions/README.md", "TUnit 1.81.16 or later")
        self.assertTrue(_matches(self.repo(), "src/GrpcAssertions/README.md: TUnit minimum 1.81.16"))

    def test_core_readme_without_floor_is_fine(self):
        _write(self.dir, "src/GrpcAssertions/README.md", "No TUnit line here.")
        self.assertEqual(self.repo(), [])

    def test_required_readme_without_floor_flagged(self):
        self.assertTrue(_matches(self.repo(root_readme="No floor."), "README.md: no 'TUnit X.Y.Z or later' line"))

    def test_missing_root_readme_flagged(self):
        self.assertTrue(_matches(self.repo(root_readme=None), "README.md: missing"))

    def test_no_props_skips_the_floor_check(self):
        self.assertEqual(self.repo(root_readme="TUnit 9.9.9 or later", props=None), [])

    def test_props_without_tunit_skips_the_floor_check(self):
        self.assertEqual(self.repo(root_readme="TUnit 9.9.9 or later", props="<Project />"), [])

    def test_family_list_missing_sibling_flagged(self):
        readme = "TUnit 1.83.0 or later\n" + FAMILY_LIST.replace("- TimeAssertions.TUnit", "")
        issues = self.repo(adapter_readme=readme)
        self.assertEqual(issues, ["src/GrpcAssertions.TUnit/README.md: family list does not name TimeAssertions.TUnit"])

    def test_family_list_need_not_name_itself(self):
        readme = "TUnit 1.83.0 or later\n" + FAMILY_LIST.replace("- GrpcAssertions.TUnit", "")
        self.assertEqual(self.repo(adapter_readme=readme), [])

    def test_security_old_first_row_flagged(self):
        issues = self.repo(security=SECURITY.replace("`0.4.x`", "`0.3.x`", 1))
        self.assertEqual(issues, ["SECURITY.md: first supported version line is 0.3.x, the package version is 0.4.x"])

    def test_security_without_table_flagged(self):
        self.assertTrue(_matches(self.repo(security="# Security\n"), "no supported-versions table"))

    def test_security_missing_file_skipped(self):
        self.assertEqual(self.repo(security=None), [])


FRAMEWORKS_CSPROJ = "<Project><PropertyGroup><TargetFrameworks>{}</TargetFrameworks></PropertyGroup></Project>"
NET_BADGE = "[![.NET](https://img.shields.io/badge/.NET-{}-512BD4.svg)](https://dotnet.microsoft.com/)"
REQUIREMENTS = "**Requirements:** TUnit 1.83.0 or later, .NET 10 or .NET 11."


class FrameworkTests(_Base):
    def repo(self, frameworks="net10.0;net11.0", badge="10.0%20%7C%2011.0", requirements=REQUIREMENTS,
             adapter_badge=None):
        _write(self.dir, "src/GrpcAssertions.TUnit/GrpcAssertions.TUnit.csproj", FRAMEWORKS_CSPROJ.format(frameworks))
        root = (NET_BADGE.format(badge) + "\n" if badge else "") + (requirements or "")
        _write(self.dir, "README.md", root)
        adapter = adapter_badge if adapter_badge is not None else badge
        _write(self.dir, "src/GrpcAssertions.TUnit/README.md",
               (NET_BADGE.format(adapter) + "\n" if adapter else "") + (requirements or ""))
        return fl.lint_frameworks(self.dir, "GrpcAssertions")

    def test_conforming_repo_has_no_issues(self):
        self.assertEqual(self.repo(), [])

    def test_badge_order_and_spaces_do_not_matter(self):
        self.assertEqual(self.repo(badge="11.0%20|%2010.0"), [])

    def test_adapter_without_frameworks_skips_the_check(self):
        _write(self.dir, "src/GrpcAssertions.TUnit/GrpcAssertions.TUnit.csproj", ADAPTER_CSPROJ)
        _write(self.dir, "README.md", "no badge")
        self.assertEqual(fl.lint_frameworks(self.dir, "GrpcAssertions"), [])

    def test_missing_adapter_project_skips_the_check(self):
        self.assertEqual(fl.lint_frameworks(self.dir, "GrpcAssertions"), [])

    def test_project_with_other_frameworks_flagged(self):
        _write(self.dir, "tests/GrpcAssertions.Tests/GrpcAssertions.Tests.csproj", FRAMEWORKS_CSPROJ.format("net10.0"))
        self.assertEqual(self.repo(), ["tests/GrpcAssertions.Tests/GrpcAssertions.Tests.csproj: target frameworks "
                                       "net10.0 differ from the adapter's net10.0;net11.0"])

    def test_project_in_another_order_is_fine(self):
        _write(self.dir, "src/GrpcAssertions/GrpcAssertions.csproj", FRAMEWORKS_CSPROJ.format(" net11.0; net10.0; "))
        self.assertEqual(self.repo(), [])

    def test_project_that_inherits_or_conditions_its_frameworks_is_skipped(self):
        _write(self.dir, "tests/A/A.csproj", "<Project><PropertyGroup /></Project>")
        _write(self.dir, "tests/B/B.csproj",
               "<Project><PropertyGroup><TargetFrameworks Condition=\"'$(X)' == ''\">net8.0</TargetFrameworks>"
               "</PropertyGroup></Project>")
        self.assertEqual(self.repo(), [])

    def test_single_framework_element_is_read(self):
        _write(self.dir, "tests/A/A.csproj", "<Project><PropertyGroup><TargetFramework>net9.0</TargetFramework>"
                                             "</PropertyGroup></Project>")
        self.assertTrue(_matches(self.repo(), "tests/A/A.csproj: target frameworks net9.0 differ"))

    def test_frameworks_without_a_net_version_check_only_the_projects(self):
        self.assertEqual(self.repo(frameworks="netstandard2.0", badge=None, requirements="TUnit 1.83.0 or later"), [])

    def test_badge_that_misses_a_version_flagged(self):
        issues = self.repo(badge="10.0")
        self.assertEqual(issues, ["README.md: .NET badge names 10.0, the packages target 10.0 | 11.0",
                                  "src/GrpcAssertions.TUnit/README.md: .NET badge names 10.0, "
                                  "the packages target 10.0 | 11.0"])

    def test_required_readme_without_badge_flagged(self):
        issues = self.repo(adapter_badge="")
        self.assertEqual(issues, ["src/GrpcAssertions.TUnit/README.md: no .NET badge "
                                  "(img.shields.io/badge/.NET-...) naming 10.0 | 11.0"])

    def test_core_readme_badge_checked_when_present(self):
        _write(self.dir, "src/GrpcAssertions/README.md", NET_BADGE.format("10.0"))
        self.assertEqual(self.repo(), ["src/GrpcAssertions/README.md: .NET badge names 10.0, "
                                       "the packages target 10.0 | 11.0"])

    def test_core_readme_without_badge_or_requirements_is_fine(self):
        _write(self.dir, "src/GrpcAssertions/README.md", "TUnit 1.83.0 or later, needed by the adapter only.")
        self.assertEqual(self.repo(), [])

    def test_requirements_line_with_another_version_flagged(self):
        issues = self.repo(requirements="**Requirements:** TUnit 1.83.0 or later, .NET 10.")
        self.assertEqual(issues, ["README.md: the requirements line names .NET 10, the packages target .NET 10, 11",
                                  "src/GrpcAssertions.TUnit/README.md: the requirements line names .NET 10, "
                                  "the packages target .NET 10, 11"])

    def test_required_requirements_line_without_net_version_flagged(self):
        issues = self.repo(requirements="**Requirements:** TUnit 1.83.0 or later.")
        self.assertTrue(_matches(issues, "README.md: the requirements line names no .NET version"))
        self.assertEqual(len(issues), 2)

    def test_core_requirements_line_is_checked_when_it_names_a_version(self):
        _write(self.dir, "src/GrpcAssertions/README.md", "Targets .NET 9; the adapter needs TUnit 1.83.0 or later.")
        self.assertTrue(_matches(self.repo(), "src/GrpcAssertions/README.md: the requirements line names .NET 9"))

    def test_missing_readme_is_left_to_the_minimum_check(self):
        self.repo()
        os.remove(os.path.join(self.dir, "README.md"))
        self.assertEqual(fl.lint_frameworks(self.dir, "GrpcAssertions"), [])


class MainTests(_Base):
    def test_conforming_repo_exits_zero(self):
        _write(self.dir, "CHANGELOG.md", VALID)
        self.assertEqual(fl.main(["family_lint.py", self.dir]), 0)

    def test_violation_exits_one(self):
        _write(self.dir, "CHANGELOG.md", VALID)
        _write(self.dir, "README.md", "The colour of the output.")
        self.assertEqual(fl.main(["family_lint.py", self.dir]), 1)

    def test_template_drift_reported_with_the_fix(self):
        _write(self.dir, "src/GrpcAssertions.TUnit/GrpcAssertions.TUnit.csproj", ADAPTER_CSPROJ)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = fl.main(["family_lint.py", self.dir])
        self.assertEqual(code, 1)
        self.assertIn("LICENSE: missing (family template)", out.getvalue())
        self.assertIn("\nUpdate the shared files with: python3 .assertions-ci/scripts/family_sync.py --write",
                      out.getvalue())
        listed = out.getvalue().count("\n  - ")
        self.assertIn(f"FAIL ({listed} issue(s)):", out.getvalue())

    def test_no_drift_adds_no_drift_lines(self):
        _write(self.dir, "src/GrpcAssertions.TUnit/GrpcAssertions.TUnit.csproj", ADAPTER_CSPROJ)
        out = io.StringIO()
        with mock.patch.object(fl.family_sync, "check", return_value=[]), contextlib.redirect_stdout(out):
            fl.main(["family_lint.py", self.dir])
        self.assertNotIn("family_sync.py --write", out.getvalue())

    def test_readme_facts_run_when_an_adapter_exists(self):
        _write(self.dir, "src/GrpcAssertions.TUnit/GrpcAssertions.TUnit.csproj", ADAPTER_CSPROJ)
        _write(self.dir, "src/GrpcAssertions.TUnit/README.md", "no family list")
        self.assertEqual(fl.main(["family_lint.py", self.dir]), 1)



class CoverageEdgeTests(_Base):
    def test_breaking_section_is_allowed_anywhere(self):
        text = VALID.replace("### Added\n- `Thing.New()`", "### BREAKING\n- old API removed.\n### Added\n- `Thing.New()`")
        self.assertEqual(self.changelog(text), [])

    @unittest.skipUnless(shutil.which("git"), "git not available")
    def test_tracked_files_in_a_git_checkout(self):
        _write(self.dir, "tracked.md", "x")
        _write(self.dir, "untracked.md", "x")
        subprocess.run(["git", "init", "-q", self.dir], check=True)
        subprocess.run(["git", "-C", self.dir, "add", "tracked.md"], check=True)
        self.assertEqual(fl._tracked_files(self.dir), ["tracked.md"])

    def test_missing_adapter_readme_reported_once(self):
        _write(self.dir, "src/GrpcAssertions.TUnit/GrpcAssertions.TUnit.csproj", ADAPTER_CSPROJ)
        _write(self.dir, "Directory.Packages.props", PROPS)
        _write(self.dir, "README.md", "TUnit 1.83.0 or later")
        self.assertEqual(fl.lint_readme_facts(self.dir, "GrpcAssertions"),
                         ["src/GrpcAssertions.TUnit/README.md: missing"])

    def test_runs_as_a_program(self):
        _write(self.dir, "CHANGELOG.md", VALID)
        with mock.patch.object(sys, "argv", ["family_lint.py", self.dir]), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            runpy.run_path(fl.__file__, run_name="__main__")
        self.assertEqual(raised.exception.code, 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)

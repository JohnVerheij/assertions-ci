"""Unit tests for xmldoc_check.py. Run with: python -m unittest discover -s scripts -v"""

import contextlib
import io
import os
import runpy
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

import xmldoc_check as xc


def _doc(*members):
    body = "".join(f'<member name="{name}">{inner}</member>' for name, inner in members)
    return f'<?xml version="1.0"?><doc><assembly><name>A</name></assembly><members>{body}</members></doc>'


def _members(*members):
    return xc.members_of({"a.nupkg!lib/net10.0/A.xml": _doc(*members)})


class PackageDocsTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)

    def nupkg(self, name, entries):
        path = os.path.join(self._td.name, name)
        with zipfile.ZipFile(path, "w") as package:
            for entry, text in entries.items():
                package.writestr(entry, text)
        return path

    def test_documentation_next_to_its_assembly_is_read(self):
        path = self.nupkg("a.nupkg", {"lib/net10.0/A.dll": "x", "lib/net10.0/A.xml": "﻿<doc/>",
                                      "lib/net10.0/B.xml": "<doc/>", "build/A.xml": "<doc/>"})
        self.assertEqual(xc.package_docs(path), {f"{path}!lib/net10.0/A.xml": "<doc/>"})

    def test_main_reports_ok(self):
        path = self.nupkg("a.nupkg", {"lib/net10.0/A.dll": "x",
                                      "lib/net10.0/A.xml": _doc(("M:A.F", "<summary>Does F.</summary>"))})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(xc.main(["xmldoc_check.py", path]), 0)
        self.assertIn("OK  1 documented members in 1 documentation file(s)", out.getvalue())

    def test_main_reports_issues_and_caps_the_list(self):
        members = [(f"M:A.F{i}", "") for i in range(xc.MAX_PRINTED + 2)]
        path = self.nupkg("a.nupkg", {"lib/net10.0/A.dll": "x", "lib/net10.0/A.xml": _doc(*members)})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(xc.main(["xmldoc_check.py", path]), 1)
        self.assertIn(f"FAIL ({xc.MAX_PRINTED + 2} issue(s))", out.getvalue())
        self.assertEqual(out.getvalue().count("::error::"), xc.MAX_PRINTED)
        self.assertIn("... and 2 more", out.getvalue())

    def test_main_lists_every_issue_below_the_cap(self):
        path = self.nupkg("a.nupkg", {"lib/net10.0/A.dll": "x", "lib/net10.0/A.xml": _doc(("M:A.F", ""))})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(xc.main(["xmldoc_check.py", path]), 1)
        self.assertEqual(out.getvalue().count("::error::"), 1)
        self.assertNotIn("more", out.getvalue())

    def test_main_fails_without_documentation(self):
        path = self.nupkg("a.nupkg", {"lib/net10.0/A.dll": "x"})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(xc.main(["xmldoc_check.py", path]), 1)
        self.assertIn("::error::No lib/<framework>/<assembly>.xml", out.getvalue())

    def test_main_without_arguments_prints_usage(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(xc.main(["xmldoc_check.py"]), 2)

    def test_runs_as_a_program(self):
        path = self.nupkg("a.nupkg", {"lib/net10.0/A.dll": "x",
                                      "lib/net10.0/A.xml": _doc(("M:A.F", "<summary>Does F.</summary>"))})
        with mock.patch.object(sys, "argv", ["xmldoc_check.py", path]), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            runpy.run_path(xc.__file__, run_name="__main__")
        self.assertEqual(raised.exception.code, 0)


class IssueTests(unittest.TestCase):
    def test_summary_passes(self):
        self.assertEqual(xc.doc_issues(_members(("M:A.F", "<summary>Does <c>F</c>.</summary>"))), [])

    def test_placeholder_summary_flagged(self):
        issues = xc.doc_issues(_members(("M:A.F", "<summary>Generated extension method for F</summary>")))
        self.assertEqual(len(issues), 1)
        self.assertIn("placeholder summary 'Generated extension method for F'", issues[0])

    def test_empty_member_flagged(self):
        issues = xc.doc_issues(_members(("M:A.F", "  ")))
        self.assertEqual(issues, ["a.nupkg!lib/net10.0/A.xml: M:A.F: empty documentation (no text and no <inheritdoc>)"])

    def test_member_with_remarks_only_passes(self):
        self.assertEqual(xc.doc_issues(_members(("M:A.Regex", "<remarks>Pattern: x</remarks>"))), [])

    def test_inheritdoc_without_cref_passes(self):
        self.assertEqual(xc.doc_issues(_members(("M:A.F", "<inheritdoc/>"))), [])

    def test_inheritdoc_to_a_documented_member_passes(self):
        members = _members(("M:A.F", '<inheritdoc cref="M:A.G"/>'), ("M:A.G", "<summary>Does G.</summary>"))
        self.assertEqual(xc.doc_issues(members), [])

    def test_inheritdoc_outside_the_packages_passes(self):
        self.assertEqual(xc.doc_issues(_members(("M:A.F", '<inheritdoc cref="M:TUnit.X"/>'))), [])

    def test_inheritdoc_chain_followed(self):
        members = _members(("M:A.F", '<inheritdoc cref="M:A.G"/>'), ("M:A.G", '<inheritdoc cref="M:A.H"/>'),
                           ("M:A.H", "<summary>Does H.</summary>"))
        self.assertEqual(xc.doc_issues(members), [])

    def test_inheritdoc_to_a_member_that_inherits_without_cref_passes(self):
        members = _members(("M:A.F", '<inheritdoc cref="M:A.G"/>'), ("M:A.G", "<inheritdoc/>"))
        self.assertEqual(xc.doc_issues(members), [])

    def test_inheritdoc_to_a_placeholder_flagged(self):
        members = _members(("M:A.F", '<inheritdoc cref="M:A.G"/>'),
                           ("M:A.G", "<summary>Generated extension method for G</summary>"))
        issues = xc.doc_issues(members)
        self.assertEqual(len(issues), 2)
        self.assertTrue(any('M:A.F: <inheritdoc cref="M:A.G"/> leads to no <summary>' in issue for issue in issues))

    def test_inheritdoc_to_a_member_with_remarks_only_flagged(self):
        members = _members(("M:A.F", '<inheritdoc cref="M:A.G"/>'), ("M:A.G", "<remarks>Only remarks.</remarks>"))
        self.assertEqual(len(xc.doc_issues(members)), 1)

    def test_inheritdoc_cycle_flagged(self):
        members = _members(("M:A.F", '<inheritdoc cref="M:A.G"/>'), ("M:A.G", '<inheritdoc cref="M:A.F"/>'))
        self.assertEqual(len(xc.doc_issues(members)), 2)

    def test_target_documented_in_another_package(self):
        members = xc.members_of({
            "adapter.nupkg!lib/net10.0/A.TUnit.xml": _doc(("M:A.TUnit.F", '<inheritdoc cref="M:A.G"/>')),
            "core.nupkg!lib/net10.0/A.xml": _doc(("M:A.G", "<summary>Does G.</summary>")),
        })
        self.assertEqual(xc.doc_issues(members), [])

    def test_target_resolved_in_the_same_framework(self):
        members = xc.members_of({
            "a.nupkg!lib/net10.0/A.xml": _doc(("M:A.F", '<inheritdoc cref="M:A.G"/>'), ("M:A.G", "")),
            "a.nupkg!lib/net11.0/A.xml": _doc(("M:A.G", "<summary>Does G.</summary>")),
        })
        self.assertEqual(xc.doc_issues(members), [
            'a.nupkg!lib/net10.0/A.xml: M:A.F: <inheritdoc cref="M:A.G"/> leads to no <summary>',
            "a.nupkg!lib/net10.0/A.xml: M:A.G: empty documentation (no text and no <inheritdoc>)"])

    def test_target_in_another_framework_is_used_when_the_own_has_none(self):
        members = xc.members_of({
            "adapter.nupkg!lib/net10.0/A.TUnit.xml": _doc(("M:A.TUnit.F", '<inheritdoc cref="M:A.G"/>')),
            "core.nupkg!lib/netstandard2.0/A.xml": _doc(("M:A.G", "<summary>Does G.</summary>")),
        })
        self.assertEqual(xc.doc_issues(members), [])

    def test_inheritdoc_inside_the_summary_is_followed(self):
        members = _members(("M:A.F", '<summary><inheritdoc cref="M:A.G"/></summary>'), ("M:A.G", "<summary>G.</summary>"))
        self.assertEqual(xc.doc_issues(members), [])
        broken = _members(("M:A.F", '<summary><inheritdoc cref="M:A.G"/></summary>'), ("M:A.G", "<remarks>x</remarks>"))
        self.assertEqual(len(xc.doc_issues(broken)), 1)

    def test_summary_of_only_a_reference_counts(self):
        members = _members(("M:A.F", '<summary><see cref="T:A.B"/></summary>'),
                           ("M:A.G", '<summary><see langword="null"/></summary>'),
                           ("M:A.H", '<inheritdoc cref="M:A.F"/>'))
        self.assertEqual(xc.doc_issues(members), [])

    def test_empty_summary_element_is_empty(self):
        self.assertEqual(len(xc.doc_issues(_members(("M:A.F", "<summary> <para/> </summary>")))), 1)

    def test_target_member_of_a_documented_type_without_an_entry_is_reported(self):
        members = _members(("T:A", "<summary>A.</summary>"), ("M:A.F", '<inheritdoc cref="M:A.Missing(System.Int32)"/>'),
                           ("M:A.G", '<inheritdoc cref="T:A.Unlisted"/>'))
        self.assertEqual(xc.doc_issues(members),
                         ['a.nupkg!lib/net10.0/A.xml: M:A.F: <inheritdoc cref="M:A.Missing(System.Int32)"/> leads to no '
                          '<summary>'])


if __name__ == "__main__":
    unittest.main(verbosity=2)

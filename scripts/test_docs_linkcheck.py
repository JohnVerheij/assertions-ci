#!/usr/bin/env python3
"""Tests for the docs internal-link checker. Stdlib unittest only; run with: python -m unittest discover -s scripts -v"""
import contextlib
import io
import os
import runpy
import sys
import tempfile
import unittest
from unittest import mock

import docs_linkcheck as dl


class _Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.docs = os.path.join(self._td.name, "docs")
        os.makedirs(self.docs)
        self.addCleanup(self._td.cleanup)

    def page(self, name, text=""):
        with open(os.path.join(self.docs, name), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    def check(self):
        return dl.check_docs(self.docs)


class LinkCheckTests(_Base):
    def test_resolving_link_has_no_issues(self):
        self.page("changelog.md")
        self.page("index.md", "[c](changelog.md) and [with anchor](changelog.md#top)")
        self.assertEqual(self.check(), [])

    def test_dead_link_flagged(self):
        self.page("index.md", "[gone](missing.md)")
        self.assertTrue(any("dead internal link 'missing.md'" in x for x in self.check()))

    def test_link_escaping_docs_root_flagged(self):
        self.page("index.md", "[up](../secret.md)")
        self.assertTrue(any("escapes the docs root" in x for x in self.check()))

    def test_external_links_ignored(self):
        self.page("index.md", "[a](https://example/x.md) [b](mailto:x@example.md) [c](//host/x.md)")
        self.assertEqual(self.check(), [])

    def test_anchor_and_non_markdown_ignored(self):
        self.page("index.md", "[a](#section) [b](../src/Foo.cs) [c](image.png)")
        self.assertEqual(self.check(), [])

    def test_image_links_ignored(self):
        # '![alt](target)' is an image embed, not a page link.
        self.page("index.md", "![shield](missing.md)")
        self.assertEqual(self.check(), [])

    def test_reference_style_dead_link_flagged(self):
        self.page("index.md", "See [the changelog][cl].\n\n[cl]: missing.md")
        self.assertTrue(any("dead internal link 'missing.md'" in x for x in self.check()))

    def test_reference_style_resolving_and_external_ignored(self):
        self.page("changelog.md")
        self.page("index.md", "[a][x] [b][y]\n\n[x]: changelog.md\n[y]: https://example/z.md")
        self.assertEqual(self.check(), [])

    def test_nested_page_dead_link_flagged(self):
        # DocFX builds **/*.md, so nested pages must be scanned too.
        os.makedirs(os.path.join(self.docs, "articles"))
        self.page(os.path.join("articles", "guide.md"), "[gone](missing.md)")
        self.assertTrue(any("dead internal link 'missing.md'" in x for x in self.check()))

    def test_nested_page_resolving_link_has_no_issues(self):
        os.makedirs(os.path.join(self.docs, "articles"))
        self.page("changelog.md")
        self.page(os.path.join("articles", "guide.md"), "[c](../changelog.md)")
        self.assertEqual(self.check(), [])



class EdgeCaseTests(_Base):
    def test_angle_bracket_destination_resolves(self):
        self.page("a.md", "[b](<b.md> \"title\")")
        self.page("b.md")
        self.assertEqual(self.check(), [])

    def test_angle_bracket_dead_destination_flagged(self):
        self.page("a.md", "[b](<gone.md>)")
        self.assertEqual(len(self.check()), 1)

    def test_target_on_another_drive_counts_as_escaping(self):
        # os.path.commonpath raises ValueError for paths on different Windows drives.
        with mock.patch.object(dl.os.path, "commonpath", side_effect=ValueError("different drives")):
            self.assertTrue(dl._escapes("C:\\docs", "D:\\other\\x.md"))


class MainTests(_Base):
    def run_main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = dl.main(argv)
        return code, out.getvalue()

    def test_clean_docs_exit_zero(self):
        self.page("a.md", "[b](b.md)")
        self.page("b.md")
        code, out = self.run_main(["docs_linkcheck.py", self.docs])
        self.assertEqual(code, 0)
        self.assertIn("OK  internal doc links resolve", out)

    def test_dead_link_exits_one_and_lists_it(self):
        self.page("a.md", "[b](gone.md)")
        code, out = self.run_main(["docs_linkcheck.py", self.docs])
        self.assertEqual(code, 1)
        self.assertIn("FAIL (1 dead link(s)):", out)

    def test_default_root_is_docs(self):
        cwd = os.getcwd()
        os.chdir(os.path.dirname(self.docs))
        self.addCleanup(os.chdir, cwd)
        code, out = self.run_main(["docs_linkcheck.py"])
        self.assertEqual(code, 0)
        self.assertIn("(docs)", out)

    def test_runs_as_a_program(self):
        with mock.patch.object(sys, "argv", ["docs_linkcheck.py", self.docs]), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            runpy.run_path(dl.__file__, run_name="__main__")
        self.assertEqual(raised.exception.code, 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)

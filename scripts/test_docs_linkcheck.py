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

    def test_angle_bracket_external_links_ignored(self):
        self.page("index.md", "[a](<https://example.com/guide.md>) [b](<//host/x.md>) [c](<#section>)")
        self.assertEqual(self.check(), [])

    def test_angle_bracket_local_link_may_contain_spaces(self):
        self.page("my page.md")
        self.page("index.md", "[ok](<my page.md>) [gone](<no page.md>)")
        self.assertEqual(self.check(), ["index.md: dead internal link 'no page.md'"])

    def test_blank_destination_ignored(self):
        self.page("index.md", "[empty]( )")
        self.assertEqual(self.check(), [])

    def test_links_in_fenced_code_ignored(self):
        self.page("index.md", "```markdown\n[example](missing.md)\n```\n\n~~~~\n[x](gone.md)\n~~~\nstill code\n~~~~\n")
        self.assertEqual(self.check(), [])

    def test_link_after_a_fenced_block_checked(self):
        self.page("index.md", "```\n[example](missing.md)\n```\n[real](dead.md)\n")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'"])

    def test_unclosed_fence_is_reported_and_runs_to_the_end(self):
        self.page("index.md", "[real](dead.md)\n```\n[example](missing.md)\n")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'",
                                        "index.md:2: code block never closed (a closing fence has nothing after it), "
                                        "so the rest of the page renders as code"])

    def test_text_after_a_fence_does_not_close_the_block(self):
        # The Metrics README case: the prose on the fence line kept the block open to the end of the page.
        self.page("index.md", "Intro.\n\n```csharp\nvar a = 1;\n``` More prose.\n\n## Next\n\n[hidden](dead.md)\n")
        self.assertEqual(self.check(), ["index.md:3: code block never closed (a closing fence has nothing after it), "
                                        "so the rest of the page renders as code"])

    def test_a_closing_fence_may_be_longer_and_end_in_spaces(self):
        self.page("index.md", "```\n[example](missing.md)\n`````  \n[real](dead.md)\n")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'"])

    def test_a_closing_fence_in_a_list_item_may_be_indented_more_than_three_spaces(self):
        # The fence starts at the item's content (two spaces); CommonMark measures the closing fence from there.
        self.page("index.md", "- item\n\n  ```text\n  [example](missing.md)\n    ```\n\n[real](dead.md)\n")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'"])

    def test_a_fence_indented_four_spaces_does_not_close(self):
        self.page("index.md", "```\n    ```\n[example](missing.md)\n```\n[real](dead.md)\n")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'"])

    def test_outside_a_list_a_closing_fence_has_at_most_three_spaces(self):
        # Whatever the opening fence's indentation: CommonMark measures both from the page's left edge.
        self.page("index.md", "  ```\n[example](missing.md)\n    ```\n[hidden](dead.md)\n")
        self.assertEqual(self.check(), ["index.md:1: code block never closed (a closing fence has nothing after it), "
                                        "so the rest of the page renders as code"])

    def test_a_paragraph_after_a_fence_on_the_marker_line_stays_in_the_item_and_checked(self):
        # The fence's line keeps its list marker, so the indented paragraph below is not taken for indented code.
        self.page("index.md", "- ```text\n  example\n  ```\n\n    [real](dead.md)\n")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'"])

    def test_a_fenced_block_in_a_nested_list_item_ignored(self):
        self.page("index.md", "- a\n  - b\n\n    ```\n    [example](missing.md)\n      ```\n\n[real](dead.md)\n")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'"])

    def test_triple_backtick_inline_code_at_a_line_start_opens_no_block(self):
        self.page("index.md", "```x``` is inline code.\n[real](dead.md)\n~~~ `fine`\ncode\n~~~\n")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'"])

    def test_backtick_fence_inside_a_tilde_fence_does_not_close_it(self):
        self.page("index.md", "~~~\n```\n[example](missing.md)\n~~~\n")
        self.assertEqual(self.check(), [])

    def test_links_in_inline_code_ignored(self):
        self.page("index.md", "Write `[example](missing.md)` or ``[x](gone.md)`` here; [real](dead.md).")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'"])

    def test_inline_code_does_not_span_paragraphs(self):
        self.page("index.md", "A stray ` backtick.\n\n[real](dead.md) and a ` later.")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'"])

    def test_reference_definition_in_code_ignored(self):
        self.page("index.md", "```\n[cl]: missing.md\n```\n")
        self.assertEqual(self.check(), [])

    def test_indented_code_block_after_a_blank_line_ignored(self):
        self.page("index.md", "Example:\n\n    [x](missing.md)\n\n    [y](gone.md)\n\n[real](dead.md)\n")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'"])

    def test_indented_code_block_at_the_start_and_with_a_tab_ignored(self):
        self.page("index.md", "    [x](missing.md)\n\n\t[y](gone.md)\n")
        self.assertEqual(self.check(), [])

    def test_indented_line_continuing_a_paragraph_checked(self):
        self.page("index.md", "Some text\n    [lazy](dead.md)\n")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'"])

    def test_indented_paragraph_in_a_list_item_checked(self):
        self.page("index.md", "- item\n\n    [continued](dead.md)\n\n1. step\n\n    [next](gone.md)\n")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'", "index.md: dead internal link 'gone.md'"])

    def test_indented_paragraph_in_a_footnote_checked(self):
        self.page("index.md", "[^1]: A note.\n\n    [more](dead.md)\n")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'"])

    def test_list_lasts_through_lazy_and_indented_lines(self):
        self.page("index.md", "- item\nlazy line\n\n  indented\n\n    [continued](dead.md)\n")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'"])

    def test_list_ends_at_an_unindented_line_after_a_blank_line(self):
        self.page("index.md", "- item\n\nParagraph.\n\n    [x](missing.md)\n")
        self.assertEqual(self.check(), [])

    def test_indented_code_block_ends_at_the_next_unindented_line(self):
        self.page("index.md", "\n    [x](missing.md)\n[real](dead.md)\n")
        self.assertEqual(self.check(), ["index.md: dead internal link 'dead.md'"])

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

    def test_a_byte_order_mark_does_not_hide_a_fence_on_the_first_line(self):
        self.page("a.md", chr(0xFEFF) + "```text\n[x](gone.md)\n```\n")
        self.assertEqual(self.check(), [])

    def test_a_form_feed_does_not_split_a_line(self):
        # str.splitlines would end the line at the form feed and leave '  ```' as a fence that never closes.
        self.page("a.md", "text" + chr(0x0C) + "  ```\nmore\n")
        self.assertEqual(self.check(), [])

    def test_a_line_with_only_a_no_break_space_is_not_blank(self):
        # It is paragraph text, so the indented line after it continues the paragraph and its link is checked.
        self.page("a.md", "text\n" + chr(0x00A0) + "\n    see [x](gone.md)\n")
        self.assertEqual(self.check(), ["a.md: dead internal link 'gone.md'"])

    def test_a_line_that_starts_with_a_no_break_space_is_not_indented(self):
        # It ends the list, so the indented line after the next blank line is code.
        self.page("a.md", "- item\n\n" + chr(0x00A0) + "para\n\n    code [x](gone.md)\n")
        self.assertEqual(self.check(), [])


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
        self.assertIn("OK  internal doc links resolve and code blocks close", out)

    def test_dead_link_exits_one_and_lists_it(self):
        self.page("a.md", "[b](gone.md)")
        code, out = self.run_main(["docs_linkcheck.py", self.docs])
        self.assertEqual(code, 1)
        self.assertIn("FAIL (1 issue(s)):", out)
        self.assertIn("  - a.md: dead internal link 'gone.md'", out)

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

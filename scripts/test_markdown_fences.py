#!/usr/bin/env python3
"""Tests for the fenced code block scanner. Stdlib unittest only; run with: python -m unittest discover -s scripts -v"""
import unittest

import markdown_fences as mf


def _blocks(text):
    """The blocks of the text as (start, end, fence, info, closed) tuples."""
    return [tuple(block) for block in mf.blocks(text.split("\n"))]


class TopLevelTests(unittest.TestCase):
    def test_a_block_closes_at_a_fence_with_nothing_after_it(self):
        self.assertEqual(_blocks("```csharp\nvar a = 1;\n``` More text.\n```\nafter"), [(0, 3, "```", "csharp", True)])

    def test_a_closing_fence_may_be_longer_and_end_in_spaces_but_not_shorter_or_other(self):
        self.assertEqual(_blocks("````\n```\n~~~~\n`` ``\n`````  \nafter"), [(0, 4, "````", "", True)])

    def test_a_closing_fence_has_at_most_three_spaces_whatever_the_opening_indentation(self):
        # CommonMark measures both fences from the page's left edge, not the closing fence from the opening one.
        self.assertEqual(_blocks("  ```\ncode\n    ```\nmore"), [(0, 4, "```", "", False)])
        self.assertEqual(_blocks("  ```\ncode\n   ```\nmore"), [(0, 2, "```", "", True)])

    def test_a_fence_indented_four_spaces_is_indented_code(self):
        self.assertEqual(_blocks("    ```\ncode"), [])

    def test_a_tab_counts_as_four_spaces(self):
        self.assertEqual(_blocks("\t```\ncode"), [])

    def test_a_backtick_fence_with_a_backtick_in_its_info_string_is_inline_code(self):
        self.assertEqual(_blocks("```x``` text\n~~~ `fine`\ncode\n~~~"), [(1, 3, "~~~", "`fine`", True)])

    def test_blank_lines_stay_in_the_block(self):
        self.assertEqual(_blocks("~~~\n\ncode\n\n~~~"), [(0, 4, "~~~", "", True)])

    def test_a_thematic_break_is_not_a_list_item(self):
        self.assertEqual(_blocks("- - -\n  ```\ncode\n     ```"), [(1, 4, "```", "", False)])


class ListItemTests(unittest.TestCase):
    def test_a_closing_fence_is_measured_from_the_item_content(self):
        self.assertEqual(_blocks("- item\n\n  ```text\n  example\n    ```\n\nafter"), [(2, 4, "```", "text", True)])

    def test_a_closing_fence_four_spaces_from_the_item_content_is_content(self):
        self.assertEqual(_blocks("- item\n  ```\n  code\n      ```\n  ```"), [(1, 4, "```", "", True)])

    def test_an_ordered_item_and_a_fence_indented_from_its_content(self):
        self.assertEqual(_blocks("1) step\n\n    ```csharp\n    x\n    ```"), [(2, 4, "```", "csharp", True)])

    def test_a_fence_on_the_marker_line(self):
        self.assertEqual(_blocks("- ```cs\n  a\n  ```"), [(0, 2, "```", "cs", True)])

    def test_nested_items_on_one_line(self):
        self.assertEqual(_blocks("- 1. ```\n     x\n     ```"), [(0, 2, "```", "", True)])

    def test_a_fence_four_spaces_into_a_nested_item_is_indented_code(self):
        self.assertEqual(_blocks("- a\n  - b\n\n        ```\n        x"), [])

    def test_a_marker_followed_by_five_spaces_starts_indented_code(self):
        self.assertEqual(_blocks("-     ```\n  x"), [])

    def test_a_line_indented_less_than_the_item_content_ends_the_item_and_the_block(self):
        self.assertEqual(_blocks("- item\n\n  ```\n  code\n```\nafter"),
                         [(2, 4, "```", "", False), (4, 6, "```", "", False)])

    def test_a_lazy_continuation_line_keeps_the_item_open(self):
        # Five spaces close the block only when it is in the item (three from its content).
        self.assertEqual(_blocks("- item\nlazy\n  ```\n  x\n     ```"), [(2, 4, "```", "", True)])

    def test_a_line_after_a_blank_line_ends_the_item(self):
        self.assertEqual(_blocks("- item\n\npara\n  ```\n  x\n     ```"), [(3, 6, "```", "", False)])

    def test_a_heading_ends_the_item_even_after_paragraph_text(self):
        self.assertEqual(_blocks("- item\n# Title\n  ```\n     ```"), [(2, 4, "```", "", False)])

    def test_a_fence_after_paragraph_text_ends_the_item(self):
        self.assertEqual(_blocks("- item\ntext\n```\n     ```"), [(2, 4, "```", "", False)])

    def test_a_line_after_an_empty_item_is_no_lazy_continuation(self):
        self.assertEqual(_blocks("-\ntext\n  ```\n     ```"), [(2, 4, "```", "", False)])

    def test_a_line_after_a_block_is_no_lazy_continuation(self):
        self.assertEqual(_blocks("- item\n  ```\n  ```\ntext\n  ```\n     ```"),
                         [(1, 2, "```", "", True), (4, 6, "```", "", False)])


class ParagraphInterruptionTests(unittest.TestCase):
    def test_an_ordered_item_that_does_not_start_at_one_cannot_interrupt_a_paragraph(self):
        # '2. text' continues the paragraph, so the fence is at the page level and closes at three spaces.
        self.assertEqual(_blocks("Paragraph\n2. text\n   ```text\ncode\n   ```"), [(2, 4, "```", "text", True)])

    def test_an_ordered_item_that_starts_at_one_interrupts_a_paragraph(self):
        self.assertEqual(_blocks("Paragraph\n1. text\n\n   ```\n   x\n      ```"), [(3, 5, "```", "", True)])

    def test_a_bullet_item_interrupts_a_paragraph(self):
        self.assertEqual(_blocks("Paragraph\n- b\n  ```\n  x\n     ```"), [(2, 4, "```", "", True)])

    def test_an_empty_item_cannot_interrupt_a_paragraph(self):
        self.assertEqual(_blocks("Paragraph\n-\n  ```\n  x\n     ```"), [(2, 5, "```", "", False)])

    def test_a_sibling_item_after_paragraph_text_continues_the_list(self):
        self.assertEqual(_blocks("1. a\n2. b\n   ```\n   x\n      ```"), [(2, 4, "```", "", True)])


class IndentedCodeTests(unittest.TestCase):
    def test_a_line_after_indented_code_is_no_lazy_continuation(self):
        self.assertEqual(_blocks("- item\n\n      example\noutside\n  ```text\n  x\n     ```"),
                         [(4, 7, "```", "text", False)])

    def test_a_deeply_indented_paragraph_continuation_stays_lazy(self):
        self.assertEqual(_blocks("- item\ntext\n        deep\nlazy\n  ```\n  x\n     ```"), [(4, 6, "```", "", True)])

    def test_an_item_that_starts_with_indented_code_is_not_continued_lazily(self):
        self.assertEqual(_blocks("-     code\noutside\n  ```\n  x\n     ```"), [(2, 5, "```", "", False)])


class HtmlBlockTests(unittest.TestCase):
    def test_a_fence_inside_an_html_comment_is_not_a_fence(self):
        self.assertEqual(_blocks("<!--\n```\n-->\nafter"), [])

    def test_a_comment_that_ends_on_its_line_is_over_before_the_fence(self):
        self.assertEqual(_blocks("<!-- c -->\n```\nx\n```"), [(1, 3, "```", "", True)])

    def test_blank_lines_stay_inside_a_comment(self):
        self.assertEqual(_blocks("<!--\n\n```\n-->\n```\nx\n```"), [(4, 6, "```", "", True)])

    def test_a_comment_that_never_ends_runs_to_the_end(self):
        self.assertEqual(_blocks("<!--\n```"), [])

    def test_processing_instruction_cdata_and_declaration_end_at_their_markers(self):
        for start, end in (("<?php", "?>"), ("<![CDATA[", "]]>"), ("<!DOCTYPE html", ">")):
            self.assertEqual(_blocks(f"{start}\n```\n{end}\n```\nx\n```"), [(3, 5, "```", "", True)], start)

    def test_a_raw_element_ends_at_its_closing_tag(self):
        self.assertEqual(_blocks("<pre>\n```\n</pre>\n```\nx\n```"), [(3, 5, "```", "", True)])
        self.assertEqual(_blocks("<PRE>x</pre>\n```\ny\n```"), [(1, 3, "```", "", True)])

    def test_a_block_tag_lasts_until_a_blank_line(self):
        self.assertEqual(_blocks("<details>\n```csharp\nx\n```\n</details>"), [])
        self.assertEqual(_blocks("<details>\n\n```csharp\nx\n```\n\n</details>"), [(2, 4, "```", "csharp", True)])

    def test_a_complete_tag_on_its_own_line_starts_a_block_but_cannot_interrupt_a_paragraph(self):
        self.assertEqual(_blocks("<custom-tag a=\"1\">\n```\nx\n```"), [])
        self.assertEqual(_blocks("text\n<custom-tag>\n```\nx\n```"), [(2, 4, "```", "", True)])

    def test_html_indented_four_spaces_in_a_paragraph_is_text(self):
        self.assertEqual(_blocks("text\n    <!--\n```\nx\n```"), [(2, 4, "```", "", True)])

    def test_an_html_block_in_a_list_item_ends_with_the_item(self):
        self.assertEqual(_blocks("- <div>\n  ```\nafter\n```\nx\n```"), [(3, 5, "```", "", True)])
        self.assertEqual(_blocks("- <!--\n  ```\nafter\n```\nx\n```"), [(3, 5, "```", "", True)])


class BlockTests(unittest.TestCase):
    def test_stop_includes_the_closing_fence(self):
        self.assertEqual(mf.Block(0, 2, "```", "", True).stop, 3)
        self.assertEqual(mf.Block(0, 2, "```", "", False).stop, 2)

    def test_unclosed_is_the_last_block_when_it_runs_to_the_end(self):
        lines = "```\na\n```\n```\nb".split("\n")
        self.assertEqual(mf.unclosed(mf.blocks(lines), len(lines)), mf.Block(3, 5, "```", "", False))

    def test_unclosed_is_none_for_closed_blocks_items_that_end_and_no_blocks(self):
        for text in ("```\na\n```", "- x\n  ```\n  a\nafter", "no code"):
            lines = text.split("\n")
            self.assertIsNone(mf.unclosed(mf.blocks(lines), len(lines)), text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

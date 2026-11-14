#!/usr/bin/env python3
"""The fenced code blocks of a Markdown text, found as CommonMark finds them; used by readme_samples.py and
docs_linkcheck.py. A fence is three or more backticks or tildes. It opens a block when it is indented at most three
spaces from the content of its container: the page, or the list item it is in (the item's content starts after the
marker and its spaces). A backtick fence's info string has no backtick, so a line such as '```x``` text' is inline code,
not a block. A block closes at a fence of the same character, at least as long, with nothing after it but spaces and
indented at most three spaces from the same content; a line such as '``` More text.' does not close it. A block in a
list item also ends where the item ends, at a line indented less than the item's content. A block that no fence closes
and no item ends runs to the end of the text, so the rest of the page renders as code.

The containers and blocks around a fence are followed as far as they decide where a fence can be: list items (an
ordered item that does not start at 1, or an empty item, with nothing after its marker but spaces, cannot interrupt a
paragraph, and an empty item ends at a blank line), setext heading underlines, indented code, and HTML blocks, whose
lines are raw HTML (a fence inside an HTML comment, a <pre> element, or a block tag such as <details> before the
blank line that ends it, is not a fence). Block quotes are not followed: a fence after '>' is not found. Where the
CommonMark reference implementations differ, the scanner follows cmark, which GitHub renders Markdown with."""
import re
from typing import NamedTuple

# A list item marker ('-', '+', '*', '1.', '1)') and the spaces after it, or the end of the line (an empty item).
_MARKER = re.compile(r"([-+*]|(\d{1,9})[.)])( +|$)")
# A thematic break ('- - -', '***'), which would otherwise read as list markers.
_BREAK = re.compile(r" {0,3}([-*_])(?: *\1){2,} *$")
# An ATX heading: it ends a paragraph, so a less indented line after it is not a lazy continuation.
_HEADING = re.compile(r" {0,3}#{1,6}(?:[ \t]|$)")
# A setext heading underline: right after paragraph text in the same container, it turns the paragraph into a heading.
_SETEXT = re.compile(r" {0,3}(?:=+|-+) *$")
# A fence and the info string after it.
_FENCE = re.compile(r"(`{3,}|~{3,})(.*)$")

# The starts of the seven kinds of HTML block (CommonMark 4.6). The first five end at a line that contains their end
# marker; a block tag and a complete tag on a line of its own end at a blank line.
_HTML_RAW = re.compile(r"<(?:pre|script|style|textarea)(?:[ \t>]|$)", re.IGNORECASE)
_HTML_RAW_END = re.compile(r"</(?:pre|script|style|textarea)>", re.IGNORECASE)
_BLOCK_TAGS = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|dialog|dir|div|dl|dt|"
    "fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|"
    "menuitem|nav|noframes|ol|optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|"
    "track|ul")
_HTML_BLOCK_TAG = re.compile(rf"</?(?:{_BLOCK_TAGS})(?:[ \t>]|/>|$)", re.IGNORECASE)
_HTML_COMPLETE_TAG = re.compile(
    r"(?:<[A-Za-z][A-Za-z0-9-]*(?:[ \t]+[A-Za-z_:][A-Za-z0-9_.:-]*"
    r"(?:[ \t]*=[ \t]*(?:[^ \t\"'=<>`]+|'[^']*'|\"[^\"]*\"))?)*[ \t]*/?>|</[A-Za-z][A-Za-z0-9-]*[ \t]*>)[ \t]*$")
# The end markers of the HTML blocks that end at a marker, by their start: comment, processing instruction, CDATA, and
# declaration (the last one is checked after CDATA, as both start with '<!').
_HTML_MARKED = (("<!--", "-->"), ("<?", "?>"), ("<![CDATA[", "]]>"))
_HTML_DECLARATION = re.compile(r"<![A-Za-z]")


class Block(NamedTuple):
    """One fenced code block. `start` is the line index of the opening fence; `end` is the index after the last content
    line: the closing fence when `closed`, otherwise the end of the text or the line that ends the list item."""
    start: int
    end: int
    fence: str
    info: str
    closed: bool

    @property
    def stop(self) -> int:
        """The index after the block, its closing fence included."""
        return self.end + 1 if self.closed else self.end


def _expand(line: str) -> 'tuple[str, int]':
    """The line with its tabs expanded to tab stops of four, and its indentation."""
    text = line.expandtabs(4)
    return text, len(text) - len(text.lstrip(" "))


def _open_items(text: str, items: 'list[int]', interrupts_paragraph: bool) -> int:
    """Push the content column of each list item that starts on the line onto `items` (one line may start several, as
    in '- 1. step'); return the column where the line's content starts. The content of an item starts one space after
    the marker when five or more spaces follow it (the rest is indented code) or when nothing but spaces does (an empty
    item). When the first item would interrupt a paragraph (`interrupts_paragraph`), it must not be empty and an ordered
    one must start at 1; otherwise the line is paragraph text."""
    position = items[-1] if items else 0
    first = True
    while True:
        rest = text[position:]
        offset = len(rest) - len(rest.lstrip(" "))
        match = _MARKER.match(rest, offset) if offset <= 3 and not _BREAK.match(rest) else None
        empty = match is not None and not rest[match.end():].strip()
        if match and first and interrupts_paragraph and (
                empty or (match.group(2) is not None and int(match.group(2)) != 1)):
            match = None
        if not match:
            return position
        first = False
        spaces = len(match.group(3))
        position += offset + len(match.group(1)) + (spaces if 1 <= spaces <= 4 and not empty else 1)
        items.append(position)


def _opening(text: str, position: int) -> 'tuple[str, str] | None':
    """The fence and info string when the content at `position` opens a block, or None."""
    rest = text[position:]
    offset = len(rest) - len(rest.lstrip(" "))
    match = _FENCE.match(rest, offset) if offset <= 3 else None
    if not match or (match.group(1)[0] == "`" and "`" in match.group(2)):
        return None
    return match.group(1), match.group(2).strip()


def _html_start(rest: str, interrupts_paragraph: bool) -> 'tuple[str, object] | None':
    """How an HTML block that starts with `rest` ends, or None when `rest` starts no HTML block: ('marker', text or
    pattern) for a block that ends at a line containing the marker (searched from the start line on), or ('blank', None)
    for one that ends at a blank line. A complete tag on a line of its own cannot interrupt a paragraph
    (`interrupts_paragraph`), but it can follow one lazily, as cmark does: '- a' and then '<a>' ends the item."""
    offset = len(rest) - len(rest.lstrip(" "))
    if offset > 3:
        return None
    start = rest[offset:]
    if _HTML_RAW.match(start):
        return "marker", _HTML_RAW_END
    for opener, closer in _HTML_MARKED:
        if start.startswith(opener):
            return "marker", closer
    if _HTML_DECLARATION.match(start):
        return "marker", ">"
    if _HTML_BLOCK_TAG.match(start) or (not interrupts_paragraph and _HTML_COMPLETE_TAG.match(start)):
        return "blank", None
    return None


def _ends_html(line: str, marker: object) -> bool:
    """Whether the line contains the end marker of an HTML block (a text, or the pattern of the raw elements)."""
    return marker.search(line) is not None if isinstance(marker, re.Pattern) else marker in line


def _skip_html(lines: 'list[str]', start: int, end: 'tuple[str, object]', column: int) -> int:
    """The index after the HTML block that starts at `lines[start]`, in a container whose content starts at `column`:
    after the line with its end marker, or at the blank line that ends it, or at the line that ends the list item."""
    kind, marker = end
    if kind == "marker" and _ends_html(lines[start][1:], marker):
        return start + 1
    for index in range(start + 1, len(lines)):
        text, indent = _expand(lines[index])
        if not text.strip():
            if kind == "blank":
                return index
            continue
        if indent < column:
            return index
        if kind == "marker" and _ends_html(text, marker):
            return index + 1
    return len(lines)


def _block(lines: 'list[str]', start: int, opening: 'tuple[str, str]', column: int) -> Block:
    """The block that opens at `lines[start]`, in a container whose content starts at `column`."""
    fence, info = opening
    for index in range(start + 1, len(lines)):
        text, indent = _expand(lines[index])
        stripped = text.strip()
        if not stripped:
            continue
        if indent < column:
            return Block(start, index, fence, info, False)
        if indent - column <= 3 and set(stripped) == {fence[0]} and len(stripped) >= len(fence):
            return Block(start, index, fence, info, True)
    return Block(start, len(lines), fence, info, False)


def blocks(lines: 'list[str]') -> 'list[Block]':
    """Every fenced code block of the lines, in order. A less indented line right after paragraph text continues the
    paragraph (a lazy continuation line), so it keeps the list item open; any other line indented less than an item's
    content ends the item, and so does a blank line right after an empty item. A setext heading underline ends the
    paragraph it follows; it is never a lazy continuation line. A line indented four or more spaces from its container's
    content after anything but paragraph text is indented code, which no line continues lazily. HTML blocks are skipped
    as raw HTML."""
    found: list[Block] = []
    items: list[int] = []
    lazy = False
    # Whether the innermost item started on the line before and has no content yet.
    empty_item = False
    index = 0
    while index < len(lines):
        text, indent = _expand(lines[index])
        if not text.strip():
            if empty_item:
                items = items[:-1]
                empty_item = False
            lazy = False
            index += 1
            continue
        empty_item = False
        reached = [column for column in items if column <= indent]
        depth = len(reached)
        # A marker inside the innermost open item (nothing closed by its indentation) would start a new list there.
        in_paragraph = lazy and depth == len(items)
        position = _open_items(text, reached, interrupts_paragraph=in_paragraph)
        rest = text[position:]
        started = len(reached) > depth
        offset = len(rest) - len(rest.lstrip(" "))
        if rest.strip() and offset >= 4 and (started or not lazy):
            # Indented code: not a fence, not HTML, and not paragraph text that the next line could continue.
            items = reached
            lazy = False
            index += 1
            continue
        # Whether the content would interrupt the paragraph in its own container, not follow it lazily or start an item.
        interrupts = in_paragraph and not started
        opening = _opening(text, position)
        html = None if opening else _html_start(rest, interrupts)
        setext = interrupts and _SETEXT.match(rest)
        other_block = opening is not None or html is not None or bool(
            _BREAK.match(rest) or _HEADING.match(rest) or setext)
        if started or other_block or not lazy:
            items = reached
        column = items[-1] if items else 0
        if opening:
            block = _block(lines, index, opening, column)
            found.append(block)
            lazy = False
            index = block.stop
            continue
        if html:
            lazy = False
            index = _skip_html(lines, index, html, column)
            continue
        # Paragraph text, which the next line may continue lazily; a heading, a break or an empty item is not.
        lazy = not other_block and bool(rest.strip())
        empty_item = started and not rest.strip()
        index += 1
    return found


def unclosed(found: 'list[Block]', length: int) -> 'Block | None':
    """The block that no fence closes and that runs to the end of a text of `length` lines (only the last block can),
    or None."""
    return found[-1] if found and not found[-1].closed and found[-1].end == length else None

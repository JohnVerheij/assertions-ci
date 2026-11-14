#!/usr/bin/env python3
"""The fenced code blocks of a Markdown text, found as CommonMark finds them; used by readme_samples.py and
docs_linkcheck.py. A fence is three or more backticks or tildes. It opens a block when it is indented at most three
spaces from the content of its container: the page, or the list item it is in (the item's content starts after the
marker and its spaces). A backtick fence's info string has no backtick, so a line such as '```x``` text' is inline code,
not a block. A block closes at a fence of the same character, at least as long, with nothing after it but spaces and
indented at most three spaces from the same content; a line such as '``` More text.' does not close it. A block in a
list item also ends where the item ends, at a line indented less than the item's content. A block that no fence closes
and no item ends runs to the end of the text, so the rest of the page renders as code. Block quotes are not followed: a
fence after '>' is not found."""
import re
from typing import NamedTuple

# A list item marker ('-', '+', '*', '1.', '1)') and the spaces after it, or the end of the line (an empty item).
_MARKER = re.compile(r"([-+*]|\d{1,9}[.)])( +|$)")
# A thematic break ('- - -', '***'), which would otherwise read as list markers.
_BREAK = re.compile(r" {0,3}([-*_])(?: *\1){2,} *$")
# An ATX heading: it ends a paragraph, so a less indented line after it is not a lazy continuation.
_HEADING = re.compile(r" {0,3}#{1,6}(?:[ \t]|$)")
# A fence and the info string after it.
_FENCE = re.compile(r"(`{3,}|~{3,})(.*)$")


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


def _open_items(text: str, items: 'list[int]') -> int:
    """Push the content column of each list item that starts on the line onto `items` (one line may start several, as
    in '- 1. step'); return the column where the line's content starts. A marker followed by five or more spaces starts
    an item whose content is one space after the marker (the rest is indented code)."""
    position = items[-1] if items else 0
    while True:
        rest = text[position:]
        offset = len(rest) - len(rest.lstrip(" "))
        match = _MARKER.match(rest, offset) if offset <= 3 and not _BREAK.match(rest) else None
        if not match:
            return position
        spaces = len(match.group(2))
        position += offset + len(match.group(1)) + (spaces if 1 <= spaces <= 4 else 1)
        items.append(position)


def _opening(text: str, position: int) -> 'tuple[str, str] | None':
    """The fence and info string when the content at `position` opens a block, or None."""
    rest = text[position:]
    offset = len(rest) - len(rest.lstrip(" "))
    match = _FENCE.match(rest, offset) if offset <= 3 else None
    if not match or (match.group(1)[0] == "`" and "`" in match.group(2)):
        return None
    return match.group(1), match.group(2).strip()


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
    content ends the item."""
    found: list[Block] = []
    items: list[int] = []
    lazy = False
    index = 0
    while index < len(lines):
        text, indent = _expand(lines[index])
        if not text.strip():
            lazy = False
            index += 1
            continue
        reached = [column for column in items if column <= indent]
        depth = len(reached)
        position = _open_items(text, reached)
        rest = text[position:]
        opening = _opening(text, position)
        other_block = opening is not None or bool(_BREAK.match(rest) or _HEADING.match(rest))
        if len(reached) > depth or other_block or not lazy:
            items = reached
        if opening:
            block = _block(lines, index, opening, items[-1] if items else 0)
            found.append(block)
            lazy = False
            index = block.stop
            continue
        # Paragraph text, which the next line may continue lazily; a heading, a break or an empty item is not.
        lazy = not other_block and bool(rest.strip())
        index += 1
    return found


def unclosed(found: 'list[Block]', length: int) -> 'Block | None':
    """The block that no fence closes and that runs to the end of a text of `length` lines (only the last block can),
    or None."""
    return found[-1] if found and not found[-1].closed and found[-1].end == length else None

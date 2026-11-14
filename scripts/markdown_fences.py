#!/usr/bin/env python3
"""The fenced code blocks of a Markdown text, found as CommonMark finds them, and what each line is; used by
readme_samples.py and docs_linkcheck.py. A fence is three or more backticks or tildes. It opens a block when it is
indented at most three spaces from the content of its container: the page, a list item (its content starts after the
marker and its spaces) or a block quote (after the '>' and one space). A backtick fence's info string has no backtick,
so a line such as '```x``` text' is inline code, not a block. A block closes at a fence of the same character, at least
as long, with nothing after it but spaces and indented at most three spaces from the same content; a line such as
'``` More text.' does not close it. A block also ends where its container ends: a list item at a line indented less
than its content, a block quote at a line without its '>'. A block that no fence closes and no container ends runs to
the end of the text, so the rest of the page renders as code.

The containers and blocks around a fence are followed as far as they decide where a fence can be: list items (an
ordered item that does not start at 1, or an empty item, with nothing after its marker but spaces, cannot interrupt a
paragraph, and an empty item ends at a blank line), block quotes, setext heading underlines, indented code, and HTML
blocks, whose lines are raw HTML (a fence inside an HTML comment, a <pre> element, or a block tag such as <details>
before the blank line that ends it, is not a fence). Footnote definitions, an extension of GitHub and DocFX, are not
followed. Where the CommonMark reference implementations differ, the scanner follows cmark, which GitHub renders
Markdown with.

Whitespace is spaces and tabs only, as in CommonMark: a line with a no-break space is not blank, and a no-break space
after a fence keeps it from closing a block."""
import re
from typing import NamedTuple

# The line endings of CommonMark; str.splitlines also breaks at form feeds and Unicode line separators.
_LINE_END = re.compile(r"\r\n|\r|\n")
# A list item marker ('-', '+', '*', '1.', '1)') and the spaces after it, or the end of the line (an empty item).
_MARKER = re.compile(r"([-+*]|(\d{1,9})[.)])( +|$)")
# A thematic break ('- - -', '***'), which would otherwise read as list markers.
_BREAK = re.compile(r" {0,3}([-*_])(?: *\1){2,} *$")
# An ATX heading: it ends a paragraph, so a less indented line after it is not a lazy continuation.
_HEADING = re.compile(r" {0,3}#{1,6}(?:[ \t]|$)")
# A setext heading underline: right after paragraph text in the same container, it turns the paragraph into a heading.
_SETEXT = re.compile(r" {0,3}(?:=+|-+) *$")
# A link reference definition on one line ('[label]: destination "title"'): a paragraph of nothing but these is no
# paragraph for a setext underline, which then stays paragraph text, as in cmark.
_DEFINITION = re.compile(r" {0,3}\[[^\]]*[^\]\s][^\]]*\]: *\S+(?: +(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))? *$")
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


# What a line is, as scan() reports it.
BLANK = "blank"
FENCE = "fence"
CODE = "code"
HTML_START = "html start"
HTML = "html"
TEXT = "text"
CONTINUED = "continued"


class Block(NamedTuple):
    """One fenced code block. `start` is the line index of the opening fence; `end` is the index after the last content
    line: the closing fence when `closed`, otherwise the end of the text or the line that ends its container. `quoted`
    when it is inside a block quote."""
    start: int
    end: int
    fence: str
    info: str
    closed: bool
    quoted: bool = False

    @property
    def stop(self) -> int:
        """The index after the block, its closing fence included."""
        return self.end + 1 if self.closed else self.end


class Scan(NamedTuple):
    """The fenced code blocks of a text and what each of its lines is: BLANK; FENCE, a line of a fenced code block, its
    fences included; CODE, indented code; HTML_START and HTML, the first and the further lines of an HTML block; TEXT, a
    line that starts a paragraph, a heading or another block with inline content; or CONTINUED, a line that continues
    the paragraph of the line before."""
    blocks: 'list[Block]'
    kinds: 'list[str]'


def lines_of(text: str) -> 'list[str]':
    """The lines of a Markdown text as CommonMark reads them: without a leading byte order mark, and ended by a line
    feed, a carriage return or both; a line ending at the end of the text starts no further line."""
    lines = _LINE_END.split(text.removeprefix(chr(0xFEFF)))
    if lines[-1] == "":
        lines.pop()
    return lines


def _expand(line: str) -> str:
    """The line with its tabs expanded to tab stops of four."""
    return line.expandtabs(4)


def _spaces(text: str, position: int) -> int:
    """The number of spaces at `position`."""
    rest = text[position:]
    return len(rest) - len(rest.lstrip(" "))


def _quote_marker(text: str, position: int) -> 'int | None':
    """The column after the block quote marker at `position` ('>' indented at most three spaces, and the space after
    it), or None."""
    offset = _spaces(text, position)
    if offset > 3 or text[position + offset:position + offset + 1] != ">":
        return None
    position += offset + 1
    return position + 1 if text[position:position + 1] == " " else position


def _match(text: str, containers: 'list[int | None]') -> 'tuple[int, int]':
    """How many of the open containers, outermost first, the line continues, and the column where its content starts
    after them. A block quote (None) continues at its marker; a list item (the width of its marker and the spaces after
    it) continues at a line indented that far from where its container's content starts on the line, or blank there."""
    position = 0
    for count, width in enumerate(containers):
        if width is None:
            after = _quote_marker(text, position)
            if after is None:
                return count, position
            position = after
        elif text[position:].strip(" "):
            if _spaces(text, position) < width:
                return count, position
            position += width
    return len(containers), position


def _open_containers(text: str, position: int, containers: 'list[int | None]', interrupts_paragraph: bool) -> int:
    """Push each block quote (None) and list item (the width of its marker and the spaces after it) that starts on the
    line at `position` onto `containers` (one line may start several, as in '> - 1. step'); return the column where the
    line's content starts. The content of an item starts one space after the marker when five or more spaces follow it
    (the rest is indented code) or when nothing but spaces does (an empty item). When the first item would interrupt a
    paragraph (`interrupts_paragraph`), it must not be empty and an ordered one must start at 1; otherwise the line is
    paragraph text. A block quote may interrupt a paragraph."""
    first = True
    while True:
        after = _quote_marker(text, position)
        if after is not None:
            containers.append(None)
            position = after
            first = False
            continue
        rest = text[position:]
        offset = _spaces(text, position)
        match = _MARKER.match(rest, offset) if offset <= 3 and not _BREAK.match(rest) else None
        empty = match is not None and not rest[match.end():].strip(" ")
        if match and first and interrupts_paragraph and (
                empty or (match.group(2) is not None and int(match.group(2)) != 1)):
            match = None
        if not match:
            return position
        first = False
        spaces = len(match.group(3))
        width = offset + len(match.group(1)) + (spaces if 1 <= spaces <= 4 and not empty else 1)
        position += width
        containers.append(width)


def _opening(text: str, position: int) -> 'tuple[str, str] | None':
    """The fence and info string when the content at `position` opens a block, or None."""
    rest = text[position:]
    offset = len(rest) - len(rest.lstrip(" "))
    match = _FENCE.match(rest, offset) if offset <= 3 else None
    if not match or (match.group(1)[0] == "`" and "`" in match.group(2)):
        return None
    return match.group(1), match.group(2).strip(" ")


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


def _skip_html(lines: 'list[str]', start: int, end: 'tuple[str, object]', containers: 'list[int | None]',
               position: int) -> int:
    """The index after the HTML block that starts at column `position` of `lines[start]` inside `containers`: after the
    line with its end marker, at the blank line that ends it, or at the line that does not continue its containers. The
    end marker is looked for after the containers' markers, so the '>' of a block quote ends no declaration."""
    kind, marker = end
    if kind == "marker" and _ends_html(_expand(lines[start])[position + 1:], marker):
        return start + 1
    for index in range(start + 1, len(lines)):
        text = _expand(lines[index])
        depth, position = _match(text, containers)
        if depth < len(containers):
            return index
        rest = text[position:]
        if not rest.strip(" "):
            if kind == "blank":
                return index
            continue
        if kind == "marker" and _ends_html(rest, marker):
            return index + 1
    return len(lines)


def _block(lines: 'list[str]', start: int, opening: 'tuple[str, str]', containers: 'list[int | None]') -> Block:
    """The block that opens at `lines[start]` inside `containers`."""
    fence, info = opening
    quoted = None in containers
    for index in range(start + 1, len(lines)):
        text = _expand(lines[index])
        depth, position = _match(text, containers)
        if depth < len(containers):
            return Block(start, index, fence, info, False, quoted)
        stripped = text[position:].strip(" ")
        if stripped and _spaces(text, position) <= 3 and set(stripped) == {fence[0]} and len(stripped) >= len(fence):
            return Block(start, index, fence, info, True, quoted)
    return Block(start, len(lines), fence, info, False, quoted)


def blocks(lines: 'list[str]') -> 'list[Block]':
    """Every fenced code block of the lines, in order (see scan)."""
    return scan(lines).blocks


def scan(lines: 'list[str]') -> Scan:
    """The fenced code blocks of the lines, in order, and what each line is. A line continues the open containers it
    matches (list items and block quotes, outermost first). A line right after paragraph text that matches fewer of them
    continues the paragraph (a lazy continuation line), so it keeps them all open; any other line ends each container
    it does not match, and so does a blank line, which has no '>' for a block quote, and a blank line right after an
    empty item. A setext heading underline ends the paragraph it follows; it is never a lazy continuation line. A line
    indented four or more spaces from its container's content after anything but paragraph text is indented code, which
    no line continues lazily. HTML blocks are skipped as raw HTML."""
    found: list[Block] = []
    kinds = [BLANK] * len(lines)
    containers: 'list[int | None]' = []
    lazy = False
    # Whether the open paragraph consists of link reference definitions only.
    definitions = False
    # Whether the innermost container is a list item that started on the line before and has no content yet.
    empty_item = False
    index = 0
    while index < len(lines):
        text = _expand(lines[index])
        depth, position = _match(text, containers)
        if not text[position:].strip(" "):
            containers = containers[:depth - 1 if empty_item and depth == len(containers) else depth]
            empty_item = False
            lazy = False
            index += 1
            continue
        empty_item = False
        reached = containers[:depth]
        # A marker inside the innermost open container (all of them continued) would start a new list there.
        in_paragraph = lazy and depth == len(containers)
        position = _open_containers(text, position, reached, interrupts_paragraph=in_paragraph)
        rest = text[position:]
        started = len(reached) > depth
        if rest.strip(" ") and _spaces(text, position) >= 4 and (started or not lazy):
            # Indented code: not a fence, not HTML, and not paragraph text that the next line could continue.
            kinds[index] = CODE
            containers = reached
            lazy = False
            index += 1
            continue
        # Whether the content would interrupt the paragraph in its own container, not follow it lazily or start an item.
        interrupts = in_paragraph and not started
        opening = _opening(text, position)
        html = None if opening else _html_start(rest, interrupts)
        setext = interrupts and not definitions and _SETEXT.match(rest)
        other_block = opening is not None or html is not None or bool(
            _BREAK.match(rest) or _HEADING.match(rest) or setext)
        if started or other_block or not lazy:
            containers = reached
        if opening:
            block = _block(lines, index, opening, containers)
            found.append(block)
            kinds[block.start:block.stop] = [FENCE] * (block.stop - block.start)
            lazy = False
            index = block.stop
            continue
        if html:
            end = _skip_html(lines, index, html, containers, position)
            kinds[index:end] = [HTML_START] + [HTML] * (end - index - 1)
            lazy = False
            index = end
            continue
        # Paragraph text, which the next line may continue lazily; a heading, a break or an empty item is not.
        kinds[index] = CONTINUED if lazy and not started and not other_block else TEXT
        definitions = (kinds[index] == TEXT or definitions) and bool(_DEFINITION.match(rest))
        lazy = not other_block and bool(rest.strip(" "))
        empty_item = started and not rest.strip(" ") and reached[-1] is not None
        index += 1
    return Scan(found, kinds)


def unclosed(found: 'list[Block]') -> 'Block | None':
    """The first block that no fence closes, or None. When it runs to the end of the text, the rest of the page renders
    as code; when it ends with its list item or block quote, the rest of that container does."""
    return next((block for block in found if not block.closed), None)

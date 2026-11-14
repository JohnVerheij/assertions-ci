#!/usr/bin/env python3
"""Offline internal-link check for the generated docs sources (CI-safe: no
network). Run after the docs/*.md files are copied and their cross-file links
rewritten, before `dotnet docfx`. Fails if any inline Markdown link to a local
Markdown page (a target ending in '.md') does not resolve to an existing file
inside the docs root, or escapes it. External links (http/https/mailto/...),
bare '#anchor' links, and links to non-Markdown repo files are intentionally
not checked, so the gate stays deterministic and offline. Links shown as code
or raw HTML are not links and are not checked: fenced and indented code blocks
and HTML blocks (such as a commented-out link), found as CommonMark finds them
by markdown_fences.py, and inline code and HTML comments within a paragraph.
Footnotes are the exception: an indented line in a footnote definition stays
checked, as it may continue the note, so a real link is never hidden. A fenced
code block that no fence closes is reported too: the rest of the page would
render as code (a fence line with text after it, such as '``` More text.', does
not close a block). Exit 1 on any issue."""
import glob
import os
import re
import string
import sys

import markdown_fences

# Inline '[text](target)' links; the leading (?<!!) skips '![image](...)'.
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
# Reference-style definitions: a line '[label]: destination "optional title"'.
_REFDEF = re.compile(r"^ {0,3}\[[^\]]+\]:\s*(\S+)", re.MULTILINE)
_EXTERNAL = ("http://", "https://", "mailto:", "tel:", "ftp://", "//")
# A run of backticks, which opens or closes an inline code span.
_BACKTICKS = re.compile(r"`+")
# The kinds of line (from markdown_fences.scan) that show code or raw HTML.
_CODE_KINDS = (markdown_fences.FENCE, markdown_fences.HTML_START, markdown_fences.HTML)
# The start of a footnote definition ('[^label]:'), which markdown_fences does not follow.
_FOOTNOTE = re.compile(r" {0,3}\[\^[^\]]+\]:")


def _without_code_lines(lines, kinds):
    """The lines with fenced code, HTML blocks and indented code (`kinds`, from markdown_fences.scan) blanked out. An
    indented line inside a footnote definition stays: markdown_fences does not follow footnotes, and there such a line
    can continue the note after a blank line, so it is checked rather than hidden. A footnote lasts until a line with
    no indentation follows a blank line."""
    out = []
    in_footnote = False
    previous_blank = True
    for line, kind in zip(lines, kinds):
        blank = not line.strip(" \t")
        if kind == markdown_fences.TEXT and _FOOTNOTE.match(line):
            in_footnote = True
        elif not blank and previous_blank and not line.startswith((" ", "\t")):
            in_footnote = False
        out.append("" if kind in _CODE_KINDS or (kind == markdown_fences.CODE and not in_footnote) else line)
        previous_blank = blank
    return out


def _closing_run(text, start, length):
    """The index of the first run of exactly `length` backticks from `start` on, or None."""
    for match in _BACKTICKS.finditer(text, start):
        if len(match.group()) == length:
            return match.start()
    return None


def _comment_end(text, start):
    """The index after the inline HTML comment that starts at `start`, or None. Only a comment that both CommonMark
    0.29 (cmark, GitHub) and 0.31 (DocFX) accept counts: its text does not start with '>' or '->', does not end with
    '-' and has no '--', so a link that either renderer shows is never taken for a comment."""
    end = text.find("-->", start + 4)
    body = text[start + 4:end]
    if end < 0 or body.startswith((">", "->")) or body.endswith("-") or "--" in body:
        return None
    return end + 3


def _without_code_spans_and_comments(text):
    """The text of one paragraph with its inline code spans and HTML comments removed, found as CommonMark finds them,
    from left to right: a run of backticks opens a span that the next run of the same length closes, a run with no
    such partner is text, and a backslash before a punctuation character escapes it, so an escaped backtick opens
    nothing."""
    out = []
    index = 0
    while index < len(text):
        end = _comment_end(text, index) if text.startswith("<!--", index) else None
        if end is not None:
            index = end
        elif text[index] == "\\" and index + 1 < len(text) and text[index + 1] in string.punctuation:
            out.append(text[index:index + 2])
            index += 2
        elif text[index] == "`":
            length = _BACKTICKS.match(text, index).end() - index
            close = _closing_run(text, index + length, length)
            if close is None:
                out.append(text[index:index + length])
                index += length
            else:
                index = close + length
        else:
            out.append(text[index])
            index += 1
    return "".join(out)


def _prose(lines, kinds):
    """The prose of a page, one text per paragraph (or other block with inline content) with its inline code spans and
    HTML comments removed; code and HTML blocks (`kinds`, from markdown_fences.scan) are left out. Line breaks are kept,
    so reference definitions still start a line."""
    paragraphs = []
    joined = False
    for line, kind in zip(_without_code_lines(lines, kinds), kinds):
        if not line.strip(" \t"):
            joined = False
            continue
        if joined and kind == markdown_fences.CONTINUED:
            paragraphs[-1].append(line)
        else:
            paragraphs.append([line])
        joined = True
    return [_without_code_spans_and_comments("\n".join(paragraph)) for paragraph in paragraphs]


def _target(dest):
    """Extract the path portion of a link destination: drop <> (an angle-bracket
    destination may contain spaces), a trailing "title", and any #anchor /
    ?query."""
    dest = dest.strip()
    if dest.startswith("<") and ">" in dest:
        dest = dest[1:dest.index(">")]
    else:
        parts = dest.split()
        dest = parts[0] if parts else ""
    return dest.split("#", 1)[0].split("?", 1)[0]


def _escapes(root_abs, target):
    try:
        return os.path.commonpath([root_abs, target]) != root_abs
    except ValueError:  # different drive on Windows
        return True


def _validate(dest, base, root_abs, name, issues):
    """Check one link destination; append an issue if it names a local Markdown
    page that is missing or escapes the docs root. Non-Markdown, external, and
    bare-anchor destinations are skipped, also inside <>."""
    frag = _target(dest)
    if not frag or frag.lower().startswith(_EXTERNAL) or not frag.lower().endswith(".md"):
        return
    target = os.path.normpath(os.path.join(base, frag))
    if _escapes(root_abs, target):
        issues.append(f"{name}: link '{frag}' escapes the docs root")
    elif not os.path.isfile(target):
        issues.append(f"{name}: dead internal link '{frag}'")


def check_docs(root):
    root_abs = os.path.abspath(root)
    issues = []
    # Recursive to match DocFX's build.content pattern (**/*.md); nested pages
    # would otherwise publish unchecked.
    for path in sorted(glob.glob(os.path.join(root, "**", "*.md"), recursive=True)):
        with open(path, encoding="utf-8", newline="") as f:
            lines = markdown_fences.lines_of(f.read())
        scan = markdown_fences.scan(lines)
        base = os.path.dirname(os.path.abspath(path))
        name = os.path.relpath(path, root).replace(os.sep, "/")
        for paragraph in _prose(lines, scan.kinds):
            for m in _LINK.finditer(paragraph):
                _validate(m.group(1), base, root_abs, name, issues)
            for m in _REFDEF.finditer(paragraph):
                _validate(m.group(1), base, root_abs, name, issues)
        unclosed = markdown_fences.unclosed(scan.blocks, len(lines))
        if unclosed:
            issues.append(f"{name}:{unclosed.start + 1}: code block never closed (a closing fence has nothing after "
                          "it), so the rest of the page renders as code")
    return issues


def main(argv: list[str]) -> int:
    root = argv[1] if len(argv) > 1 else "docs"
    found = check_docs(root)
    if found:
        print(f"FAIL ({len(found)} issue(s)):")
        for x in found:
            print("  - " + x)
        return 1
    print(f"OK  internal doc links resolve and code blocks close ({root})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

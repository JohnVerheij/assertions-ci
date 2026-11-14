#!/usr/bin/env python3
"""Offline internal-link check for the generated docs sources (CI-safe: no
network). Run after the docs/*.md files are copied and their cross-file links
rewritten, before `dotnet docfx`. Fails if any inline Markdown link to a local
Markdown page (a target ending in '.md') does not resolve to an existing file
inside the docs root, or escapes it. External links (http/https/mailto/...),
bare '#anchor' links, and links to non-Markdown repo files are intentionally
not checked, so the gate stays deterministic and offline. Links shown as code
are not links and are not checked: fenced code blocks, inline code, and
indented code blocks outside lists and footnotes. Inside a list item or a
footnote an indented line can be a continuation paragraph, so it stays checked:
a code block there may show as a dead link, which fails loudly, but a real link
is never hidden. A fenced code block that no fence closes is reported too: the
rest of the page would render as code (a fence line with text after it, such as
'``` More text.', does not close a block). Exit 1 on any issue."""
import glob
import os
import re
import sys

# Inline '[text](target)' links; the leading (?<!!) skips '![image](...)'.
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
# Reference-style definitions: a line '[label]: destination "optional title"'.
_REFDEF = re.compile(r"^ {0,3}\[[^\]]+\]:\s*(\S+)", re.MULTILINE)
_EXTERNAL = ("http://", "https://", "mailto:", "tel:", "ftp://", "//")
# The opening or closing fence of a fenced code block: three or more backticks or tildes, indented up to three spaces.
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
# An inline code span: a run of backticks, then the code (within one paragraph), then a run of the same length.
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)((?:(?!\n[ \t]*\n).)+?)(?<!`)\1(?!`)", re.DOTALL)
# The start of a list item ('-', '+', '*', '1.', '1)') or of a footnote definition ('[^label]:').
_CONTAINER = re.compile(r"^ {0,3}(?:(?:[-+*]|\d{1,9}[.)])(?:[ \t]|$)|\[\^[^\]]+\]:)")


def _indent(line):
    """The number of leading spaces."""
    return len(line) - len(line.lstrip(" "))


def _opening(line):
    """The fence and its indentation when the line opens a fenced code block, or None. A backtick fence's info string
    has no backtick: a line such as '```x``` text' is inline code, not a block."""
    match = _FENCE.match(line)
    if not match or (match.group(1)[0] == "`" and "`" in line[match.end():]):
        return None
    return match.group(1), _indent(line)


def _closes(line, opening):
    """Whether the line closes a block opened with `opening` (its fence and indentation): a fence of the same
    character, at least as long, with nothing after it but spaces, and indented at most three spaces more than the
    opening fence. CommonMark measures that indentation from the list item's content, where a fence in a list item
    starts. A line such as '``` More text.' does not close the block."""
    fence, indent = opening
    stripped = line.strip()
    return _indent(line) <= indent + 3 and set(stripped) == {fence[0]} and len(stripped) >= len(fence)


def _blank_fenced_blocks(lines):
    """The lines with every fenced code block blanked out. A fence closes at a fence of the same character that is at
    least as long, or at the end of the text."""
    out = []
    opening = None
    for line in lines:
        if opening is None:
            opening = _opening(line)
            if opening:
                line = ""
        else:
            if _closes(line, opening):
                opening = None
            line = ""
        out.append(line)
    return out


def _unclosed_fence(lines):
    """The line number of an opening fence that no fence closes, or None. CommonMark runs such a block to the end of the
    page; in these docs that is always a missing or broken closing fence, and everything after it renders as code."""
    opening = opened = None
    for number, line in enumerate(lines, 1):
        if opening is None:
            opening, opened = _opening(line), number
        elif _closes(line, opening):
            opening = None
    return opened if opening else None


def _is_indented(line):
    """Whether the line starts with four or more columns of indentation (a tab counts as four)."""
    expanded = line.expandtabs(4)
    return len(expanded) - len(expanded.lstrip(" ")) >= 4


def _blank_indented_blocks(lines):
    """The lines with every indented code block outside lists and footnotes blanked out. Such a block starts with an
    indented line after a blank line (or at the start of the text) and runs, blank lines included, to the next line
    that is not indented. A list or footnote lasts until a line with no indentation follows a blank line; until then an
    indented line may continue it, so it is kept."""
    out = []
    in_container = False
    in_code = False
    previous_blank = True
    for line in lines:
        blank = not line.strip()
        if in_code and (blank or _is_indented(line)):
            out.append("")
            previous_blank = blank
            continue
        in_code = False
        if not blank:
            if _is_indented(line) and previous_blank and not in_container:
                in_code = True
                line = ""
            elif _CONTAINER.match(line):
                in_container = True
            elif previous_blank and not line[:1].isspace():
                in_container = False
        out.append(line)
        previous_blank = blank
    return out


def _prose(text):
    """The text with its code blanked out: fenced and indented code blocks and inline code spans. Line breaks are
    kept, so reference definitions still start a line."""
    lines = _blank_indented_blocks(_blank_fenced_blocks(text.splitlines()))
    return _CODE_SPAN.sub("", "\n".join(lines))


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
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        text = _prose(raw)
        base = os.path.dirname(os.path.abspath(path))
        name = os.path.relpath(path, root).replace(os.sep, "/")
        for m in _LINK.finditer(text):
            _validate(m.group(1), base, root_abs, name, issues)
        for m in _REFDEF.finditer(text):
            _validate(m.group(1), base, root_abs, name, issues)
        opened = _unclosed_fence(raw.splitlines())
        if opened:
            issues.append(f"{name}:{opened}: code block never closed (a closing fence has nothing after it), so the "
                          "rest of the page renders as code")
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

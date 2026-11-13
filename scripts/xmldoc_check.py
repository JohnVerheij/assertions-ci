#!/usr/bin/env python3
"""XML documentation of packed packages: every documented member tells the reader something.

Usage: xmldoc_check.py <package.nupkg>...

Reads lib/<framework>/<assembly>.xml of each package (the documentation an IDE shows for the assembly next to it) and
reports
- an empty member: no documentation text or reference at all (no summary, remarks, parameters, ...) and no <inheritdoc>;
- a summary that is a generator placeholder ("Generated extension method for ...");
- an <inheritdoc cref="..."/> (anywhere in the member, also inside <summary>) whose target has no summary of its own,
  followed through further inheritdoc links.
A summary counts when it has text or a reference such as <see cref="..."/> or <see langword="null"/>. A target is
looked up in every package given, in the inheriting member's framework when that framework has it, so an adapter member
may inherit from the core package. A target that is a member of a type the packages document but has no entry of its
own is reported; any other target outside the documentation (TUnit, the .NET libraries) is not checked, and neither is
an <inheritdoc/> without cref (it inherits from a base type or interface). A member with other text but no summary
passes: the XML does not say whether it is public (the regex generator documents its private methods with remarks
only). Members the compiler did not write at all are the compiler's job (CS1591). Exit 1 on any issue.
"""
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

PLACEHOLDER_RE = re.compile(r"^Generated extension method for\b", re.IGNORECASE)
DOC_RE = re.compile(r"^lib/[^/]+/[^/]+\.xml$")
MEMBER_PREFIXES = ("M:", "P:", "F:", "E:")
MAX_INHERITDOC_DEPTH = 10
MAX_PRINTED = 50

Members = 'dict[str, list[tuple[str, ET.Element]]]'


def _text(element: ET.Element) -> str:
    """The element's text with whitespace collapsed."""
    return " ".join("".join(element.itertext()).split())


def _has_content(element: ET.Element) -> bool:
    """Whether the element holds text, or a reference element such as <see cref> (an <inheritdoc> does not count)."""
    return bool(_text(element)) or any(child.attrib for child in element.iter()
                                       if child is not element and child.tag != "inheritdoc")


def _framework(label: str) -> str:
    """The target framework folder of a documentation file label `<package>!lib/<framework>/<file>`."""
    return label.split("!", 1)[1].split("/")[1]


def _declaring_type(cref: str) -> str:
    """The type a member documentation ID belongs to: M:Ns.Type.Method(Ns.Arg) -> Ns.Type."""
    return cref[2:].split("(", 1)[0].rsplit(".", 1)[0]


def package_docs(path: str) -> 'dict[str, str]':
    """The XML documentation files of one package next to their assembly, as `<package>!<entry>` -> text."""
    with zipfile.ZipFile(path) as package:
        names = set(package.namelist())
        return {f"{path}!{name}": package.read(name).decode("utf-8-sig") for name in sorted(names)
                if DOC_RE.match(name) and name[: -len(".xml")] + ".dll" in names}


def members_of(docs: 'dict[str, str]') -> Members:
    """Every documented member of the files, by its documentation ID, with the file it comes from."""
    members: Members = {}
    for label, text in docs.items():
        for member in ET.fromstring(text).iter("member"):
            members.setdefault(member.get("name", ""), []).append((label, member))
    return members


def _summary_documents(member: ET.Element) -> bool:
    """Whether the member's own summary documents it: content that is not a generator placeholder."""
    summary = member.find("summary")
    return summary is not None and _has_content(summary) and not PLACEHOLDER_RE.match(_text(summary))


def _target_documented(cref: str, members: Members, owned: 'set[str]', framework: str, depth: int = 0) -> bool:
    """Whether an inheritdoc target ends in a real summary."""
    if cref not in members:
        return not (cref.startswith(MEMBER_PREFIXES) and _declaring_type(cref) in owned)
    entries = members[cref]
    for label, target in [entry for entry in entries if _framework(entry[0]) == framework] or entries:
        if _summary_documents(target):
            return True
        inherit = target.find(".//inheritdoc")
        if inherit is None:
            continue
        next_cref = inherit.get("cref")
        if next_cref is None:
            return True
        if depth < MAX_INHERITDOC_DEPTH and _target_documented(next_cref, members, owned, _framework(label), depth + 1):
            return True
    return False


def doc_issues(members: Members) -> list[str]:
    """The documentation issues of every member."""
    owned = {name[2:] for name in members if name.startswith("T:")}
    issues = []
    for name, entries in sorted(members.items()):
        for label, member in entries:
            summary = member.find("summary")
            text = _text(summary) if summary is not None else ""
            if PLACEHOLDER_RE.match(text):
                issues.append(f"{label}: {name}: placeholder summary '{text}'")
                continue
            if _summary_documents(member):
                continue
            inherit = member.find(".//inheritdoc")
            if inherit is None:
                if not _has_content(member):
                    issues.append(f"{label}: {name}: empty documentation (no text and no <inheritdoc>)")
                continue
            cref = inherit.get("cref")
            if cref is not None and not _target_documented(cref, members, owned, _framework(label)):
                issues.append(f"{label}: {name}: <inheritdoc cref=\"{cref}\"/> leads to no <summary>")
    return issues


def main(argv: list[str]) -> int:
    paths = argv[1:]
    if not paths:
        print("usage: xmldoc_check.py <package.nupkg>...")
        return 2
    docs: 'dict[str, str]' = {}
    for path in paths:
        docs.update(package_docs(path))
    if not docs:
        print("::error::No lib/<framework>/<assembly>.xml documentation file in " + ", ".join(paths))
        return 1
    members = members_of(docs)
    issues = doc_issues(members)
    if issues:
        print(f"FAIL ({len(issues)} issue(s)) in the XML documentation of the packages:")
        for issue in issues[:MAX_PRINTED]:
            print("::error::" + issue)
        if len(issues) > MAX_PRINTED:
            print(f"... and {len(issues) - MAX_PRINTED} more")
        return 1
    print(f"OK  {len(members)} documented members in {len(docs)} documentation file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

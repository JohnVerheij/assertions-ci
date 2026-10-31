"""Release notes for one version, taken from CHANGELOG.md.

Copies the section that starts with the line `## [<version>]` up to the next `## [` header or the link reference
definitions at the end of the file. Fails when the section is missing or has nothing besides its header, so a
release can't ship without notes.

Usage: release_notes.py <version> <changelog> <output>
Exit code 1 when the section is missing or empty.
"""

from __future__ import annotations

import re
import sys

LINK_DEFINITION = re.compile(r"^\[[^\]]+\]:\s")


def extract(changelog: str, version: str) -> str:
    header = f"## [{version}]"
    section: list[str] = []
    for line in changelog.splitlines():
        if section:
            if line.startswith("## [") or LINK_DEFINITION.match(line):
                break
            section.append(line)
        elif line.startswith(header):
            section.append(line)
    if not section:
        raise ValueError(f"CHANGELOG has no section for version {version}")
    if not any(line.strip() for line in section[1:]):
        raise ValueError(f"CHANGELOG section for version {version} is empty")
    return "\n".join(section).rstrip() + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: release_notes.py <version> <changelog> <output>")
        return 1
    _, version, changelog_path, output_path = argv
    try:
        with open(changelog_path, encoding="utf-8") as handle:
            notes = extract(handle.read(), version)
    except (OSError, ValueError) as error:
        print(f"::error::{error}")
        return 1
    with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(notes)
    print(f"Extracted {notes.count(chr(10))} lines of release notes for {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

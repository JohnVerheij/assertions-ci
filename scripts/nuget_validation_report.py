#!/usr/bin/env python3
"""Readable result of Meziantou's NuGet package validation (meziantou.validate-nuget-package writes JSON).

Usage: nuget_validation_report.py <validation output>

Prints one line per package. For a package with errors it prints each kind of error once as a ::error annotation,
with how often it occurs and up to three examples, so a hundred source-path errors stay readable. Exit 1 when the
tool reported any invalid package or its output is not the expected JSON.
"""
import json
import sys

MAX_EXAMPLES = 3


def _name(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def report(result: dict) -> 'tuple[list[str], bool]':
    """The report lines and whether every package is valid."""
    lines = []
    valid = bool(result.get("IsValid"))
    for path, package in sorted(result.get("Packages", {}).items()):
        errors = package.get("Errors") or []
        if not errors:
            lines.append(f"OK    {_name(path)}")
            continue
        valid = False
        lines.append(f"FAIL  {_name(path)} ({len(errors)} error(s))")
        by_code: 'dict[object, list[dict]]' = {}
        for error in errors:
            by_code.setdefault(error.get("ErrorCode"), []).append(error)
        for code, group in by_code.items():
            examples = "; ".join(_example(error) for error in group[:MAX_EXAMPLES])
            more = f" (and {len(group) - MAX_EXAMPLES} more)" if len(group) > MAX_EXAMPLES else ""
            lines.append(f"::error::{_name(path)}: rule {code}, {len(group)}x: {examples}{more}")
    return lines, valid


def _example(error: dict) -> str:
    message = str(error.get("Message", "")).strip()
    file_name = error.get("FileName")
    help_text = error.get("HelpText")
    text = f"{message} [{file_name}]" if file_name else message
    return f"{text} ({help_text})" if help_text else text


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: nuget_validation_report.py <validation output>")
        return 2
    with open(argv[1], encoding="utf-8-sig") as handle:
        raw = handle.read()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        print("::error::The NuGet package validation did not write JSON:")
        print(raw)
        return 1
    lines, valid = report(result)
    print("\n".join(lines) if lines else "::error::The NuGet package validation reported no package")
    return 0 if valid and lines else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

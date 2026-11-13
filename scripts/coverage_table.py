#!/usr/bin/env python3
"""Coverage of each test run, before the reports are merged: one row per suite, target framework and assembly.

Usage: coverage_table.py <coverage.cobertura.xml>...

Prints a Markdown table (suite, framework, assembly, line and branch coverage) and appends it to the job summary when
GITHUB_STEP_SUMMARY is set. It only reports: a suite covers part of an assembly that another suite also covers, and the
threshold applies to the merged report. The same suite and assembly with lower rates on one framework show code that
only the other framework covers.
"""
import os
import sys
import xml.etree.ElementTree as ET


def _percent(value: 'str | None') -> str:
    return f"{float(value) * 100:.2f}%" if value else "n/a"


def _folder_after(parts: list[str], name: str, offset: int) -> str:
    """The folder `offset` places after the folder `name`, or ? when there is none."""
    if name not in parts:
        return "?"
    index = parts.index(name) + offset
    return parts[index] if index < len(parts) - 1 else "?"


def describe(path: str) -> 'tuple[str, str]':
    """The suite (test project folder) and target framework of a report under tests/<suite>/bin/<config>/<tfm>/."""
    parts = path.replace("\\", "/").split("/")
    return _folder_after(parts, "tests", 1), _folder_after(parts, "bin", 2)


def table(paths: list[str]) -> str:
    """The Markdown table of the reports."""
    lines = ["| Suite | Framework | Assembly | Line | Branch |", "| --- | --- | --- | --- | --- |"]
    for path in paths:
        suite, framework = describe(path)
        packages = list(ET.parse(path).getroot().iter("package"))
        if not packages:
            lines.append(f"| {suite} | {framework} | (no measured code) | n/a | n/a |")
        for package in packages:
            lines.append(f"| {suite} | {framework} | {package.get('name', '?')} | "
                         f"{_percent(package.get('line-rate'))} | {_percent(package.get('branch-rate'))} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: coverage_table.py <coverage.cobertura.xml>...")
        return 2
    text = table(argv[1:])
    print(text, end="")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("### Coverage per test run\n\n" + text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

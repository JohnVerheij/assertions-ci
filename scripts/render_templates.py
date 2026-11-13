#!/usr/bin/env python3
"""Renders the family workflow templates into a workflows folder, so the workflow linters check what the package
repositories will run.

Usage: render_templates.py <workflows folder>  (in CI: .github/workflows, right before actionlint or zizmor)

Each workflow template is rendered for a demo package with a core package and written as template-<name>.yml; the
rendered files exist only in the CI workspace. The {{assertions-ci}} placeholder becomes a released commit with its
tag, so zizmor's online audits can resolve the reference.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import family_sync

DEMO_PACKAGE = "DemoAssertions"
# A released assertions-ci commit and its tag. Any release works: the linters check the reference's form, and
# zizmor that the commit belongs to the tag.
DEMO_PIN = "f7b3fdc470bba7b00e7333aeccae17e0377e6e15 # v1.3.0"
PREFIX = "template-"


def workflow_templates() -> list[str]:
    """The repository-relative paths of the workflow templates."""
    return [rel for rel in family_sync.template_files() if rel.startswith(".github/workflows/")]


def render_workflows(folder: str) -> list[str]:
    """Writes every rendered workflow template into the folder; returns the written paths."""
    written = []
    for rel in workflow_templates():
        text = family_sync.render(family_sync.read_template(rel), DEMO_PACKAGE, True, DEMO_PIN)
        path = os.path.join(folder, PREFIX + os.path.basename(rel))
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        written.append(path)
    return written


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        print("usage: render_templates.py <existing workflows folder>")
        return 2
    for path in render_workflows(argv[1]):
        print("rendered " + path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

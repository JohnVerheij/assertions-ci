"""Family templates: check a package repository against the shared files, or write them into it.

Usage: family_sync.py [--write] [<repo root>]  (default: the current directory)

The templates live in templates/package/ of assertions-ci, with the repository's path; a template may end in
.template, which the written file drops (the workflow callers do, so no tool in assertions-ci reads them as workflows,
and so does docs/docfx.json, whose {{core}} line is not valid JSON). Placeholders:
- {{Package}}: the package name without .TUnit (from src/<Package>.TUnit/), {{domain}}: its documentation domain;
- {{assertions-ci}}: the assertions-ci pin of the repository's own ci.yml, so every caller uses the same commit;
- a line starting with {{core}} is kept only when the repository has a core package (src/<Package>/).
Pinned versions of other actions (`uses: owner/action@<sha> # vX`) are not compared: Renovate updates them per
repository. The assertions-ci pins are compared: every caller must use the pin of ci.yml.

Without --write: lists every template file that is missing or differs, every obsolete file the family now shares from
assertions-ci, and every required local tool missing from .config/dotnet-tools.json; exit 1 when there is any.
With --write: writes the differing files (keeping the repository's own pins of other actions) and deletes the
obsolete ones, then lists the missing local tools, which it cannot add itself; exit 1 when there is any.
"""
import difflib
import glob
import json
import os
import re
import sys

TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "package")
TEMPLATE_SUFFIX = ".template"

# Files that moved into assertions-ci (scripts/, codeql/); a repository that still has them is out of date.
OBSOLETE = (
    ".github/family-lint.py",
    ".github/test_family_lint.py",
    ".github/docs-linkcheck.py",
    ".github/test_docs_linkcheck.py",
    ".github/codeql/codeql-config.yml",
)

# Local tools the shared workflows run: the coverage merge, the release SBOM, the documentation site.
REQUIRED_TOOLS = ("dotnet-reportgenerator-globaltool", "cyclonedx", "docfx")

# Pins of other actions; the negative lookahead leaves the assertions-ci pins to the comparison.
ACTION_PIN_RE = re.compile(r"(uses: (?!JohnVerheij/assertions-ci/)([^@\s]+)@)([0-9a-f]{40}(?: # \S+)?)")
ACI_PIN_RE = re.compile(r"uses: JohnVerheij/assertions-ci/\.github/workflows/package-ci\.yml@([0-9a-f]{40}(?: # \S+)?)")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read().replace("\r\n", "\n")


def template_files() -> list[str]:
    """Every template, as the repository-relative path it is written to (forward slashes, no .template suffix)."""
    root = os.path.normpath(TEMPLATES)
    files = []
    for directory, _, names in os.walk(root):
        for name in names:
            rel = os.path.relpath(os.path.join(directory, name), root).replace(os.sep, "/")
            files.append(rel[: -len(TEMPLATE_SUFFIX)] if rel.endswith(TEMPLATE_SUFFIX) else rel)
    return sorted(files)


def template_path(rel: str) -> str:
    """The template file of a repository-relative path."""
    path = os.path.join(TEMPLATES, rel)
    return path if os.path.isfile(path) else path + TEMPLATE_SUFFIX


def read_template(rel: str) -> str:
    """The text of the template for a repository-relative path, with LF line endings."""
    return _read(template_path(rel))


def package_name(root: str) -> 'str | None':
    """The package name (without .TUnit) of the repository's adapter project, from src/<Package>.TUnit/."""
    found = sorted(glob.glob(os.path.join(root, "src", "*.TUnit", "*.TUnit.csproj")))
    return os.path.basename(found[0])[: -len(".TUnit.csproj")] if found else None


def has_core(root: str, package: str) -> bool:
    return os.path.isfile(os.path.join(root, "src", package, f"{package}.csproj"))


def assertions_ci_pin(root: str) -> 'str | None':
    """The assertions-ci pin (`<sha> # vX.Y.Z`) of the repository's ci.yml."""
    path = os.path.join(root, ".github", "workflows", "ci.yml")
    if not os.path.isfile(path):
        return None
    match = ACI_PIN_RE.search(_read(path))
    return match.group(1) if match else None


def render(text: str, package: str, core: bool, pin: 'str | None') -> str:
    """The template text for one repository. Raises ValueError when it needs an assertions-ci pin and there is none."""
    lines = []
    for line in text.split("\n"):
        if line.startswith("{{core}}"):
            if not core:
                continue
            line = line[len("{{core}}"):]
        lines.append(line)
    text = "\n".join(lines).replace("{{Package}}", package).replace("{{domain}}", package.lower() + ".dev")
    if "{{assertions-ci}}" in text:
        if pin is None:
            raise ValueError("no assertions-ci pin in .github/workflows/ci.yml")
        text = text.replace("{{assertions-ci}}", pin)
    return text


def _without_pins(text: str) -> str:
    return ACTION_PIN_RE.sub(lambda m: m.group(1) + "PIN", text)


def _keep_pins(rendered: str, existing: str) -> str:
    """The rendered text with the existing file's pin for every action both of them use."""
    pins = {m.group(2): m.group(3) for m in ACTION_PIN_RE.finditer(existing)}
    return ACTION_PIN_RE.sub(lambda m: m.group(1) + pins.get(m.group(2), m.group(3)), rendered)


def _first_difference(expected: str, actual: str) -> int:
    matcher = difflib.SequenceMatcher(a=expected.split("\n"), b=actual.split("\n"), autojunk=False)
    for tag, first, _, _, _ in matcher.get_opcodes():
        if tag != "equal":
            return first + 1
    return 0


def _tool_issues(root: str) -> list[str]:
    path = os.path.join(root, ".config", "dotnet-tools.json")
    if not os.path.isfile(path):
        return [".config/dotnet-tools.json: missing (required local tools: " + ", ".join(REQUIRED_TOOLS)
                + "; create it with dotnet new tool-manifest)"]
    tools = json.loads(_read(path)).get("tools", {})
    return [f".config/dotnet-tools.json: missing the local tool {tool} (add it: dotnet tool install --local {tool})"
            for tool in REQUIRED_TOOLS if tool not in tools]


def _expected(root: str, package: str) -> 'tuple[dict[str, str], list[str]]':
    """The rendered template of every file, and the issues of templates that could not be rendered."""
    core, pin = has_core(root, package), assertions_ci_pin(root)
    expected, issues = {}, []
    for rel in template_files():
        try:
            expected[rel] = render(read_template(rel), package, core, pin)
        except ValueError as error:
            issues.append(f"{rel}: cannot render the family template: {error}")
    return expected, issues


def check(root: str, package: str) -> list[str]:
    expected, issues = _expected(root, package)
    for rel, text in expected.items():
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            issues.append(f"{rel}: missing (family template)")
            continue
        actual = _read(path)
        if _without_pins(actual) != _without_pins(text):
            line = _first_difference(_without_pins(text), _without_pins(actual))
            issues.append(f"{rel}: differs from the family template (first difference at line {line})")
    issues += [f"{rel}: obsolete, now shared from assertions-ci" for rel in OBSOLETE
               if os.path.isfile(os.path.join(root, rel))]
    return issues + _tool_issues(root)


def write(root: str, package: str) -> list[str]:
    """Writes the differing template files and deletes the obsolete ones. Returns what changed."""
    expected, issues = _expected(root, package)
    if issues:
        raise ValueError("; ".join(issues))
    changed = []
    for rel, text in expected.items():
        path = os.path.join(root, rel)
        if os.path.isfile(path):
            existing = _read(path)
            if _without_pins(existing) == _without_pins(text):
                continue
            text = _keep_pins(text, existing)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        changed.append(f"wrote {rel}")
    for rel in OBSOLETE:
        path = os.path.join(root, rel)
        if os.path.isfile(path):
            os.remove(path)
            changed.append(f"deleted {rel}")
    return changed


def main(argv: list[str]) -> int:
    args = argv[1:]
    write_mode = "--write" in args
    paths = [arg for arg in args if arg != "--write"]
    root = paths[0] if paths else "."
    package = package_name(root)
    if not package:
        print(f"::error::{root} has no src/<Package>.TUnit/<Package>.TUnit.csproj")
        return 1
    if write_mode:
        try:
            changed = write(root, package)
        except ValueError as error:
            print(f"::error::{error}")
            return 1
        print("\n".join(changed) if changed else "Nothing to write: the repository matches the family templates.")
        tools = _tool_issues(root)
        if tools:
            print(f"FAIL ({len(tools)} issue(s)) left to fix by hand:")
            for issue in tools:
                print("  - " + issue)
            return 1
        return 0
    issues = check(root, package)
    if issues:
        print(f"FAIL ({len(issues)} issue(s)); family_sync.py --write updates the template files and obsolete files:")
        for issue in issues:
            print("  - " + issue)
        return 1
    print("OK  the repository matches the family templates")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

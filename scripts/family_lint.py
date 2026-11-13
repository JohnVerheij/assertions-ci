#!/usr/bin/env python3
"""Family lint gate for a package repository (CI-safe: no sensitive terms).

Usage: family_lint.py [<repo root>]  (default: the current directory)

Checks, each exit 1 on a violation:
- CHANGELOG.md follows Keep a Changelog and the family conventions;
- every src/**/*.csproj <PackageTags> follows the two-variant order;
- American English: no known British spellings in tracked text files (a word list; release history and snapshot
  baselines excepted);
- README facts: the TUnit minimum in every README equals the central TUnit version, the adapter README names every
  sibling package, and the first row of the SECURITY.md supported-versions table is the current version line;
- the shared files match the family templates (family_sync.py check: templates/package/, obsolete files, local tools).
"""
import glob
import os
import re
import subprocess
import sys

# The sibling module family_sync, also when Python runs isolated (-I), which leaves the script's folder off sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import family_sync

ALLOWED_H3 = {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security", "BREAKING"}
ORDER = ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]
VER_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}: \S.*$")
VER_LOOSE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]")
FOOT_RE = re.compile(r"^\[(\d+\.\d+\.\d+)\]:(\s*)(\S.*?)\s*$")
UNREL_FOOT_RE = re.compile(r"^\[[Uu]nreleased\]:(\s*)(\S.*?)\s*$")
TAGS_RE = re.compile(r"<PackageTags>(.*?)</PackageTags>")

def _ver(s: str) -> tuple[int, ...]:
    return tuple(int(p) for p in s.split("."))

def _order_issues(header_versions: list[str]) -> list[str]:
    out = []
    for a, b in zip(header_versions, header_versions[1:]):
        if _ver(a) <= _ver(b):
            out.append(f"versions must be newest-first: [{a}] should sit above [{b}], not below")
    return out

def _footer_issues(line: str, i: int, footer_versions: list[str]) -> list[str]:
    fm = FOOT_RE.match(line)
    if fm:
        footer_versions.append(fm.group(1))
        out = []
        if fm.group(2) != " ":
            out.append(f"L{i}: footer [{fm.group(1)}] needs exactly one space after ':'")
        if not fm.group(3).rstrip().endswith(f"v{fm.group(1)}"):
            out.append(f"L{i}: footer [{fm.group(1)}] should target 'v{fm.group(1)}': {fm.group(3).strip()!r}")
        return out
    um = UNREL_FOOT_RE.match(line)
    if um:
        out = []
        if um.group(1) != " ":
            out.append(f"L{i}: footer [unreleased] needs exactly one space after ':'")
        if not um.group(2).rstrip().endswith("HEAD"):
            out.append(f"L{i}: footer [unreleased] should target 'HEAD': {um.group(2).strip()!r}")
        return out
    return []

def _header_issues(line: str, i: int, header_versions: list[str]) -> tuple[list[str], str]:
    """Validate a non-Unreleased '## [...]' header. Returns (issues, cur)."""
    m = VER_LOOSE.match(line)
    if not m:
        return [f"L{i}: malformed version header, expected '## [x.y.z] - YYYY-MM-DD: summary': {line.strip()!r}"], line.strip()
    header_versions.append(m.group(1))
    issues = []
    if not VER_RE.match(line):
        issues.append(f"L{i}: version header not '## [x.y.z] - YYYY-MM-DD: summary': {line.strip()!r}")
    return issues, m.group(1)

def _section_issues(line: str, i: int, cur: 'str | None', seen: list[int]) -> list[str]:
    """Validate a '### ' section header; records its order index in `seen`."""
    name = line[4:].strip()
    if name not in ALLOWED_H3:
        return [f"L{i}: non-standard section '### {name}'"]
    if name not in ORDER:
        return []
    idx = ORDER.index(name)
    if idx in seen:
        out = [f"L{i}: duplicate '### {name}' section under [{cur}]"]
    elif seen and idx < seen[-1]:
        out = [f"L{i}: '### {name}' out of order under [{cur}]"]
    else:
        out = []
    seen.append(idx)
    return out

def lint_changelog(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    v, header_versions, footer_versions = [], [], []
    if not any(line.strip() == "## [Unreleased]" for line in lines):
        v.append("missing '## [Unreleased]' section")
    if not any(line.strip().lower().startswith("[unreleased]:") for line in lines):
        v.append("missing '[unreleased]:' footer link")
    cur, seen, first_section, unreleased_at = None, [], None, None
    for i, line in enumerate(lines, 1):
        if line.startswith("## ["):
            seen = []  # every version section starts a fresh order scope
            if first_section is None:
                first_section = line.strip()
                if first_section != "## [Unreleased]":
                    v.append(f"L{i}: first section must be '## [Unreleased]', found {first_section!r}")
            if line.strip() == "## [Unreleased]":
                if unreleased_at is not None:
                    v.append(f"L{i}: duplicate '## [Unreleased]' section (first at L{unreleased_at})")
                unreleased_at = i
                cur = "Unreleased"
            else:
                issues, cur = _header_issues(line, i, header_versions)
                v += issues
        elif line.startswith("#### "):
            v.append(f"L{i}: sub-header deeper than '###' not allowed: {line.strip()!r}")
        elif line.startswith("### "):
            v += _section_issues(line, i, cur, seen)
        else:
            v += _footer_issues(line, i, footer_versions)
    v += _order_issues(header_versions)
    for miss in sorted(set(header_versions) - set(footer_versions)):
        v.append(f"[{miss}] version section has no footer link")
    for miss in sorted(set(footer_versions) - set(header_versions)):
        v.append(f"[{miss}] footer link has no version section")
    return v

def lint_tags(csproj: str) -> list[str]:
    with open(csproj, encoding="utf-8") as f:
        m = TAGS_RE.search(f.read())
    if not m:
        return []
    tags = [t.strip() for t in m.group(1).split(";") if t.strip()]
    is_adapter = csproj.endswith(".TUnit.csproj")
    lead = ["tunit", "assertions", "testing"] if is_adapter else ["assertions", "testing"]
    v = []
    if tags[:len(lead)] != lead:
        v.append(f"{csproj}: PackageTags must start with '{';'.join(lead)}' (got '{';'.join(tags[:len(lead)])}')")
    if tags[-2:] != ["dotnet", "aot"]:
        v.append(f"{csproj}: PackageTags must end with 'dotnet;aot' (got '{';'.join(tags[-2:])}')")
    if not is_adapter and "tunit" in tags:
        v.append(f"{csproj}: core PackageTags must not contain 'tunit'")
    return v

# The packages of the family. A new package is added here once, and every repository's adapter README must list it.
FAMILY = (
    "GrpcAssertions",
    "JsonAssertions",
    "LogAssertions",
    "MathAssertions",
    "MetricsAssertions",
    "SnapshotAssertions",
    "SseAssertions",
    "TimeAssertions",
    "TracingAssertions",
)

# Known British spellings. The -ise verbs need an -ise ending, so "organism" or "realistic" do not match, and "analyses"
# passes (it is also the American plural of "analysis"). A blocklist: it catches the spellings the family has used and
# the common -ise verbs, not every British word.
BRITISH_RE = re.compile(
    r"(?:initialis|recognis|normalis|serialis|organis|synchronis"  # spellchecker:disable-line
    r"|customis|optimis|utilis|prioritis|summaris|categoris)"  # spellchecker:disable-line
    r"(?:e|ed|es|ing|ation|ations|er|ers|able)\b"
    r"|analys(?:e|ed|ing|er|ers)\b"
    r"|behaviour|artefact|honour|cancelled|colour|favour|licence|centre",
    re.IGNORECASE,
)
TEXT_SUFFIXES = (".md", ".cs", ".csproj", ".props", ".targets", ".yml", ".yaml", ".json", ".xml", ".txt", ".py",
                 ".slnx", ".sh", ".ps1", ".config")
TEXT_NAMES = (".editorconfig", ".gitattributes", ".gitignore")
# Release history keeps its wording; snapshot baselines are generated; lock files and LICENSE are not ours to word.
SPELLING_SKIP = re.compile(
    r"(^|/)CHANGELOG\.md$|(^|/)LICENSE$|packages\.lock\.json$|\.(verified|received|expected)\.txt$|(^|/)Snapshots/"
    r"|(^|/)docs/_site/"
)

TUNIT_PIN_RE = re.compile(r'<PackageVersion\s+Include="TUnit"\s+Version="([^"]+)"')
FLOOR_RE = re.compile(r"TUnit (\d+\.\d+\.\d+) or later")
VERSION_RE = re.compile(r"<Version>(\d+)\.(\d+)\.\d+[^<]*</Version>")
VERSION_LINE_RE = re.compile(r"`(\d+\.\d+)\.x`")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _identifier_part(line: str, start: int, word: str, code_file: bool) -> bool:
    """True when the match is part of code: a call such as GitHub's `cancelled()`, a name joined with an underscore
    (`Status_Cancelled_Fails`), or a capitalized word in camel case or after a dot (`IsCancelled`,
    `StatusCode.Cancelled`); in a C# file every capitalized match counts as code (an enum member or a status string)."""
    end = start + len(word)
    after = line[end:end + 1]
    before = line[start - 1] if start > 0 else ""
    if after in ("(", "_") or before == "_":
        return True
    if not word[0].isupper():
        return False
    return code_file or before.isalnum() or before == "."


def british_spellings(text: str, name: str) -> list[str]:
    """Known British spellings in one file's text, with their line numbers. Code is exempt (see _identifier_part), so a
    released API such as `IsCancelled` or a dependency's `StatusCode.Cancelled` passes."""
    code_file = name.endswith(".cs")
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in BRITISH_RE.finditer(line):
            if not _identifier_part(line, match.start(), match.group(0), code_file):
                out.append(f"{name}:{number}: British spelling '{match.group(0)}' (use American English)")
    return out


def _tracked_files(root: str) -> list[str]:
    """The repository's tracked files, relative to root; every file below root when it is not a Git checkout."""
    try:
        result = subprocess.run(["git", "-C", root, "ls-files"], capture_output=True, text=True, check=True)
        return [line for line in result.stdout.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        files = []
        for directory, folders, names in os.walk(root):
            folders[:] = [folder for folder in folders if folder not in (".git", ".assertions-ci")]
            for file_name in names:
                files.append(os.path.relpath(os.path.join(directory, file_name), root).replace(os.sep, "/"))
        return files


def lint_spelling(root: str, files: list[str]) -> list[str]:
    """British spellings in the tracked text files of the repository."""
    out = []
    for name in files:
        if SPELLING_SKIP.search(name):
            continue
        if not (name.endswith(TEXT_SUFFIXES) or os.path.basename(name) in TEXT_NAMES):
            continue
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        try:
            out += british_spellings(_read(path), name)
        except UnicodeDecodeError:
            continue
    return out


# The package name (without .TUnit) of the repository's adapter project, from src/<Package>.TUnit/.
adapter_package = family_sync.package_name


def _floor_issues(root: str, package: str) -> list[str]:
    props = os.path.join(root, "Directory.Packages.props")
    if not os.path.isfile(props):
        return []
    pin = TUNIT_PIN_RE.search(_read(props))
    if not pin:
        return []
    required = {"README.md", f"src/{package}.TUnit/README.md"}
    readmes = sorted(required | {os.path.relpath(p, root).replace(os.sep, "/")
                                 for p in glob.glob(os.path.join(root, "src", "*", "README.md"))})
    out = []
    for name in readmes:
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            out.append(f"{name}: missing")  # only a required name can be missing: the others come from the glob
            continue
        floors = FLOOR_RE.findall(_read(path))
        if not floors and name in required:
            out.append(f"{name}: no 'TUnit X.Y.Z or later' line (the TUnit minimum, decision D4)")
        for floor in floors:
            if floor != pin.group(1):
                out.append(f"{name}: TUnit minimum {floor} differs from the central TUnit version {pin.group(1)}")
    return out


def _family_issues(root: str, package: str) -> list[str]:
    path = os.path.join(root, "src", f"{package}.TUnit", "README.md")
    if not os.path.isfile(path):
        return []
    text = _read(path)
    return [f"src/{package}.TUnit/README.md: family list does not name {sibling}.TUnit"
            for sibling in FAMILY if sibling != package and f"{sibling}.TUnit" not in text]


def _security_issues(root: str, package: str) -> list[str]:
    csproj = os.path.join(root, "src", f"{package}.TUnit", f"{package}.TUnit.csproj")
    version = VERSION_RE.search(_read(csproj)) if os.path.isfile(csproj) else None
    security = os.path.join(root, "SECURITY.md")
    if not version or not os.path.isfile(security):
        return []
    current = f"{version.group(1)}.{version.group(2)}"
    text = _read(security)
    _, found, section = text.partition("## Supported versions")
    rows = [line for line in section.splitlines() if line.startswith("|")][2:3] if found else []
    first = VERSION_LINE_RE.search(rows[0]) if rows else None
    if not first:
        return ["SECURITY.md: no supported-versions table with a `X.Y.x` first row"]
    if first.group(1) != current:
        return [f"SECURITY.md: first supported version line is {first.group(1)}.x, the package version is {current}.x"]
    return []


def lint_readme_facts(root: str, package: str) -> list[str]:
    """README facts that drift by hand: the TUnit minimum, the family list and the supported-versions table."""
    return _floor_issues(root, package) + _family_issues(root, package) + _security_issues(root, package)


def main(argv: list[str]) -> int:
    root = argv[1] if len(argv) > 1 else "."
    issues = []
    changelog = os.path.join(root, "CHANGELOG.md")
    if os.path.isfile(changelog):
        issues += [f"CHANGELOG.md: {x}" for x in lint_changelog(changelog)]
    for csproj in sorted(glob.glob(os.path.join(root, "src", "**", "*.csproj"), recursive=True)):
        issues += lint_tags(csproj)
    issues += lint_spelling(root, _tracked_files(root))
    drift: list[str] = []
    package = adapter_package(root)
    if package:
        issues += lint_readme_facts(root, package)
        drift = family_sync.check(root, package)
        issues += drift
    if issues:
        print(f"FAIL ({len(issues)} issue(s)):")
        for issue in issues:
            print("  - " + issue)
        if drift:
            print("Update the shared files with: python3 .assertions-ci/scripts/family_sync.py --write")
        return 1
    print("OK  changelog, package tags, spelling, README facts and family templates conform")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

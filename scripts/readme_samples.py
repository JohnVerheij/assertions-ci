#!/usr/bin/env python3
"""Turns the C# samples of a package repository's READMEs into a project that compiles them against the packed packages.

Usage: readme_samples.py <package> <version> <frameworks> [<repo root>]

Writes tests/.readme-samples/ (not committed): ReadmeSamples.csproj with the smoke test project's package references,
the adapter at the packed version and implicit usings on, as in a consumer's project; the smoke test's NuGet.config;
and one generated file per sample. `dotnet build` on the project then compiles every sample. The conventions:
- a fenced block whose info string starts with csharp, cs or c# is a sample; `csharp no-compile` opts a block out
  (pseudo code, a deliberately wrong example, an excerpt that cannot stand on its own);
- a sample may mix what a consumer writes in different places: its leading using and preprocessor directives go to the
  top of the file, each top-level type or namespace declaration into the sample's namespace, each member declaration
  (one that starts with an attribute, an access modifier or readonly) into a class, and every other line, in order,
  into the body of an async method of that class. A line inside an open string, comment, bracket, or an unfinished
  statement or declaration stays with the line before it. A sample with a file-scoped namespace compiles as a file of
  its own, its namespace prefixed with the sample's (so two samples may declare the same types);
- tests/ReadmeSamples.Prelude.cs, when present, declares what samples use without declaring it themselves: types in
  namespace ReadmeSamples, and members of `public partial class Prelude` there, which every wrapping class derives from;
- #line directives map every part back to its README line, so a compiler error names the README line.
"""
import glob
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr

OUTPUT = os.path.join("tests", ".readme-samples")
PRELUDE = "ReadmeSamples.Prelude.cs"
LANGUAGES = ("csharp", "cs", "c#")
OPT_OUT = "no-compile"
FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*(.*)$")
USING_RE = re.compile(r"^\s*(global\s+)?using\s+((static\s+)?[\w.:<>,\s]+|\w+\s*=\s*[^;]+)\s*;\s*(//.*)?$")
TYPE_RE = re.compile(r"^((public|internal|private|protected|file|sealed|static|abstract|partial|readonly|ref|unsafe|new)"
                     r"\s+)*(class|record|struct|interface|enum|namespace|delegate)\b")
# An access modifier, or readonly (never the start of a statement): a field, property, method or constructor.
MEMBER_RE = re.compile(r"^(public|private|protected|internal|static\s+readonly|readonly)\b")
ASSEMBLY_ATTRIBUTE_RE = re.compile(r"^\[\s*(assembly|module)\s*:")
FILE_SCOPED_NAMESPACE_RE = re.compile(r"^(\s*)namespace\s+([\w.]+)\s*;")
CODE = ("code",)


class UnclosedFence(ValueError):
    """A fenced code block that no fence closes: GitHub and nuget.org render the rest of the README as code."""


def _closes(line: str, fence: str) -> bool:
    """Whether the line closes a block opened with `fence`: the same fence character, at least as many, and nothing
    else but spaces (CommonMark). A line such as '``` More text.' does not close the block."""
    stripped = line.strip()
    return bool(stripped) and set(stripped) == {fence[0]} and len(stripped) >= len(fence)


class Sample:
    """One C# block of a README: its file, the README line of its first line, and its lines. `source` is the path the
    #line directives name (absolute in the generated project, so an error points at the README itself)."""

    def __init__(self, readme: str, first_line: int, lines: list[str], source: 'str | None' = None):
        self.readme = readme
        self.first_line = first_line
        self.lines = lines
        self.source = source or readme


class Part:
    """A run of sample lines that compiles in one place: a type, a member or statements. `last_code` is its last line
    of code (literals and comments removed) and `only_attributes` whether every line of code so far is an attribute,
    which together tell whether the part has ended."""

    def __init__(self, kind: str, start: int):
        self.kind = kind
        self.start = start
        self.lines: list[str] = []
        self.last_code = ""
        self.only_attributes = True

    def add(self, line: str, code: str) -> None:
        self.lines.append(line)
        if code and not code.startswith("#"):
            self.last_code = code
            self.only_attributes = self.only_attributes and code.startswith("[")

    def is_open(self) -> bool:
        """Whether the next line belongs to this part whatever it starts with: a declaration with only attributes so far,
        or any part whose last line of code ends in neither ; nor } (a call chain, an assignment, an argument list)."""
        if self.kind != "statements" and self.only_attributes:
            return True
        return bool(self.last_code) and not self.last_code.endswith((";", "}"))


def _code(line: str, state: tuple) -> 'tuple[str, tuple]':
    """The code of a line, without comments and literals, and the state the line ends in: code, or inside a /* comment,
    a verbatim string or a raw string (with its number of quotes), which can all span lines."""
    out, index = [], 0
    while index < len(line):
        if state[0] == "comment":
            end = line.find("*/", index)
            index, state = (len(line), state) if end < 0 else (end + 2, CODE)
        elif state[0] == "verbatim":
            end = _verbatim_end(line, index)
            index, state = (len(line), state) if end < 0 else (end, CODE)
        elif state[0] == "raw":
            end = line.find('"' * state[1], index)
            index, state = (len(line), state) if end < 0 else (end + state[1], CODE)
        elif line.startswith("//", index):
            break
        elif line.startswith("/*", index):
            index, state = index + 2, ("comment",)
        elif line[index] == '"':
            quotes = len(line[index:]) - len(line[index:].lstrip('"'))
            if quotes >= 3:
                index, state = index + quotes, ("raw", quotes)
            elif "@" in line[max(0, index - 2):index]:
                index, state = index + 1, ("verbatim",)
            else:
                index = _regular_end(line, index)
        elif line[index] == "'":
            index = _regular_end(line, index)
        else:
            out.append(line[index])
            index += 1
    return "".join(out), state


def _verbatim_end(line: str, start: int) -> int:
    """The index after the closing quote of a verbatim string ("" is an escaped quote), or -1 on this line."""
    index = start
    while index < len(line):
        if line[index] == '"':
            if line[index + 1:index + 2] == '"':
                index += 2
                continue
            return index + 1
        index += 1
    return -1


def _regular_end(line: str, start: int) -> int:
    """The index after a regular string or character literal that starts at `start` (backslash escapes)."""
    quote, index = line[start], start + 1
    while index < len(line):
        if line[index] == "\\":
            index += 2
        elif line[index] == quote:
            return index + 1
        else:
            index += 1
    return index


def _declaration_kind(code: str) -> 'str | None':
    """assembly, type, member or None (a statement) for a line of code at the top level of a sample."""
    if ASSEMBLY_ATTRIBUTE_RE.match(code):
        return "assembly"
    if TYPE_RE.match(code):
        return "type"
    if code.startswith("[") or MEMBER_RE.match(code):
        return "member"
    return None


def _nesting(code: str) -> int:
    return sum(code.count(open_) - code.count(close) for open_, close in ("{}", "()", "[]"))


def parts_of(sample: Sample) -> 'tuple[list[tuple[int, str]], list[Part], int | None]':
    """The leading using and preprocessor directives, the parts, and the index of a file-scoped namespace line."""
    usings: 'list[tuple[int, str]]' = []
    parts: list[Part] = []
    current: 'Part | None' = None
    nesting, state, leading = 0, CODE, True
    for index, line in enumerate(sample.lines):
        continues = state != CODE or nesting > 0 or (current is not None and current.is_open())
        code, state = _code(line, state)
        stripped = code.strip()
        if leading and (USING_RE.match(line) or stripped.startswith("#")):
            usings.append((index, line.strip()))
            continue
        leading = leading and not stripped
        continues = continues or (stripped.startswith("#") and current is not None)
        if not continues and stripped and FILE_SCOPED_NAMESPACE_RE.match(stripped):
            return usings, [], index
        if continues and current is not None:
            pass  # the line continues the current part
        elif not stripped:
            if current is None or current.kind != "statements":
                continue
        else:
            kind = _declaration_kind(stripped) or "statements"
            if current is None or kind != "statements" or current.kind != "statements":
                current = Part(kind, index)
                parts.append(current)
        if current.kind == "member" and current.only_attributes and TYPE_RE.match(stripped):
            current.kind = "type"
        current.add(line, stripped)
        nesting += _nesting(stripped)
    return usings, parts, None


def samples_of(readme: str, text: str, source: 'str | None' = None) -> 'tuple[list[Sample], int]':
    """The compiled samples of one README, and how many C# blocks opt out. Raises UnclosedFence for a block that no
    fence closes."""
    samples, skipped = [], 0
    lines = text.removeprefix("﻿").splitlines()
    index = 0
    while index < len(lines):
        match = FENCE_RE.match(lines[index])
        # A backtick fence's info string has no backtick: a line such as '```x``` text' is inline code, not a block.
        if not match or (match.group(2)[0] == "`" and "`" in match.group(3)):
            index += 1
            continue
        fence, info = match.group(2), match.group(3).split()
        end = index + 1
        while end < len(lines) and not _closes(lines[end], fence):
            end += 1
        if end == len(lines):
            raise UnclosedFence(f"{readme}:{index + 1}: this code block is never closed, so the rest of the README "
                                "renders as code. A closing fence has nothing but the fence characters on its line.")
        if info and info[0].lower() in LANGUAGES:
            if OPT_OUT in info[1:]:
                skipped += 1
            else:
                samples.append(Sample(readme, index + 2, lines[index + 1:end], source))
        index = end + 1
    return samples, skipped


def _line(sample: Sample, index: int) -> str:
    return f'#line {sample.first_line + index} "{sample.source}"'


def _emit(sample: Sample, part: Part) -> list[str]:
    return [_line(sample, part.start)] + part.lines + ["#line default"]


def render(sample: Sample, number: int) -> str:
    """The generated C# file of one sample."""
    usings, parts, file_scoped = parts_of(sample)
    out = ["// <auto-generated/>", f"// Sample {number} of {sample.readme}, written by readme_samples.py."]
    for index, line in usings:
        out += [_line(sample, index), line, "#line default"]
    if file_scoped is not None:
        rest = Part("file", file_scoped)
        prefix = f"ReadmeSamples.Sample{number:03}."
        rest.lines = [FILE_SCOPED_NAMESPACE_RE.sub(lambda m: f"{m.group(1)}namespace {prefix}{m.group(2)};",
                                                   sample.lines[file_scoped], count=1)] + sample.lines[file_scoped + 1:]
        return "\n".join(out + _emit(sample, rest)) + "\n"
    for part in parts:
        if part.kind == "assembly":
            out += _emit(sample, part)
    out += [f"namespace ReadmeSamples.Sample{number:03}", "{"]
    for part in parts:
        if part.kind == "type":
            out += _emit(sample, part)
    members = [part for part in parts if part.kind == "member"]
    statements = [part for part in parts if part.kind == "statements"]
    if members or statements:
        out += ["public partial class Sample : global::ReadmeSamples.Prelude", "{"]
        for part in members:
            out += _emit(sample, part)
        if statements:
            out += ["public async global::System.Threading.Tasks.Task RunAsync()", "{"]
            for part in statements:
                out += _emit(sample, part)
            out += ["}"]
        out += ["}"]
    return "\n".join(out + ["}"]) + "\n"


def _framework_condition(condition: 'str | None') -> 'str | None':
    """The condition when it is on the target framework (a per-framework version); None for any other condition, which
    names the smoke project's own properties and does not apply to the generated project."""
    return condition if condition and "TargetFramework" in condition else None


def _both(group_condition: 'str | None', item_condition: 'str | None') -> 'str | None':
    """The condition of an item: its group's and its own, both when there are two."""
    if group_condition and item_condition:
        return f"({group_condition}) and ({item_condition})"
    return group_condition or item_condition


def package_references(smoke_csproj: str, package: str, version: str) -> 'list[tuple[str | None, str, str]]':
    """The smoke project's package references as (framework condition, name, version), the adapter at the packed
    version. A condition on the target framework, on the item or its item group, is kept (both, when both have one):
    the smoke project gives a dependency a version per framework that way (dpfa Proj0028 puts it on the group)."""
    references = []
    for group in ET.parse(smoke_csproj).getroot().iter("ItemGroup"):
        group_condition = _framework_condition(group.get("Condition"))
        for item in group.findall("PackageReference"):
            name = item.get("Include", "")
            condition = _both(group_condition, _framework_condition(item.get("Condition")))
            references.append((condition, name, version if name == f"{package}.TUnit" else item.get("Version", "")))
    return references


def _reference_groups(references: 'list[tuple[str | None, str, str]]') -> str:
    """The item groups of the references, one per condition, in the order the conditions first appear. The values are
    XML-quoted again: the parser decoded entities such as &lt; in them."""
    conditions: 'list[str | None]' = []
    for condition, _, _ in references:
        if condition not in conditions:
            conditions.append(condition)
    groups = []
    for condition in conditions:
        attribute = f" Condition={quoteattr(condition)}" if condition else ""
        items = "\n".join(f"    <PackageReference Include={quoteattr(name)} Version={quoteattr(version)} />"
                          for item_condition, name, version in references if item_condition == condition)
        groups.append(f"  <ItemGroup{attribute}>\n{items}\n  </ItemGroup>")
    return "\n".join(groups)


def project(frameworks: str, references: 'list[tuple[str | None, str, str]]') -> str:
    """The generated project file."""
    return f"""<Project Sdk="Microsoft.NET.Sdk">
  <!-- Generated by readme_samples.py from the smoke test project; compiles the README samples. Not committed. -->
  <PropertyGroup>
    <TargetFrameworks>{";".join(frameworks.split())}</TargetFrameworks>
    <AssemblyName>ReadmeSamples</AssemblyName>
    <RootNamespace>ReadmeSamples</RootNamespace>
    <IsPackable>false</IsPackable>
    <ImplicitUsings>enable</ImplicitUsings>
    <ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally>
    <RestorePackagesWithLockFile>false</RestorePackagesWithLockFile>
    <TreatWarningsAsErrors>false</TreatWarningsAsErrors>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="*.g.cs" />
    <Compile Include="../{PRELUDE}" Condition="Exists('../{PRELUDE}')" />
  </ItemGroup>
{_reference_groups(references)}
</Project>
"""


def readmes(root: str) -> list[str]:
    """The README files with samples: the root README and every package README under src/."""
    found = ["README.md"] if os.path.isfile(os.path.join(root, "README.md")) else []
    found += sorted(os.path.relpath(path, root).replace(os.sep, "/")
                    for path in glob.glob(os.path.join(root, "src", "*", "README.md")))
    return found


def write(root: str, package: str, version: str, frameworks: str) -> 'tuple[int, int]':
    """Writes the project; returns the number of compiled samples and of opted-out blocks."""
    smoke = os.path.join(root, "tests", f"{package}.TUnit.SmokeTest")
    output = os.path.join(root, OUTPUT)
    shutil.rmtree(output, ignore_errors=True)
    os.makedirs(output)
    samples, skipped = [], 0
    for readme in readmes(root):
        path = os.path.abspath(os.path.join(root, readme))
        with open(path, encoding="utf-8-sig") as handle:
            found, opted_out = samples_of(readme, handle.read(), path.replace(os.sep, "/"))
        samples += found
        skipped += opted_out
    files = {"Prelude.g.cs": "// <auto-generated/>\nnamespace ReadmeSamples\n{\npublic partial class Prelude\n{\n}\n}\n"}
    for number, sample in enumerate(samples, 1):
        files[f"Sample{number:03}.g.cs"] = render(sample, number)
    references = package_references(os.path.join(smoke, f"{package}.TUnit.SmokeTest.csproj"), package, version)
    files["ReadmeSamples.csproj"] = project(frameworks, references)
    for name, text in files.items():
        with open(os.path.join(output, name), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    shutil.copyfile(os.path.join(smoke, "NuGet.config"), os.path.join(output, "NuGet.config"))
    return len(samples), skipped


def main(argv: list[str]) -> int:
    if len(argv) not in (4, 5):
        print("usage: readme_samples.py <package> <version> <frameworks> [<repo root>]")
        return 2
    package, version, frameworks = argv[1], argv[2], argv[3]
    root = argv[4] if len(argv) == 5 else "."
    try:
        count, skipped = write(root, package, version, frameworks)
    except UnclosedFence as error:
        print(f"FAIL {error}")
        return 1
    print(f"{count} README sample(s) written to {OUTPUT}; {skipped} block(s) marked {OPT_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

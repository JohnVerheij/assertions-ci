""".NET release gate for the packages built from a repository.

Reads the NuGet restore output (src/*/obj/project.assets.json) of every packable project and follows, per target
framework, the packages that reach consumers (the license gate's walk: direct package dependencies that are not
PrivateAssets=all, plus their transitive closure). A runtime, ASP.NET Core or extensions package ships one version per
.NET release, and its major version is that release: a System.*, Microsoft.Extensions.*, Microsoft.AspNetCore.*,
Microsoft.Bcl.*, Microsoft.NETCore.* or Microsoft.Win32.* package whose .nuspec repository is dotnet/dotnet,
dotnet/runtime, dotnet/aspnetcore or dotnet/extensions. Such a package must not be newer than the target framework:
Microsoft.Extensions.Logging 11.0.0 in the net10.0 dependencies would hand .NET 11 assemblies to .NET 10 consumers.

Not checked: other packages of those repositories (MSBuild, Roslyn and NuGet have versions of their own), packages
whose .nuspec names no repository, and build-only packages (PrivateAssets=all, such as SourceLink), which do not
reach consumers.

Usage: net_line_gate.py
Exit code 1 when a package is newer than its target framework, when a target framework has no restore targets, when a
shipped package's .nuspec is missing or unreadable or its version is not a number, or when no restore output is found.
"""

from __future__ import annotations

import glob
import json
import re
import sys
import xml.etree.ElementTree as ET

from license_gate import find_nuspec, framework_targets, shipped_for

# Since .NET 10 the runtime and ASP.NET Core packages are built in the unified dotnet/dotnet repository.
DOTNET_REPOSITORIES = {"github.com/dotnet/dotnet", "github.com/dotnet/runtime", "github.com/dotnet/aspnetcore",
                       "github.com/dotnet/extensions"}
RELEASE_PREFIXES = ("System.", "Microsoft.Extensions.", "Microsoft.AspNetCore.", "Microsoft.Bcl.", "Microsoft.NETCore.",
                    "Microsoft.Win32.")
FRAMEWORK_RE = re.compile(r"^net(\d+)\.\d+")


def repository(nuspec_path: str) -> str:
    """The repository URL of a .nuspec as host and path (github.com/dotnet/runtime); empty when it names none.
    Raises xml.etree.ElementTree.ParseError for a file that is not XML."""
    for el in ET.parse(nuspec_path).getroot().iter():
        if el.tag.rsplit("}", 1)[-1] == "repository":
            url = (el.get("url") or "").strip().lower()
            url = re.sub(r"^[a-z+]+://", "", url)
            url = re.sub(r"\.git$", "", url.rstrip("/"))
            return url.rstrip("/")
    return ""


def ships_per_release(name: str, nuspec_path: str) -> bool:
    """Whether a package ships one version per .NET release: a runtime name from a dotnet repository."""
    return name.startswith(RELEASE_PREFIXES) and repository(nuspec_path) in DOTNET_REPOSITORIES


def framework_release(alias: str) -> int | None:
    """The .NET release of a target framework alias (net10.0 gives 10); None for any other framework."""
    match = FRAMEWORK_RE.match(alias)
    return int(match.group(1)) if match else None


def _check_package(assets: dict, alias: str, release: int, key: str) -> tuple[str | None, str | None, bool]:
    """(violation, problem, checked) for one shipped package of one target framework."""
    nuspec = find_nuspec(assets, key)
    if nuspec is None:
        return None, f"no .nuspec found for {key}, so its .NET release cannot be checked.", False
    name, _, version = key.partition("/")
    try:
        if not ships_per_release(name, nuspec):
            return None, None, False
    except ET.ParseError as error:
        return None, f"the .nuspec of {key} is not readable XML ({error}).", False
    head = version.split(".", 1)[0]
    if not head.isdigit():
        return None, f"{key}: version {version} does not start with a number, so its .NET release is unknown.", False
    major = int(head)
    if major <= release:
        return None, None, True
    return (f"{alias} ships {name} {version}, a package of .NET {major}; a {alias} consumer would get .NET {major} "
            f"assemblies. Take the .NET {release} version for {alias} (a per-framework ItemGroup in "
            f"Directory.Packages.props)."), None, True


def check(assets: dict) -> tuple[list[str], list[str], int]:
    """(violations, problems that keep a package from being checked, framework/package pairs checked) for one
    project."""
    violations: list[str] = []
    problems: list[str] = []
    checked = 0
    for alias in assets["project"]["frameworks"]:
        release = framework_release(alias)
        if release is None:
            continue
        if framework_targets(assets, alias) is None:
            problems.append(f"no restore targets for {alias} (keys: {', '.join(assets['targets'])}).")
            continue
        for key in sorted(shipped_for(assets, alias)):
            violation, problem, counted = _check_package(assets, alias, release, key)
            checked += counted
            if violation:
                violations.append(violation)
            if problem:
                problems.append(problem)
    return violations, problems, checked


def main() -> int:
    assets_files = sorted(glob.glob("src/*/obj/project.assets.json"))
    if not assets_files:
        print("::error::No src/*/obj/project.assets.json found; run the .NET release gate after restore.")
        return 1
    failures = 0
    checked = 0
    for assets_path in assets_files:
        with open(assets_path, encoding="utf-8") as f:
            assets = json.load(f)
        project = assets_path.replace("\\", "/").split("/obj/", 1)[0]
        violations, problems, count = check(assets)
        checked += count
        for message in violations + problems:
            print(f"::error::{project}: {message}")
        failures += len(violations) + len(problems)
    print(f"Checked {checked} pair(s) of target framework and shipped .NET package; {failures} problem(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

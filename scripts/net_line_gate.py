""".NET release gate for the packages built from a repository.

Reads the NuGet restore output (src/*/obj/project.assets.json) of every packable project and follows, per target
framework, the packages that reach consumers (the license gate's walk: direct package dependencies that are not
PrivateAssets=all, plus their transitive closure). A runtime, ASP.NET Core or extensions package (a System.*,
Microsoft.Extensions.*, Microsoft.AspNetCore.*, Microsoft.Bcl.*, Microsoft.NETCore.* or Microsoft.Win32.* package whose
.nuspec repository is dotnet/dotnet, dotnet/runtime, dotnet/aspnetcore or dotnet/extensions) ships one version per .NET
release, and its major version is that release. Such a package must not be newer than the target framework:
Microsoft.Extensions.Logging 11.0.0 in the net10.0 dependencies would hand .NET 11 assemblies to .NET 10 consumers.
Other packages of those repositories (MSBuild, Roslyn, NuGet) have versions of their own and are not checked. Build-only packages (PrivateAssets=all, such as
SourceLink) do not reach consumers and are not checked.

Usage: net_line_gate.py
Exit code 1 when a package is newer than its target framework, when a shipped package has no .nuspec in the package
folders, or when no restore output is found.
"""

from __future__ import annotations

import glob
import json
import re
import sys
import xml.etree.ElementTree as ET

from license_gate import find_nuspec, shipped_for

# Since .NET 10 the runtime and ASP.NET Core packages are built in the unified dotnet/dotnet repository.
DOTNET_REPOSITORIES = {"github.com/dotnet/dotnet", "github.com/dotnet/runtime", "github.com/dotnet/aspnetcore",
                       "github.com/dotnet/extensions"}
RELEASE_PREFIXES = ("System.", "Microsoft.Extensions.", "Microsoft.AspNetCore.", "Microsoft.Bcl.", "Microsoft.NETCore.",
                    "Microsoft.Win32.")
FRAMEWORK_RE = re.compile(r"^net(\d+)\.\d+")


def repository(nuspec_path: str) -> str:
    """The repository URL of a .nuspec as host and path (github.com/dotnet/runtime); empty when it names none."""
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


def check(assets: dict) -> tuple[list[str], list[str], int]:
    """(violations, packages without a .nuspec, number of .NET packages checked) for one project."""
    violations: list[str] = []
    missing: list[str] = []
    checked = 0
    for alias in assets["project"]["frameworks"]:
        release = framework_release(alias)
        if release is None:
            continue
        for key in sorted(shipped_for(assets, alias)):
            nuspec = find_nuspec(assets, key)
            if nuspec is None:
                missing.append(key)
                continue
            name, _, version = key.partition("/")
            if not ships_per_release(name, nuspec):
                continue
            checked += 1
            major = int(version.split(".", 1)[0])
            if major > release:
                violations.append(f"{alias} ships {name} {version}, a package of .NET {major}; a {alias} consumer "
                                  f"would get .NET {major} assemblies. Take the .NET {release} version for {alias} "
                                  f"(a per-framework ItemGroup in Directory.Packages.props).")
    return violations, missing, checked


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
        violations, missing, count = check(assets)
        checked += count
        for message in violations:
            print(f"::error::{project}: {message}")
        for key in missing:
            print(f"::error::{project}: no .nuspec found for {key}, so its .NET release cannot be checked.")
        failures += len(violations) + len(missing)
    print(f"Checked {checked} shipped .NET package(s) against their target frameworks; {failures} problem(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

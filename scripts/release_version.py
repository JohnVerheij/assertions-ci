"""Version gate for a package release.

The core package (when the repository has one) and the TUnit adapter ship in lockstep: both csproj files must
declare the same <Version>, and a release must run on the tag v<that version>. A dry-run has no tag; it only checks
that the csproj files agree.

Environment:
  PACKAGE        package name without the .TUnit suffix, for example LogAssertions
  HAS_CORE       'true' when the repository ships the framework-agnostic core package, otherwise 'false'
  DRY_RUN        'true' for a dry-run (no tag needed), otherwise 'false'
  GITHUB_REF     the triggering ref; must be refs/tags/v<version> unless DRY_RUN is 'true'
  GITHUB_OUTPUT  optional, receives version=<version> and prerelease=<true|false>
Exit code 1 when the versions disagree or the ref is not a release tag.
"""

from __future__ import annotations

import os
import re
import sys
import xml.etree.ElementTree as ET

SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
TAG_PREFIX = "refs/tags/v"


def parse_flag(name: str, value: str) -> bool:
    if value not in ("true", "false"):
        raise ValueError(f"{name} must be 'true' or 'false', got {value!r}")
    return value == "true"


def read_version(csproj_path: str) -> str:
    root = ET.parse(csproj_path).getroot()
    versions = [element.text.strip() for element in root.iter("Version") if element.text and element.text.strip()]
    if len(versions) != 1:
        raise ValueError(f"{csproj_path}: expected exactly one <Version>, found {len(versions)}")
    return versions[0]


def tag_version(ref: str) -> str:
    if not ref.startswith(TAG_PREFIX):
        raise ValueError(f"A release must run on a v<version> tag, got ref {ref!r}")
    return ref[len(TAG_PREFIX):]


def project_paths(package: str, has_core: bool, root: str = ".") -> list[str]:
    paths = [os.path.join(root, "src", package, f"{package}.csproj")] if has_core else []
    paths.append(os.path.join(root, "src", f"{package}.TUnit", f"{package}.TUnit.csproj"))
    return paths


def resolve(package: str, has_core: bool, dry_run: bool, ref: str, root: str = ".") -> str:
    declared = {path: read_version(path) for path in project_paths(package, has_core, root)}
    # The adapter is always the last project; a dry-run releases what the csproj files declare.
    expected = list(declared.values())[-1] if dry_run else tag_version(ref)
    if not SEMVER.match(expected):
        raise ValueError(f"Version {expected!r} is not a semantic version")
    mismatches = [f"{path} declares {version}" for path, version in declared.items() if version != expected]
    if mismatches:
        raise ValueError(f"Version mismatch, expected {expected}: " + "; ".join(mismatches))
    return expected


def main() -> int:
    try:
        package = os.environ["PACKAGE"]
        has_core = parse_flag("HAS_CORE", os.environ.get("HAS_CORE", "true"))
        dry_run = parse_flag("DRY_RUN", os.environ.get("DRY_RUN", "false"))
        version = resolve(package, has_core, dry_run, os.environ.get("GITHUB_REF", ""))
    except (KeyError, OSError, ValueError, ET.ParseError) as error:
        print(f"::error::{error}")
        return 1

    prerelease = "true" if "-" in version else "false"
    print(f"Version {version} (prerelease: {prerelease}, dry-run: {str(dry_run).lower()})")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"version={version}\nprerelease={prerelease}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

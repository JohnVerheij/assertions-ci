"""License gate for the packages built from a repository.

Reads the NuGet restore output (src/*/obj/project.assets.json) of every packable project, follows the
dependency graph that ships to consumers (direct package dependencies that are not PrivateAssets=all,
plus their transitive closure), and checks each package's license from its .nuspec.

Policy: MIT is always accepted. Anything else must be listed in LICENSE_ALLOWLIST, one entry per line as
`PackageId=<accepted license>`, where <accepted license> is the SPDX expression from the nuspec, or `file`
for a package that ships a license file instead of an expression.

Environment:
  LICENSE_ALLOWLIST   optional, newline-separated `PackageId=license` entries
  GITHUB_STEP_SUMMARY optional, receives a markdown table of every checked package
Exit code 1 when a package is not accepted.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

ALWAYS_ALLOWED = {"MIT"}


def parse_allowlist(text: str) -> dict[str, str]:
    allow: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, license_value = line.partition("=")
        if not sep or not name.strip() or not license_value.strip():
            raise ValueError(f"Invalid allowlist entry {raw!r}; expected PackageId=license")
        allow[name.strip().lower()] = license_value.strip()
    return allow


def expression_accepted(expression: str, extra: str | None) -> bool:
    """True when the SPDX expression is satisfied by MIT (or the allowlisted license)."""
    accepted = set(ALWAYS_ALLOWED)
    if extra:
        if extra == expression:
            return True
        accepted.add(extra)
    expression = expression.strip().strip("()")
    for alternative in re.split(r"\s+OR\s+", expression):
        parts = [p.strip().strip("()") for p in re.split(r"\s+AND\s+", alternative)]
        if all(part in accepted for part in parts):
            return True
    return False


def read_license(nuspec_path: str) -> tuple[str, str]:
    """Returns (kind, value): ('expression', 'MIT'), ('file', 'LICENSE.txt'), ('url', ...) or ('none', '')."""
    root = ET.parse(nuspec_path).getroot()
    license_el = None
    license_url = None
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "license":
            license_el = el
        elif tag == "licenseUrl":
            license_url = (el.text or "").strip()
    if license_el is not None:
        kind = license_el.get("type", "expression")
        return kind, (license_el.text or "").strip()
    if license_url:
        return "url", license_url
    return "none", ""


def find_target(targets: dict, name: str) -> str | None:
    prefix = name.lower() + "/"
    for key in targets:
        if key.lower().startswith(prefix):
            return key
    return None


def shipped_packages(assets: dict) -> set[str]:
    """Keys like 'Name/Version' of every package that reaches a consumer of this project."""
    result: set[str] = set()
    for alias, framework in assets["project"]["frameworks"].items():
        targets = assets["targets"].get(alias) or next(iter(assets["targets"].values()))
        queue = []
        for name, dep in framework.get("dependencies", {}).items():
            if dep.get("target") != "Package" or dep.get("suppressParent") == "All":
                continue
            key = find_target(targets, name)
            if key:
                queue.append(key)
        while queue:
            key = queue.pop()
            if key in result or targets.get(key, {}).get("type") != "package":
                continue
            result.add(key)
            for child in targets[key].get("dependencies", {}):
                child_key = find_target(targets, child)
                if child_key:
                    queue.append(child_key)
    return result


def main() -> int:
    allow = parse_allowlist(os.environ.get("LICENSE_ALLOWLIST", ""))
    assets_files = sorted(glob.glob("src/*/obj/project.assets.json"))
    if not assets_files:
        print("::error::No src/*/obj/project.assets.json found; run the license gate after restore.")
        return 1

    rows: list[tuple[str, str, str, str]] = []
    failures = 0
    seen: set[str] = set()
    for assets_path in assets_files:
        with open(assets_path, encoding="utf-8") as f:
            assets = json.load(f)
        folders = list(assets.get("packageFolders", {}).keys())
        for key in sorted(shipped_packages(assets)):
            if key in seen:
                continue
            seen.add(key)
            name, _, version = key.partition("/")
            library = assets["libraries"].get(key, {})
            nuspec = None
            for folder in folders:
                candidate = os.path.join(folder, library.get("path", key.lower()), name.lower() + ".nuspec")
                if os.path.exists(candidate):
                    nuspec = candidate
                    break
            if nuspec is None:
                rows.append((name, version, "nuspec not found", "FAIL"))
                failures += 1
                continue
            kind, value = read_license(nuspec)
            extra = allow.get(name.lower())
            if kind == "expression":
                ok = expression_accepted(value, extra)
                shown = value
            elif kind == "file":
                ok = extra == "file"
                shown = f"file: {value}"
            else:
                ok = False
                shown = f"{kind}: {value}" if value else kind
            rows.append((name, version, shown, "ok" if ok else "FAIL"))
            if not ok:
                failures += 1
                print(f"::error::{name} {version} has license '{shown}', which the policy does not accept. "
                      f"Add '{name}=<license>' to license-allowlist only after review.")

    width = max((len(r[0]) for r in rows), default=10)
    for name, version, shown, verdict in rows:
        print(f"{verdict:4}  {name:<{width}}  {version:<12}  {shown}")
    print(f"Checked {len(rows)} shipped package(s); {failures} not accepted.")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### License gate\n\n| Package | Version | License | Verdict |\n|---|---|---|---|\n")
            for name, version, shown, verdict in rows:
                f.write(f"| {name} | {version} | {shown} | {verdict} |\n")
            f.write(f"\n{len(rows)} shipped package(s) checked; {failures} not accepted.\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

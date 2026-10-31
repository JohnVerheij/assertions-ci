"""Dependency snapshot for GitHub's dependency graph, built from the NuGet restore output.

Reads every src/*/obj/project.assets.json and tests/*/obj/project.assets.json and writes one manifest per project:
every resolved package with its exact version, whether it is a direct or an indirect dependency, and its scope.
Packages that reach consumers of a src project (the same walk as the license gate) are "runtime"; everything else
(analyzers, build-time packages, every package of a test project) is "development". The output is the request body
of the dependency submission API (POST /repos/{owner}/{repo}/dependency-graph/snapshots).

Environment:
  GITHUB_SHA, GITHUB_REF, GITHUB_RUN_ID, GITHUB_REPOSITORY, GITHUB_SERVER_URL   set by GitHub Actions
  DETECTOR_VERSION   optional, the assertions-ci commit that produced the snapshot
Usage: dependency_snapshot.py <output.json>
Exit code 1 when no restore output is found or a required variable is missing.
"""

from __future__ import annotations

import datetime
import glob
import json
import os
import sys

from license_gate import find_target, shipped_packages

DETECTOR_NAME = "assertions-ci"
DETECTOR_URL = "https://github.com/JohnVerheij/assertions-ci"
CORRELATOR = "assertions-ci dependency-graph"


def purl(name: str, version: str) -> str:
    return f"pkg:nuget/{name}@{version}"


def manifest_path(assets: dict, root: str) -> str:
    project = assets["project"]["restore"]["projectPath"]
    return os.path.relpath(project, root).replace("\\", "/")


def resolved_packages(assets: dict, runtime_scope: bool) -> dict[str, dict]:
    runtime = shipped_packages(assets) if runtime_scope else set()
    resolved: dict[str, dict] = {}
    for alias, framework in assets["project"]["frameworks"].items():
        targets = assets["targets"].get(alias) or next(iter(assets["targets"].values()))
        direct = {name.lower() for name, dep in framework.get("dependencies", {}).items() if dep.get("target") == "Package"}
        for key, entry in targets.items():
            if entry.get("type") != "package":
                continue
            name, version = key.split("/", 1)
            children = sorted(purl(*child_key.split("/", 1))
                              for child in entry.get("dependencies", {})
                              if (child_key := find_target(targets, child)) and targets[child_key].get("type") == "package")
            package = {
                "package_url": purl(name, version),
                "relationship": "direct" if name.lower() in direct else "indirect",
                "scope": "runtime" if key in runtime else "development",
                "dependencies": children,
            }
            previous = resolved.get(package["package_url"])
            if previous:
                # Seen for another target framework: direct wins and the dependencies merge. The scope is the
                # same, because the runtime set covers all frameworks.
                if previous["relationship"] == "direct":
                    package["relationship"] = "direct"
                package["dependencies"] = sorted(set(previous["dependencies"]) | set(children))
            resolved[package["package_url"]] = package
    return dict(sorted(resolved.items()))


def manifest(assets: dict, root: str) -> dict:
    path = manifest_path(assets, root)
    return {"name": path, "file": {"source_location": path},
            "resolved": resolved_packages(assets, runtime_scope=path.startswith("src/"))}


def snapshot(manifests: dict[str, dict], env: dict[str, str], scanned: str) -> dict:
    server = env.get("GITHUB_SERVER_URL", "https://github.com")
    return {
        "version": 0,
        "sha": env["GITHUB_SHA"],
        "ref": env["GITHUB_REF"],
        "job": {
            "correlator": CORRELATOR,
            "id": env["GITHUB_RUN_ID"],
            "html_url": f"{server}/{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}",
        },
        "detector": {"name": DETECTOR_NAME, "version": env.get("DETECTOR_VERSION") or "local", "url": DETECTOR_URL},
        "scanned": scanned,
        "manifests": manifests,
    }


def main(argv: list[str], root: str = ".") -> int:
    if len(argv) != 2:
        print("usage: dependency_snapshot.py <output.json>")
        return 1
    files = sorted(glob.glob(os.path.join(root, "src", "*", "obj", "project.assets.json"))
                   + glob.glob(os.path.join(root, "tests", "*", "obj", "project.assets.json")))
    if not files:
        print("::error::No project.assets.json under src/ or tests/; run dotnet restore first")
        return 1
    manifests: dict[str, dict] = {}
    for path in files:
        with open(path, encoding="utf-8") as handle:
            entry = manifest(json.load(handle), os.path.abspath(root))
        manifests[entry["name"]] = entry
    scanned = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        body = snapshot(manifests, dict(os.environ), scanned)
    except KeyError as error:
        print(f"::error::Missing environment variable {error}")
        return 1
    with open(argv[1], "w", encoding="utf-8", newline="\n") as handle:
        json.dump(body, handle, indent=2)
        handle.write("\n")
    for name, entry in manifests.items():
        packages = entry["resolved"].values()
        runtime = sum(1 for package in packages if package["scope"] == "runtime")
        print(f"{name}: {len(packages)} packages ({runtime} runtime)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

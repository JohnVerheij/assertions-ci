# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.0] - 2026-10-31: dependency graph and provenance bundles

Minor release. Callers of `package-ci.yml` and `package-publish` need no change; `dependency-graph.yml` is opt-in
through one job in the repository's `ci.yml`.

### Added

- **`dependency-graph.yml`**, a reusable workflow that submits the resolved NuGet dependencies to GitHub's
  dependency graph. A read-only job restores in locked mode and builds the snapshot from `project.assets.json`;
  a separate job with `contents: write`, which runs no project code, submits it. The snapshot lists every package
  with its exact version, direct or indirect, and runtime or development scope. Dependabot alerts then match the
  real versions.
- **Provenance bundle on GitHub releases.** `package-publish` attaches the Sigstore bundle of the provenance
  attestation as `<Package>.<version>.intoto.jsonl`, so a package can also be verified offline
  (`gh attestation verify --bundle`).

### Changed

- `package-ci.yml` restores with `--locked-mode`. The repositories already enable locked mode on GitHub Actions;
  the flag makes it explicit where the restore runs.

## [1.1.0] - 2026-10-31: release builds and the publish action

Minor release: the release path for the package repositories. Callers of `package-ci.yml` need no change; a
new, non-required `Upload coverage` check appears next to `Build, test & pack`.

### Added

- **Release builds in `package-ci.yml`** (`release: true`). Every CI gate runs on the exact packages that ship, and
  the job adds:
  - a version gate (the tag must match the csproj versions);
  - release notes from the CHANGELOG;
  - a CycloneDX SBOM (build-time packages listed with scope `excluded`) and an OpenVEX document per package;
  - a `SHA256SUMS` file.

  All of it is uploaded as the `release-packages` artifact. A run without a tag is a dry-run.
- **`package-publish`**, a composite action for the publish job of a package repository's `release.yml`. It runs
  no project code:
  - checks that the tag is signed, annotated, unmoved and on the default branch;
  - checks every release file against the build job's checksums;
  - attests provenance (`actions/attest`) and SBOMs;
  - pushes to NuGet through Trusted Publishing;
  - creates the GitHub release with `gh`.
- **Release workflow** for this repository: a signed `vX.Y.Z` tag creates the GitHub release from the CHANGELOG.

### Changed

- The Codecov upload moved from the build job to its own `Upload coverage` job, the only job with an OIDC token,
  so build and test code no longer runs next to a credential. The caller's `ci.yml` doesn't change.

## [1.0.0] - 2026-10-31: reusable package CI workflow

First release. The SseAssertions repository ran it as a pilot before release, including the Native AOT gate on
Linux and the Codecov OIDC upload.

### Added

- **`package-ci.yml`**, a reusable workflow that builds, tests and packs one package repository by convention
  (inputs `package` and `has-core`). Tests run with coverage; the reports are merged, uploaded to Codecov through
  OIDC, and gated at 90% line and branch coverage by default.
- **License gate** (`scripts/license_gate.py`): every package that ships to consumers must be MIT or be listed in
  the `license-allowlist` input.
- **Package-content check** (`expected-package-files` input) for files such as `build/*.targets` that unit tests
  cannot see.
- **Smoke test against the exact packed version** of the adapter, passed as `SmokePackageVersion`.
- **Native AOT gate** that publishes the smoke consumer with `PublishAot` in both restore and publish, verifies a
  native executable was produced, and runs it.
- **actionlint** and **script test** workflows; zizmor and CodeQL now run on every change, so all four can be
  required status checks.

[unreleased]: https://github.com/JohnVerheij/assertions-ci/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/JohnVerheij/assertions-ci/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/JohnVerheij/assertions-ci/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/JohnVerheij/assertions-ci/releases/tag/v1.0.0

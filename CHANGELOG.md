# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`package-release`**, a composite action for a package repository's `release.yml`. It checks that the tag
  matches the csproj versions, takes the release notes from the CHANGELOG, runs every test suite, packs, writes a
  CycloneDX SBOM (build-time packages listed with scope `excluded`) and an OpenVEX document per package, attests provenance (`actions/attest`) and SBOMs, pushes to
  NuGet through Trusted Publishing, and creates the GitHub release with `gh`.
- **Dry-run mode** (`dry-run: 'true'`) that stops before the attestations and uploads the packages, SBOMs, VEX
  documents and release notes as a workflow artifact, so the release path can be tested without a tag.
- **Release workflow** for this repository: a pushed `vX.Y.Z` tag creates the GitHub release from the CHANGELOG.

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

[unreleased]: https://github.com/JohnVerheij/assertions-ci/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/JohnVerheij/assertions-ci/releases/tag/v1.0.0

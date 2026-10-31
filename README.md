# assertions-ci

Shared GitHub Actions building blocks for the [DotNetAssertions](https://dotnetassertions.dev) package family,
so a CI or release fix lands once instead of once per package repository: a reusable CI workflow, and a composite
action for the release workflow.

> **Scope:** internal tooling for the `*Assertions.TUnit` repositories. It is public so those public repositories
> can call it. It is not a general-purpose product and makes no stability promise outside the family.

## Contents

| Path | Purpose |
| --- | --- |
| `.github/workflows/package-ci.yml` | Reusable CI for one package repository: build, tests with coverage, license gate, pack, package-content check, smoke test against the packed package, Native AOT gate |
| `.github/actions/package-release/` | Composite action for a package repository's `release.yml`: version gate, release notes, build, tests, pack, SBOM and VEX, attestations, NuGet push, GitHub release; or a dry-run |
| `scripts/license_gate.py` | License gate used by `package-ci.yml`, with unit tests in `scripts/test_license_gate.py` |
| `scripts/release_version.py`, `scripts/release_notes.py` | Version gate and CHANGELOG extraction used by the release action, with unit tests |
| `.github/workflows/actionlint.yml` | Lints every workflow (syntax, expressions, shellcheck) |
| `.github/workflows/zizmor.yml` | Security audit of the workflows (blocks on findings) |
| `.github/workflows/codeql.yml` | CodeQL analysis of the workflows (`actions` language) |
| `.github/workflows/scripts.yml` | Runs the script unit tests |
| `.github/workflows/scorecard.yml` | OpenSSF Scorecard supply-chain analysis |
| `.github/workflows/dependency-review.yml` | Blocks pull requests that introduce a vulnerable dependency |
| `.github/workflows/release.yml` | Creates this repository's GitHub release from the CHANGELOG when a `vX.Y.Z` tag is pushed |

## Using `package-ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  ci:
    uses: JohnVerheij/assertions-ci/.github/workflows/package-ci.yml@<commit-sha> # vX.Y.Z
    with:
      package: LogAssertions
    permissions:
      contents: read
      id-token: write   # Codecov upload through OIDC
```

### Inputs

| Input | Default | Meaning |
| --- | --- | --- |
| `package` | (required) | Package name without the `.TUnit` suffix, for example `LogAssertions` |
| `has-core` | `true` | `false` when the repository ships only the adapter package (no framework-agnostic core) |
| `line-threshold` | `0.90` | Minimum merged line coverage |
| `branch-threshold` | `0.90` | Minimum merged branch coverage |
| `expected-package-files` | empty | Newline-separated paths that must be in the adapter `.nupkg`, for example `build/SnapshotAssertions.TUnit.targets` |
| `license-allowlist` | empty | Newline-separated `PackageId=license` entries accepted besides MIT, for example `Grpc.Core.Api=Apache-2.0`; use `PackageId=file` for a package that ships a license file |

### Repository contract

The workflow finds everything by convention:

| Path | Role |
| --- | --- |
| `global.json` | SDK version |
| `src/<Package>/` | Framework-agnostic core (when `has-core`) |
| `src/<Package>.TUnit/` | TUnit adapter |
| `tests/<Package>.Tests/` | Core tests, run with coverage (when `has-core`) |
| `tests/<Package>.TUnit.Tests/` | Adapter tests, run with coverage |
| `tests/<Package>.TUnit.SnapshotTests/` | Public API snapshot tests |
| `tests/<Package>.TUnit.SmokeTest/` | External consumer of the packed adapter; assembly name `Smoke.Consumer` |
| `.config/codecoverage.settings.xml` | Coverage scope |
| `.config/dotnet-tools.json` | Must include `dotnet-reportgenerator-globaltool` when `has-core` (two coverage reports are merged) |

The smoke test project references the adapter as
`<PackageReference Include="<Package>.TUnit" Version="$(SmokePackageVersion)" />` with a `*-*` default for
`SmokePackageVersion`, so CI tests exactly the version it just packed. Codecov uses OIDC, so the repository needs
no `CODECOV_TOKEN` secret.

## Using `package-release`

The action runs inside the caller's job, so the OIDC token, the NuGet Trusted Publishing policy and the attestation
signer identity all belong to the package repository. It checks out the repository and sets up .NET itself.

```yaml
name: Release

on:
  push:
    tags:
      - 'v[0-9]+.[0-9]+.[0-9]+'
      - 'v[0-9]+.[0-9]+.[0-9]+-*'
  workflow_dispatch:   # dry-run: builds, tests and packs, publishes nothing

permissions:
  contents: read

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false   # never cancel an in-progress release

jobs:
  publish:
    name: Build, pack & publish
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    timeout-minutes: 20
    permissions:
      contents: write       # GitHub release
      id-token: write       # NuGet Trusted Publishing and Sigstore signing
      attestations: write   # provenance and SBOM attestations
    environment:
      name: nuget
      url: https://www.nuget.org/packages/LogAssertions/
    steps:
      - name: Release
        uses: JohnVerheij/assertions-ci/.github/actions/package-release@<commit-sha> # vX.Y.Z
        with:
          package: LogAssertions

  dry-run:
    name: Release dry-run
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    timeout-minutes: 20
    permissions:
      contents: read
    steps:
      - name: Release dry-run
        uses: JohnVerheij/assertions-ci/.github/actions/package-release@<commit-sha> # vX.Y.Z
        with:
          package: LogAssertions
          dry-run: 'true'
```

The dry-run job has no environment and no write permission, so it can't publish. It uploads the packages, SBOMs,
VEX documents and release notes as the `release-dry-run` workflow artifact.

### Inputs

| Input | Default | Meaning |
| --- | --- | --- |
| `package` | (required) | Package name without the `.TUnit` suffix |
| `has-core` | `'true'` | `'false'` when the repository ships only the adapter package |
| `dry-run` | `'false'` | `'true'` to stop before the attestations; no tag is needed |

### What a release does

1. Checks that the tag is `v<version>` and that the core and adapter csproj files both declare `<Version>`
   `<version>` (a dry-run only checks that the two agree).
2. Takes the release notes from the `## [<version>]` section of `CHANGELOG.md` and fails when it is missing or empty.
3. Restores, builds, and runs the core (when `has-core`), adapter and snapshot suites.
4. Packs each package and writes a CycloneDX 1.6 SBOM and an OpenVEX document next to it.
5. Attests build provenance for every `.nupkg` and `.snupkg`, and the CycloneDX SBOM of each `.nupkg`.
6. Pushes to nuget.org through Trusted Publishing (`NuGet/login`), and creates the GitHub release with the packages,
   SBOMs and VEX documents attached; a version with a `-` suffix becomes a prerelease.

Besides the CI contract above, the repository needs `cyclonedx` in `.config/dotnet-tools.json` and a Trusted
Publishing policy on nuget.org for `release.yml` with environment `nuget`.

## Versioning

Releases are signed tags (`vX.Y.Z`); see [CHANGELOG.md](CHANGELOG.md). Callers pin a release by its commit SHA with
the tag as a comment, which keeps the reference immutable and lets Renovate propose updates. The workflow checks out
`scripts/` at its own commit (`job.workflow_sha`), and the release action runs the scripts from its own download,
so the scripts always match the pinned version.

## Security

See [SECURITY.md](SECURITY.md) for how to report a vulnerability.

## License

[MIT](LICENSE)

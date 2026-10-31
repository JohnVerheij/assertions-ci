# assertions-ci

Shared GitHub Actions building blocks for the [DotNetAssertions](https://dotnetassertions.dev) package family,
so a CI or release fix lands once instead of once per package repository: a reusable CI workflow that is also the
build stage of a release, and a composite action for the publish stage.

> **Scope:** internal tooling for the `*Assertions.TUnit` repositories. It is public so those public repositories
> can call it. It is not a general-purpose product and makes no stability promise outside the family.

## Contents

| Path | Purpose |
| --- | --- |
| `.github/workflows/package-ci.yml` | Reusable CI for one package repository: build, tests with coverage, license gate, pack, package-content check, smoke test against the packed package, Native AOT gate. With `release: true`, the build stage of a release |
| `.github/actions/package-publish/` | Composite action for the publish job of a package repository's `release.yml`: tag and checksum checks, attestations, NuGet push, GitHub release |
| `scripts/license_gate.py` | License gate used by `package-ci.yml`, with unit tests in `scripts/test_license_gate.py` |
| `scripts/release_version.py`, `scripts/release_notes.py`, `scripts/verify_tag.py` | Version gate, CHANGELOG extraction and tag check for releases, with unit tests |
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
| `release` | `false` | Release build; see [Releasing](#releasing-package-ciyml--package-publish) |

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
`SmokePackageVersion`, so CI tests exactly the version it just packed.

The build job can only read the repository. The coverage report goes to Codecov from a separate job, the only
one with an OIDC token, so build and test code never runs next to a credential. Codecov uses OIDC, so the
repository needs no `CODECOV_TOKEN` secret.

## Releasing: `package-ci.yml` + `package-publish`

A release has two jobs in the package repository's own `release.yml`:

1. **build**: `package-ci.yml` with `release: true`.
   - It runs every CI gate (tests, coverage, license gate, smoke test, Native AOT) on the exact packages that
     ship.
   - It adds the version gate, the release notes, and a CycloneDX SBOM and an OpenVEX document per package.
   - It uploads all of it with a `SHA256SUMS` file as the `release-packages` artifact.
   - The job can only read the repository, so build and test code never runs next to a publishing credential.
2. **publish**: the `package-publish` action, in a job with the `nuget` environment and the write permissions.
   It runs no project code:
   - checks the tag and the release files;
   - attests provenance and SBOMs;
   - pushes to nuget.org through Trusted Publishing;
   - creates the GitHub release.

   Because the action runs inside the caller's job, the OIDC token, the NuGet Trusted Publishing policy and the
   attestation signer identity all belong to the package repository.

A manual run (`workflow_dispatch`) is a dry-run: only the build job runs. Its `release-packages` artifact shows
exactly what a release would publish.

```yaml
name: Release

on:
  push:
    tags:
      - 'v[0-9]+.[0-9]+.[0-9]+'
      - 'v[0-9]+.[0-9]+.[0-9]+-*'
  workflow_dispatch:   # dry-run: the build job only, nothing is published

permissions:
  contents: read

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false   # never cancel an in-progress release

jobs:
  build:
    uses: JohnVerheij/assertions-ci/.github/workflows/package-ci.yml@<commit-sha> # vX.Y.Z
    with:
      package: LogAssertions
      release: true
    permissions:
      contents: read
      id-token: write   # ceiling for the Codecov job, which a release skips; the build job itself only reads

  publish:
    name: Publish
    needs: build
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    timeout-minutes: 15
    permissions:
      contents: write       # GitHub release
      id-token: write       # NuGet Trusted Publishing and Sigstore signing
      attestations: write   # provenance and SBOM attestations
    environment:
      name: nuget
      url: https://www.nuget.org/packages/LogAssertions/
    steps:
      - name: Publish
        uses: JohnVerheij/assertions-ci/.github/actions/package-publish@<commit-sha> # vX.Y.Z
        with:
          package: LogAssertions
          version: ${{ needs.build.outputs.version }}
          checksum: ${{ needs.build.outputs.checksum }}
```

A repository without a core package passes `has-core: false` to both.

### What the build job adds with `release: true`

1. **Version gate.**
   - On a tag `v<version>`, the core and adapter csproj files must both declare `<Version>` `<version>`.
   - On a branch (a dry-run), the two must agree with each other.
2. **Release notes** from the `## [<version>]` section of `CHANGELOG.md`; a missing or empty section fails.
3. **SBOM and VEX** per package, after all gates passed:
   - a CycloneDX 1.6 SBOM, with build-time packages listed with scope `excluded`;
   - an OpenVEX document with no statements yet.
4. **`SHA256SUMS`** over all release files. Its own hash is the `checksum` output.

### What `package-publish` does

1. Checks that the tag is an annotated tag with a signature GitHub verifies, that it still points to the commit
   the build job built, and that this commit is on the default branch.
2. Downloads the artifact, which fails on a digest mismatch with the artifact store. Then it checks the
   `SHA256SUMS` hash against the build job's `checksum` output, checks every file against `SHA256SUMS`, and
   requires exactly the expected set of files.
3. Attests build provenance for every `.nupkg` and `.snupkg`, and the CycloneDX SBOM of each `.nupkg`.
4. Pushes to nuget.org with `NuGet/login` (Trusted Publishing; no API key secret) and `--skip-duplicate`, so a
   re-run is safe.
5. Creates the GitHub release with the packages, SBOMs, VEX documents and `SHA256SUMS` attached. `gh` creates a
   draft, uploads the assets and then publishes, so immutable releases work. A version with a `-` suffix becomes a
   prerelease.

| Input | Default | Meaning |
| --- | --- | --- |
| `package` | (required) | Package name without the `.TUnit` suffix |
| `has-core` | `'true'` | `'false'` when the repository ships only the adapter package |
| `version` | (required) | The build job's `version` output |
| `checksum` | (required) | The build job's `checksum` output |

### Repository setup for releases

Besides the CI contract above:
- **Tool manifest:** `.config/dotnet-tools.json` includes `cyclonedx`.
- **NuGet:** a Trusted Publishing policy on nuget.org for `release.yml` with environment `nuget`.
- **Signed tags:** release tags are signed annotated tags (`git tag -s`).
- **Repository settings:**
  - *Enable release immutability*, so a published release's assets and tag can't change.
  - Limit the `nuget` environment's deployments to tags matching `v*.*.*`.

## Versioning

Releases are signed tags (`vX.Y.Z`); see [CHANGELOG.md](CHANGELOG.md). Callers pin a release by its commit SHA with
the tag as a comment, which keeps the reference immutable and lets Renovate propose updates. The workflow checks out
`scripts/` at its own commit (`job.workflow_sha`), and `package-publish` runs the scripts from its own download,
so the scripts always match the pinned version.

## Security

See [SECURITY.md](SECURITY.md) for how to report a vulnerability.

## License

[MIT](LICENSE)

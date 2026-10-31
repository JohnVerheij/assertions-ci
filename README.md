# assertions-ci

Shared GitHub Actions building blocks for the [DotNetAssertions](https://dotnetassertions.dev) package family,
so a CI fix lands once instead of once per package repository. Today it holds the reusable CI workflow; composite
actions for the release workflow follow in a later release.

> **Scope:** internal tooling for the `*Assertions.TUnit` repositories. It is public so those public repositories
> can call it. It is not a general-purpose product and makes no stability promise outside the family.

## Contents

| Path | Purpose |
| --- | --- |
| `.github/workflows/package-ci.yml` | Reusable CI for one package repository: build, tests with coverage, license gate, pack, package-content check, smoke test against the packed package, Native AOT gate |
| `scripts/license_gate.py` | License gate used by `package-ci.yml`, with unit tests in `scripts/test_license_gate.py` |
| `.github/workflows/actionlint.yml` | Lints every workflow (syntax, expressions, shellcheck) |
| `.github/workflows/zizmor.yml` | Security audit of the workflows (blocks on findings) |
| `.github/workflows/codeql.yml` | CodeQL analysis of the workflows (`actions` language) |
| `.github/workflows/scripts.yml` | Runs the script unit tests |
| `.github/workflows/scorecard.yml` | OpenSSF Scorecard supply-chain analysis |
| `.github/workflows/dependency-review.yml` | Blocks pull requests that introduce a vulnerable dependency |

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

## Versioning

Releases are signed tags (`vX.Y.Z`); see [CHANGELOG.md](CHANGELOG.md). Callers pin a release by its commit SHA with
the tag as a comment, which keeps the reference immutable and lets Renovate propose updates. The workflow checks out
`scripts/` at its own commit (`job.workflow_sha`), so the scripts always match the pinned workflow.

## Security

See [SECURITY.md](SECURITY.md) for how to report a vulnerability.

## License

[MIT](LICENSE)

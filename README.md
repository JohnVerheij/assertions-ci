# assertions-ci

Shared GitHub Actions building blocks for the [DotNetAssertions](https://dotnetassertions.dev) package family,
so a CI or release fix lands once instead of once per package repository: a reusable CI workflow that is also the
build stage of a release, and a composite action for the publish stage.

> **Scope:** internal tooling for the `*Assertions.TUnit` repositories. It is public so those public repositories
> can call it. It is not a general-purpose product and makes no stability promise outside the family.

## Contents

| Path | Purpose |
| --- | --- |
| `.github/workflows/package-ci.yml` | Reusable CI for one package repository: build, tests with coverage on each target framework, license gate, pack, API compatibility suppression check, NuGet package validation, XML documentation check, package-content check, smoke test against the packed package, README code samples, Native AOT gate. With `release: true`, the build stage of a release |
| `.github/actions/package-publish/` | Composite action for the publish job of a package repository's `release.yml`: tag and checksum checks, attestations, NuGet push, GitHub release |
| `.github/workflows/package-lint.yml` | Reusable family lint: CHANGELOG format, PackageTags, known British spellings, README facts, the shared files against the family templates, and typos with the family dictionary |
| `.github/workflows/package-docs.yml` | Reusable documentation site: build, internal link check, docfx, GitHub Pages deployment |
| `.github/workflows/package-codeql.yml` | Reusable CodeQL analysis (the C# of the shipped projects under `src/`, and the repository's workflows), with the shared configuration in `codeql/package-config.yml` |
| `.github/workflows/package-zizmor.yml` | Reusable zizmor audit of the repository's workflows |
| `renovate/family.json` | Shared Renovate preset of the package repositories |
| `templates/package/` | The family templates: the files every package repository shares, with placeholders |
| `typos/family.toml` | The family dictionary for typos: excluded generated files and the words that are correct in the family |
| `scripts/family_lint.py`, `scripts/family_sync.py`, `scripts/docs_linkcheck.py`, `scripts/render_templates.py` | The family lint, the template check and sync, the docs link check, and the template rendering for the workflow linters, with unit tests |
| `scripts/xmldoc_check.py`, `scripts/nuget_validation_report.py`, `scripts/coverage_table.py`, `scripts/readme_samples.py` | The package checks of `package-ci.yml` (see [Package checks](#package-checks)), with unit tests |
| `.github/workflows/dependency-graph.yml` | Reusable workflow that submits the resolved NuGet dependencies (exact versions, transitive included) to GitHub's dependency graph |
| `scripts/license_gate.py` | License gate used by `package-ci.yml`, with unit tests in `scripts/test_license_gate.py` |
| `scripts/dependency_snapshot.py` | Builds the dependency snapshot from the restore output, with unit tests |
| `scripts/release_version.py`, `scripts/release_notes.py`, `scripts/verify_tag.py` | Version gate, CHANGELOG extraction and tag check for releases, with unit tests |
| `.github/workflows/actionlint.yml` | Lints every workflow (syntax, expressions, shellcheck), including the workflow templates rendered for a demo package |
| `.github/workflows/zizmor.yml` | Security audit of the workflows, including the rendered workflow templates (blocks on findings) |
| `.github/workflows/codeql.yml` | CodeQL analysis of the workflows (`actions` language) |
| `.github/workflows/scripts.yml` | Runs the script unit tests with coverage and fails below 90% line and branch coverage (coverage.py, hash-pinned in `scripts/requirements-ci.txt`) |
| `.github/workflows/renovate-config.yml` | Validates the family preset, the repository template that extends it and this repository's Renovate configuration with Renovate's own validator (`--strict`; the preset and the template as repository configuration, `--no-global`) |
| `.github/workflows/spelling.yml` | typos with the family dictionary on this repository, so a dictionary change is proven here first |
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
| `readme-samples` | `report` | What a README C# sample that does not compile does: `report` (a warning on its README line) or `enforce` (fails the build); see [README code samples](#readme-code-samples) |
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
| `packages.lock.json` | Lock file per project; the restore runs with `--locked-mode` (the smoke test project has none, because it consumes the package packed in the same run) |
| `.config/dotnet-tools.json` | Must include `dotnet-reportgenerator-globaltool` (the coverage merge: with `has-core`, or when the adapter test project targets more than one framework, there is more than one report), `cyclonedx` (the release SBOM) and `docfx` (the documentation site); `family_sync.py` checks all three |
| `src/*/CompatibilitySuppressions.xml` | ApiCompat suppressions, committed; pack regenerates them, and a changed or new file fails the build |
| `tests/ReadmeSamples.Prelude.cs` | Optional: what the README samples use without declaring it (see [README code samples](#readme-code-samples)) |

### Target frameworks

Each test project's frameworks come from the project itself (`TargetFrameworks`, or `TargetFramework`), read with
`dotnet msbuild -getProperty`. The core, adapter and snapshot suites, the smoke test and the Native AOT gate run
once per framework, and the coverage reports of all runs are merged before the thresholds apply. The SDK comes from
`global.json`, so it must support the newest framework the projects target (the .NET 11 SDK for `net11.0`; the .NET
10 SDK fails with `NETSDK1045`). For every other .NET version the projects target, the workflow installs that
version's SDK for its runtime, and `global.json` keeps selecting the pinned one. So once `global.json` selects the
.NET 11 SDK, a repository adds `net11.0` next to `net10.0` by changing its projects only. A test project must target
`netX.Y` frameworks only.

When `global.json` moves to the .NET 11 SDK, pack writes `CompatibilitySuppressions.xml` without a byte order mark.
The suppression check below compares the file byte for byte (apart from line endings), so commit the file as pack
writes it.

Pack runs package validation against the previous release (`PackageValidationBaselineVersion`). The workflow
packs with `-p:ApiCompatGenerateSuppressionFile=true`, so pack rewrites `CompatibilitySuppressions.xml` instead of
failing, whatever the project sets. The build fails when that changes a committed file or adds one (including one
that a `.gitignore` pattern would hide), so every public API difference from the baseline shows up in the pull
request: run `dotnet pack -p:ApiCompatGenerateSuppressionFile=true` locally and commit the regenerated file. Line
endings don't count.

The comparison leaves out the attributes listed in `.config/apicompat-excluded-attributes.txt` (a family template,
passed to package validation by the `Directory.Build.targets` template): TUnit's `GenerateAssertionAttribute`, whose
expectation message changes with a failure text, and the compiler's state machine attributes, whose argument names a
generated class that is renumbered whenever a method is added. Neither changes what a consumer compiles against, so
the suppression file records only real API differences.

The smoke test project references the adapter as
`<PackageReference Include="<Package>.TUnit" Version="$(SmokePackageVersion)" />` with a `*-*` default for
`SmokePackageVersion`, so CI tests exactly the version it just packed.

The build job can only read the repository. The coverage report goes to Codecov from a separate job, the only
one with an OIDC token, so build and test code never runs next to a credential. Codecov uses OIDC, so the
repository needs no `CODECOV_TOKEN` secret.

### Package checks

Besides the tests, `package-ci.yml` checks what a consumer gets:

| Check | What fails |
| --- | --- |
| Coverage per test run | Nothing: before the merge, a table in the job summary shows each suite's coverage per framework and assembly, so code that only one framework covers shows. The thresholds apply to the merged report |
| NuGet package validation | [Meziantou's validator](https://github.com/meziantou/Meziantou.Framework) on every packed package: SourceLink and a deterministic build, symbols whose sources resolve, XML documentation, readme, license, repository metadata, tags, optimized assemblies. An icon is required from version 1.0.0. The tool's version is pinned in the workflow and updated by Renovate here |
| XML documentation | `scripts/xmldoc_check.py` on the packed XML documentation, which is what an IDE shows: an empty member, a generator placeholder summary (`Generated extension method for ...`), or an `<inheritdoc cref>` (also one inside `<summary>`) that leads to no summary. A summary with only a reference such as `<see cref>` counts. A target is resolved in the same framework where it exists; a member of a documented type without an entry of its own is reported, any other target outside the packages (TUnit, the .NET libraries) is not checked |
| README code samples | See below; `report` by default |

#### README code samples

`scripts/readme_samples.py` turns every C# sample of the root README and the package READMEs (`src/*/README.md`)
into a project, `tests/.readme-samples/` (generated, not committed), and the step builds it against the packed
packages. The project takes the smoke test project's package references, with the packed version and their
per-framework conditions (a dependency with a version per target framework keeps it), and turns implicit usings on,
as in a consumer's project. `#line` directives map every sample line back to its README, so an error
names the README line. With `readme-samples: enforce` the build fails. With `report` it is a warning: the first
ten errors as annotations on their README lines (GitHub shows ten per step) and all of them in the job summary.
The compiler reports errors inside method bodies only once every declaration compiles, so fixing samples comes in
waves: build again after each round until the list is empty.

The conventions:
- A fenced block whose info string starts with `csharp`, `cs` or `c#` is a sample. ` ```csharp no-compile ` opts a
  block out: pseudo code, a deliberately wrong example, a sample of another package.
- Every fenced block of a README must close, and a closing fence has nothing but the fence characters on its line
  (CommonMark). A line such as "\`\`\` More text." does not close a block: GitHub and nuget.org then render the rest of
  the README as code. The step fails on a block that no fence closes and names its README line, in both modes.
- A sample may mix what a consumer writes in different places. Its leading `using` and preprocessor directives go
  to the top of the file, each top-level type declaration into the sample's own namespace, each member declaration (a
  line that starts with an attribute, an access modifier or `readonly`) into a class, and every other line, in order,
  into an async method of that class. A line inside an open string, comment or bracket, or after an unfinished
  statement or declaration (one whose last line does not end in `;` or `}`), stays with the line before it, whatever
  it starts with. A sample with a file-scoped namespace compiles as a file of its own, its namespace prefixed with the
  sample's, so two samples may declare the same types.
- `tests/ReadmeSamples.Prelude.cs` declares what the samples use without declaring it: global usings, types in
  namespace `ReadmeSamples`, and fields or helpers of `public partial class Prelude` there, from which every wrapping
  class derives. A field `protected FakeLogCollector collector = new();` serves every sample that uses `collector`.
- The samples see the packages the smoke test project references. A sample that needs another package (for example
  `Microsoft.Extensions.TimeProvider.Testing` for `FakeTimeProvider`) needs that reference in the smoke test project,
  or the `no-compile` mark when the package would only serve the sample.

## The support workflows

Four reusable workflows replace the copies each package repository used to keep. The repository keeps a thin caller
with its own triggers and permissions; the scripts and configuration come from the workflow's own commit, so they
always match the pinned version. `family_sync.py --write` writes the callers (see
[Family templates](#family-templates)).

| Workflow | Caller needs | What it runs |
| --- | --- | --- |
| `package-lint.yml` | `contents: read` | `scripts/family_lint.py`: the CHANGELOG format, the `<PackageTags>` order, known British spellings in the tracked text files (a word list, not a dictionary), the README facts (the TUnit minimum in every README equals the central TUnit version; the adapter README names every sibling package; the first `SECURITY.md` supported-versions row is the current `X.Y.x` line), `family_sync.py`'s template check, and typos with the family dictionary (`typos/family.toml`; a line ending in a `spellchecker:disable-line` comment is skipped) |
| `package-docs.yml` | input `package`; `contents: read`, `pages: write`, `id-token: write` | Build, Markdown pages from the repository files, `scripts/docs_linkcheck.py`, docfx, and on pushes the GitHub Pages deployment |
| `package-codeql.yml` | `contents: read`, `security-events: write`, `actions: read` | CodeQL for C# (the shipped projects, built) and the workflows, `security-extended` queries, `codeql/package-config.yml` |
| `package-zizmor.yml` | `contents: read`, `actions: read` | zizmor on the repository's workflows, blocking on any finding |

Two workflows stay in each repository on purpose:
- `dependency-review.yml`: its check, `Review dependency changes`, is a required status check. Inside a reusable
  workflow its name would change and block every repository's auto-merge until its ruleset is edited.
- `scorecard.yml`: OpenSSF Scorecard checks the workflow that publishes its results and does not document reusable
  workflows; a rejected publish would silently drop the score.

The family templates keep both identical across the repositories.

## The Renovate preset

`renovate/family.json` is the Renovate configuration of every package repository. A repository's
`.github/renovate.json` only extends it:

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": [
    "github>JohnVerheij/assertions-ci//renovate/family"
  ]
}
```

It reads the preset from this repository's default branch, so a Renovate change lands once for all repositories.
Besides the shared rules (semver for NuGet, the TUnit group, auto-merge of non-major updates, the commit conventions),
it has two family rules:
- **TUnit version literals:** the `TUnit X.Y.Z or later` line of every README, the smoke test's `TUnit` reference and
  the bug-report form move in the same pull request as `Directory.Packages.props`.
- **Packages of the .NET release line** (`dotnet-sdk`, `Microsoft.Extensions.*`, `Microsoft.SourceLink.GitHub`,
  `System.Numerics.Tensors`): a major update waits for approval in the Dependency Dashboard. A package takes the
  dependency version of each target framework's own .NET release (a conditional `ItemGroup` per framework in
  `Directory.Packages.props`), so a new major means a new target framework, not a bump of the existing entries.
  Minor and patch updates stay automatic within each line.

## Family templates

`templates/package/` holds the files every package repository shares, at their path in the repository: the
`.gitattributes` and `.gitignore`, `Directory.Build.props` and `Directory.Build.targets`, the community files, the
docs-site files, the Renovate configuration, and the workflow callers. The callers are stored as
`<name>.yml.template`, so no tool in this repository (actionlint, zizmor, CodeQL) reads them as workflows, and
`docs/docfx.json` as `docfx.json.template`, because its `{{core}}` line is not valid JSON; `family_sync.py` writes them
without the suffix. This repository's own Renovate configuration adds the templates to
its GitHub Actions files, so their action pins stay current, and leaves the `{{assertions-ci}}` placeholder alone.
Placeholders:

| Placeholder | Value |
| --- | --- |
| `{{Package}}` | The package name without `.TUnit`, from `src/<Package>.TUnit/` |
| `{{domain}}` | The documentation domain, the lowercase package name plus `.dev` |
| `{{assertions-ci}}` | The assertions-ci pin of the repository's own `ci.yml` (`<sha> # vX.Y.Z`), so every caller uses the same commit |
| `{{core}}` at the start of a line | The line is kept only when the repository has a core package (`src/<Package>/`) |

```bash
python3 path/to/assertions-ci/scripts/family_sync.py            # check (exit 1 on drift)
python3 path/to/assertions-ci/scripts/family_sync.py --write    # update the repository
```

The check reports every template file that is missing or differs, every obsolete file (the old copies of the scripts
and of the CodeQL configuration), and every local tool missing from `.config/dotnet-tools.json`
(`dotnet-reportgenerator-globaltool`, `cyclonedx`, `docfx`). Pinned versions of other actions are not compared,
because Renovate updates them per repository; `--write` keeps the repository's own pins. The assertions-ci pins of the
callers are compared: each must equal the pin in `ci.yml`, and `--write` sets it. Renovate moves all of them in the same
pull request. `package-lint.yml` runs the check.

A template is shared as a whole: the check reports a local change and `--write` overwrites it. A change one repository
needs goes into the template, and so into every repository. What belongs to one repository stays in the files the
templates leave alone: the project files, `Directory.Packages.props`, `ci.yml` and `release.yml`.

When a template changes in a new assertions-ci release, the Renovate pull request that moves a repository's pin shows
the drift in its lint run. Run `family_sync.py --write` on that pull request's branch and commit the result.

### Adopting 1.4.0 in a package repository

1. Move the pin in `ci.yml` and `release.yml` to the 1.4.0 commit (or take Renovate's digest pull request).
2. Run `family_sync.py --write`, then add any local tool it still reports (`dotnet tool install --local <tool>`).
   The `Directory.Build.props` template sets `LangVersion` 15.0, which needs the .NET 11 SDK, so move `global.json`
   to SDK 11 in the same step. It changes only the C# the source may use: the packages still target `net10.0` and
   `net11.0`, and a C# 15 feature that needs .NET 11 types fails the `net10.0` build.
3. Run `family_lint.py` and fix what it reports (British spellings, the TUnit minimum, the family list, the
   `SECURITY.md` table).
4. The checks of the support workflows get the caller's job as a prefix: `Family lint` becomes `lint / Family lint`,
   and likewise `docs / Build docs`, `codeql / Analyze (csharp)` and `zizmor / Audit GitHub Actions workflows`. None of
   them is a required check today; a ruleset that requires one must name the new check, or every pull request waits
   for a check that never reports.
5. Allow the typos action: in **Settings → Actions → General**, under "Allow select actions", add `crate-ci/typos@*`.
   A repository that allows only its own, GitHub's and Marketplace-verified actions refuses to start the lint
   workflow otherwise (`startup_failure`: "The action crate-ci/typos@... is not allowed"). Then fix what typos
   reports. A word that is correct in the family goes into `typos/family.toml` here, for all repositories.
6. Build the README samples locally (the step's commands, after a pack) and fix the samples or add
   `tests/ReadmeSamples.Prelude.cs`; mark what cannot compile `no-compile`. When every sample compiles, set
   `readme-samples: enforce` in `ci.yml` and `release.yml`.
7. To target .NET 11 next to .NET 10, see [Target frameworks](#target-frameworks).

### Adopting 1.5.0 in a package repository

1. Move the pins to the 1.5.0 commit (or take Renovate's digest pull request).
2. Run `family_sync.py --write`. It adds `.config/apicompat-excluded-attributes.txt` and the item in
   `Directory.Build.targets` that passes it to package validation.
3. Pack both packages once with `-p:ApiCompatGenerateSuppressionFile=true` and commit the regenerated
   `CompatibilitySuppressions.xml` files: their `CP0015` entries for `GenerateAssertionAttribute` and the state
   machine attributes are gone. Without this step the suppression check fails the build, because pack changes the
   committed files.
4. A README with a fence line that has text after it, or a block that never closes, now fails the README samples step
   (and the docs link check for the root README). Put the closing fence on its own line.

## Using `dependency-graph.yml`

GitHub's dependency graph doesn't resolve centrally managed NuGet versions: the static parse of the csproj files
lists packages without versions and without transitive packages. So Dependabot can't match advisories to the real
versions. `dependency-graph.yml` submits the resolved graph instead:
- **detect** (read-only): a `--locked-mode` restore, then `scripts/dependency_snapshot.py` reads every
  `project.assets.json` under `src/` and `tests/`. It writes one manifest per project: every package with its exact
  version, direct or indirect. Packages that reach consumers of a `src/` project are `runtime`; analyzers,
  build-time packages and everything in test projects are `development`.
- **submit** (`contents: write`): posts the snapshot to the dependency submission API. It runs no project code.
  Each submission replaces the previous one.

Add a job to the repository's `ci.yml`. It runs on pushes to `main` only:

```yaml
  dependency-graph:
    # Submits the resolved NuGet dependencies (exact versions, transitive included) to the dependency graph,
    # so Dependabot alerts see the real versions.
    if: github.event_name == 'push'
    uses: JohnVerheij/assertions-ci/.github/workflows/dependency-graph.yml@<commit-sha> # vX.Y.Z
    permissions:
      contents: write   # dependency submission API; the detect job itself only reads
```

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
5. Creates the GitHub release with the packages, SBOMs, VEX documents, `RELEASE_NOTES.md`, `SHA256SUMS` and the
   provenance bundle attached. Every file `SHA256SUMS` lists is attached, so `sha256sum --check SHA256SUMS` works on
   the downloaded assets. `gh` creates a draft, uploads the assets and then publishes, so immutable releases work. A version
   with a `-` suffix becomes a prerelease.

The provenance bundle `<Package>.<version>.intoto.jsonl` is the Sigstore bundle of the provenance attestation.
With it, a package can be verified offline as well:

```shell
gh attestation verify LogAssertions.TUnit.0.13.0.nupkg --bundle LogAssertions.0.13.0.intoto.jsonl \
  --repo JohnVerheij/LogAssertions.TUnit
```

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

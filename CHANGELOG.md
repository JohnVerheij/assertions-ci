# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.5.0] - 2026-11-14: API comparison without attribute noise, code blocks that must close

Minor release. Two things:
- Package validation no longer records changes of attributes that a consumer never compiles against, so
  `CompatibilitySuppressions.xml` lists only real API differences. A repository adopts it with `family_sync.py --write`
  and one regenerating pack (see the README, "Adopting 1.5.0").
- A code block in a README or docs page that no fence closes now fails the README samples step or the docs link
  check. Before, the rest of the page silently rendered as code.

### Added

- **Excluded attributes for package validation.** New template `.config/apicompat-excluded-attributes.txt`, which the
  `Directory.Build.targets` template passes to package validation (`ApiCompatExcludeAttributesFile`):
  `GenerateAssertionAttribute` (its expectation message) and the compiler's async, iterator and async-iterator state
  machine attributes (their argument names a generated class whose number shifts when a method is added). Their
  changes were recorded as `CP0015` entries: 27 in SseAssertions.TUnit, 25 in MetricsAssertions.TUnit. A pack of
  SseAssertions.TUnit with the template drops all 27 and keeps the 21 entries of real API additions.
- **Unclosed code blocks in the docs.** `scripts/docs_linkcheck.py` reports a fenced code block that no fence closes,
  with its line. The rest of the page would render as code, and its links went unchecked.

### Fixed

- **README samples: a fence line with text after it no longer closes a block.** `scripts/readme_samples.py` closed a
  block at any line that starts with the fence, such as "\`\`\` More text.". In CommonMark only the fence characters
  close a block, so on GitHub and nuget.org the rest of the README rendered as code while the sample still compiled
  (MetricsAssertions.TUnit, found in review). Such a block, and any block that no fence closes, now fails the step
  with the README line, with `readme-samples: report` as well as `enforce` (the script exits with 3 for it, and
  `package-ci.yml` fails on 3 in both modes).
- **Fenced code blocks found as CommonMark finds them.** `scripts/readme_samples.py` and `scripts/docs_linkcheck.py` now
  share `scripts/markdown_fences.py`. A fence opens or closes a block when it is indented at most three spaces from the
  content of its container: the page, or the list item it is in. Before, `readme_samples.py` took a fence at any
  indentation (also a line of an indented code block) and closed a block at a fence indented any amount. A line that
  starts with inline code, such as "\`\`\`x\`\`\` text", opens no block, and a block in a list item ends with the item.
  The scanner follows what decides where a fence can be: an ordered list item that does not start at 1, or an empty item
  (nothing after the marker but spaces), cannot interrupt a paragraph, and an empty item ends at a blank line; a setext
  heading underline ends a paragraph; an indented code line is not paragraph text that a later line continues; and the
  lines of an HTML block (a comment, a `<pre>` element, a block tag such as `<details>` up to the blank line that ends
  it) are raw HTML, so a fence there is not a fence. Where the CommonMark reference implementations differ, the scanner
  follows cmark, which GitHub renders Markdown with. Whitespace is spaces and tabs only, so a no-break space after a
  fence keeps it from closing a block and a line with one is not blank; lines end only at a line feed or carriage return
  (not at a form feed or a Unicode line separator), and both scripts drop a byte order mark, which before hid a fence on
  the first line of a docs page. `docs_linkcheck.py` keeps the list marker of a fence that starts on the marker line, so
  a paragraph later in that item is still checked. A scan of the 80 Markdown files of the nine package repositories
  finds no block that fails the new rules, every README gives the same samples as before, and the docs pages check the
  same text.
- **Docs links: inline code paired within its paragraph, HTML blocks left out.** `scripts/docs_linkcheck.py` paired
  backticks across any lines up to a blank line, so a stray backtick could pair with one in a heading or list item below
  it and hide every link in between, and a backslash-escaped backtick also opened inline code. It now pairs inline code
  within one paragraph, as CommonMark does, from what `markdown_fences.scan` reports about each line. A link inside an
  HTML block, such as a commented-out one, is raw HTML on GitHub and in DocFX, so it is no longer checked. The docs
  pages of the nine package repositories check the same links as before.

## [1.4.0] - 2026-11-13: a test run per target framework, shared support workflows, family templates, package checks

Minor release. Three things:
- A repository can target several .NET versions, for example `net10.0;net11.0`: every test suite, the smoke test and
  the Native AOT gate run once per target framework, read from each project. A single-framework repository runs
  exactly as before.
- What every package repository kept its own copy of now lives here once: the support workflows (lint, docs, CodeQL,
  zizmor), their scripts, the Renovate configuration, and the shared files as templates with a check. Nothing changes
  for a repository until it moves its pin and runs `family_sync.py --write` (see the README, "Adopting 1.4.0").
- New checks of what a consumer gets: NuGet package validation, the packed XML documentation, and the README code
  samples compiled against the packed packages (reported, not yet enforced, until a repository opts in).

### Added

- **Target frameworks** step in `package-ci.yml`. It reads `TargetFrameworks` (or `TargetFramework`) of the core,
  adapter, snapshot and smoke test projects with `dotnet msbuild -getProperty`, so adding a framework to a
  repository needs no workflow change. A test project that targets anything other than `netX.Y` fails the build.
- **Runtimes for every target framework.** The `global.json` SDK brings only its own runtime, so a second
  `actions/setup-dotnet` step installs the SDK of each other .NET version the projects target. `global.json` keeps
  selecting the pinned SDK. The step is skipped when all frameworks match the pinned SDK.
- **Reusable support workflows:** `package-lint.yml`, `package-docs.yml`, `package-codeql.yml` (with the shared
  `codeql/package-config.yml`) and `package-zizmor.yml`. They were identical in all nine package repositories; each
  repository now keeps a thin caller. CodeQL now builds only the shipped projects (`src/*/*.csproj`): for C#, it
  analyzes what the build compiles, so the repositories' `paths-ignore` of `tests/**` never applied. The docs
  workflow also rewrites links to `README.md` to the site's `index.md`. `dependency-review.yml` (a required check) and `scorecard.yml` (Scorecard's
  publishing rules) stay in the repositories.
- **Shared scripts:** `scripts/family_lint.py` and `scripts/docs_linkcheck.py`, moved here from the repositories'
  copies, with their tests. `family_lint.py` now also flags known British spellings in the tracked text files (a word
  list: the spellings the family used before, the common -ise verbs and analyse; code such as `IsCancelled` passes)
  and three README facts: the TUnit minimum in every README equals the central TUnit version, the adapter README
  names every sibling package, and the first `SECURITY.md` supported-versions row is the current version line.
  `docs_linkcheck.py` now skips links shown as code (fenced and inline code, and indented code outside lists and
  footnotes) and reads angle-bracket link destinations as Markdown does.
- **Renovate preset** `renovate/family.json`: the shared configuration of the package repositories. TUnit version
  literals now also move in every README (the core READMEs were missed before), and a major update of a package of the
  .NET release line waits for approval in the Dependency Dashboard instead of opening a pull request that would move
  every target framework's entry.
- **Family templates** `templates/package/` and `scripts/family_sync.py`: the files every repository shares, with
  placeholders for the package name, the documentation domain, the assertions-ci pin and core-only lines. The check
  (also run by `package-lint.yml`) reports missing, differing and obsolete files and missing local tools; `--write`
  updates a repository and keeps its own pins of other actions, then lists the missing local tools it cannot add.
  The workflow callers are stored as `.yml.template`, and `docs/docfx.json` as `docfx.json.template` (its
  core-only line is not valid JSON). The templates fix drift found across the repositories: the `.gitattributes` snapshot rules and spelling, the
  `.gitignore` entries, the unreachable `return true;` in `Directory.Build.targets` (CS0162 at pack), and docfx
  reading `filterConfig.yml` as a page. The `Directory.Build.props` template sets `LangVersion` 15.0 (C# 15, from
  the .NET 11 SDK the family builds with to target `net10.0` and `net11.0`).
- **NuGet package validation** in `package-ci.yml`: Meziantou's validator checks every packed package for SourceLink
  and a deterministic build, symbols whose sources resolve, XML documentation, readme, license, repository metadata,
  tags and optimized assemblies; an icon is required from version 1.0.0. `scripts/nuget_validation_report.py` turns
  its output into one annotation per rule. The published packages of all nine repositories pass apart from the icon.
- **XML documentation check** in `package-ci.yml` (`scripts/xmldoc_check.py`): no empty member, no generator
  placeholder summary (`Generated extension method for ...`), and every `<inheritdoc cref>` leads to a summary. The
  packages built on TUnit 1.81.10 or later pass; the earlier ones carry placeholders that a rebuild removes.
- **README code samples** in `package-ci.yml` (`scripts/readme_samples.py`, input `readme-samples`): every C# sample
  of the READMEs compiles against the packed packages in a consumer-style project, with `#line` mapping each error to
  its README line. `report` (the default) shows failures as warnings, `enforce` fails the build. The README describes
  the sample conventions, `no-compile` and the optional `tests/ReadmeSamples.Prelude.cs`.
- **Coverage per test run:** before the merge, the job summary shows each suite's coverage per framework and
  assembly (`scripts/coverage_table.py`); report only.
- **typos** in `package-lint.yml`, with the family dictionary `typos/family.toml` (generated files excluded, the
  family's correct words listed). It finds no typos in the nine repositories today. A repository that allows only
  selected actions must add `crate-ci/typos@*` to them (README, "Adopting 1.4.0").

### Changed

- The core, adapter and snapshot suites run with `--framework` for each target framework. Each run writes its
  coverage report to its own output folder, and the merge step merges them all; the thresholds apply to the
  merged report, as before.
- The smoke test runs on each target framework, and the Native AOT gate publishes and runs one native executable
  per target framework.
- A suite, smoke test or Native AOT gate that fails on one framework still runs on the others; the step then fails
  with one error that names the frameworks that failed.
- The build job's timeout is 30 minutes instead of 20, since a two-framework repository runs every suite twice.
- This repository's Renovate configuration extends the family preset, as every package repository does, and keeps
  the action pins in the workflow templates and the pinned tool versions current.
- This repository's own checks: actionlint and zizmor also check the workflow templates, rendered for a demo package
  (`scripts/render_templates.py`); `renovate-config.yml` validates the preset, the repository template and this
  configuration with Renovate's validator, all three as repository configuration; `spelling.yml` runs typos with the family dictionary; `scripts.yml` measures
  the script tests and fails below 90% line and branch coverage. Every script is at 100%.
- The template `.gitignore` ignores `tests/.readme-samples/`, the generated sample project.

## [1.3.0] - 2026-11-02: API compatibility suppression check

Minor release. A repository whose packed API differs from its ApiCompat baseline in a way its committed
`CompatibilitySuppressions.xml` does not record now fails CI: run
`dotnet pack -p:ApiCompatGenerateSuppressionFile=true` locally and commit the regenerated file.

### Added

- **API compatibility suppression check** in `package-ci.yml`. Pack regenerated `CompatibilitySuppressions.xml`
  instead of failing on an API difference, so ApiCompat never blocked on its own. Both packs now pass
  `ApiCompatGenerateSuppressionFile=true`, and the build fails when pack changes a committed suppression file or
  adds one, including one that a `.gitignore` pattern would hide; the fix is to run
  `dotnet pack -p:ApiCompatGenerateSuppressionFile=true` locally and commit the regenerated file, which puts the
  API change into the pull request.

### Changed

- `package-ci.yml` merges the coverage reports in `$RUNNER_TEMP` instead of `./coverage-merged`, so a local run of
  the same steps leaves no untracked folder in the repository.

## [1.2.1] - 2026-11-01: release notes attached to the GitHub release

Patch release. Callers need no change.

### Fixed

- `package-publish` attaches `RELEASE_NOTES.md` to the GitHub release. `SHA256SUMS` lists it, so without it
  `sha256sum --check SHA256SUMS` on the downloaded assets failed on a missing file (first seen on
  SnapshotAssertions v0.8.0; `--ignore-missing` checks those assets).

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

[unreleased]: https://github.com/JohnVerheij/assertions-ci/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/JohnVerheij/assertions-ci/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/JohnVerheij/assertions-ci/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/JohnVerheij/assertions-ci/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/JohnVerheij/assertions-ci/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/JohnVerheij/assertions-ci/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/JohnVerheij/assertions-ci/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/JohnVerheij/assertions-ci/releases/tag/v1.0.0

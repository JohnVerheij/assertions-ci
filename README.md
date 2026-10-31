# assertions-ci

Shared GitHub Actions building blocks for the [DotNetAssertions](https://dotnetassertions.dev) package family:
a reusable CI workflow and composite actions for the release workflow, so a CI fix lands once instead of once per
package repository.

> **Scope:** internal tooling for the `*Assertions.TUnit` repositories. It is public so those public repositories
> can call it. It is not a general-purpose product and makes no stability promise outside the family.

## Contents

| Path | Purpose |
|---|---|
| `.github/workflows/zizmor.yml` | Security audit of this repository's workflows and actions (blocks on findings) |
| `.github/workflows/codeql.yml` | CodeQL analysis of the workflows and actions (`actions` language) |
| `.github/workflows/scorecard.yml` | OpenSSF Scorecard supply-chain analysis |
| `.github/workflows/dependency-review.yml` | Blocks pull requests that introduce a vulnerable dependency |

The reusable CI workflow (`.github/workflows/package-ci.yml`) and the release composite actions
(`.github/actions/`) are added in the first release, `v1.0.0`.

## Versioning

Releases are signed tags (`vX.Y.Z`). Callers pin a release by its commit SHA with the tag as a comment, which
keeps the reference immutable and lets Renovate propose updates:

```yaml
jobs:
  ci:
    uses: JohnVerheij/assertions-ci/.github/workflows/package-ci.yml@<commit-sha> # vX.Y.Z
```

## Security

See [SECURITY.md](SECURITY.md) for how to report a vulnerability.

## License

[MIT](LICENSE)

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

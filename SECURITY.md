# Security policy

`assertions-ci` holds the shared GitHub Actions workflows and composite actions of the DotNetAssertions package
family. A weakness here can affect the build and release pipeline of every package that uses it, so security
reports come before other work.

## Reporting a vulnerability

**Please do not open a public issue for a security vulnerability.**

Use GitHub private vulnerability reporting:

1. Open the repository's [Security tab](https://github.com/JohnVerheij/assertions-ci/security).
2. Click **Report a vulnerability**.
3. Describe the issue, the affected workflow or action, and how to reproduce it.

If private reporting is not available to you, open an issue titled `Security: contact request` with no details in
the body, and the conversation moves to a private channel.

## In scope

- Workflow or action code that could leak credentials or tokens, or allow code injection (for example through
  untrusted inputs, pull request content, or artifact handling).
- Weaknesses that could let a release publish something other than what was built and attested.

## Response targets

Personal open-source project maintained outside working hours; best-effort targets:

| Stage | Target |
| --- | --- |
| Acknowledgement | Within 5 business days |
| Initial assessment | Within 14 calendar days |
| Fix released or disclosure plan agreed | Within 90 calendar days from assessment |

## Supported versions

Only the latest release tag receives fixes. Callers pin by commit SHA and move forward through Renovate updates.

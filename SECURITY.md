# Security policy

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities. Report them
privately through GitHub Security Advisories on this repository:

https://github.com/Jack-ki1/PARK_WISE_AI/security/advisories/new

(If private vulnerability reporting is not enabled, enable it under
*Settings → Code security and analysis*, or contact the repository owner
directly.) Include a description of the issue, the affected component, steps to
reproduce, and the impact you assess. You should receive an acknowledgement
within a few working days and an assessment with a planned fix within 14 days
for issues confirmed to be real vulnerabilities.

## Supported versions

This project has no tagged releases yet. The `main` branch is the only
supported line: fixes are applied there and backported only when a release
branch exists.

## Scope

In scope: the FastAPI backend (`backend/`), the Next.js dashboard (`web/`),
and CI/CD workflows (`.github/`). Out of scope: vulnerabilities that require a
misconfigured deployment contrary to the production fail-closed checks
(`PARKWISE_ENV=production` refuses to start with auth disabled or wildcard
CORS), and issues in dependencies already reported upstream (we run `pip-audit`
and `npm audit` in CI — see `.github/workflows/ci.yml`).

## Baseline

The full description of implemented safeguards, known gaps ("not included —
required before internet exposure") and camera/video privacy guidance lives in
[docs/SECURITY.md](docs/SECURITY.md). Keep both documents in step: a change to
the security posture must update `docs/SECURITY.md` in the same pull request.

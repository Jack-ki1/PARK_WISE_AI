# Security and privacy baseline

## Included safeguards

- File extension allowlist and configurable byte limit for uploads.
- Public clip fetcher uses a fixed identifier-to-URL catalogue; clients cannot submit arbitrary remote URLs (limits SSRF exposure).
- Video paths are generated server-side using UUIDs; client-supplied file names are display metadata only.
- Normalized polygon input is validated and constrained to [0, 1].
- CORS origins are configurable; defaults are local development origins.
- Error messages are persisted with a bounded length; stack traces belong in server logs.

## Not included — required before internet exposure

- Authentication, authorization/RBAC, SSO and tenant isolation.
- Durable asynchronous job queue, API rate limiting, CSRF strategy for cookie auth, and endpoint-level quotas.
- Managed object storage, antivirus/content scanning, media transcoding sandboxing and automatic retention/deletion.
- TLS termination, secret rotation, encrypted backup, database migrations and audit trails for operator changes.
- Monitoring/alerts, log redaction, backup/restore drills and incident response plan.

## Camera/video privacy

Parking footage can contain faces, plate numbers, staff and visitor activity. Obtain appropriate notices/permissions, define purpose and retention, restrict operator access, minimize collection and avoid using LPR/identity features until a privacy/legal review is complete. This release does not perform license plate recognition and does not store plate text.

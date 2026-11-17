# Security, trust boundaries and go-live gates

## Trust boundary

The FastAPI service is the only employee-facing entry point. PostgreSQL runs on the private Compose network and its port is not published on the Windows host. Uploads use random stored names in a private local folder; downloads are routed through an authenticated task-scope check. Do not expose the server to the public internet or configure router port forwarding.

## Implemented controls

- Passwords hashed with Argon2id via `argon2-cffi`; no plaintext password field or bootstrap network endpoint.
- Signed session cookie with HttpOnly, SameSite=Strict, configurable expiry; secure-cookie flag is enabled for `APP_ENV=production`.
- Per-process failed-login throttling, CSRF header checks on all non-read methods except the login endpoint, input schemas and server-side role checks.
- Roles are reloaded from the database on each authenticated request; disabled accounts lose access. A technical administrator cannot approve schedules or verify tasks solely by being an administrator.
- Timetable date/status/version rules, overlapping shift conflict checks, independent task review, and audit records for key workflow actions.
- File extension allowlist, content signatures for PDF/PNG/JPEG/Office ZIP containers, per-file size limit, 10-file limit, random storage name, private storage and authenticated download authorization.
- PostgreSQL has no host port mapping; local CSS/JS; Compose container runs as a non-root user; secrets live in untracked `.env`.
- Database/upload paired-backup tooling, manifest checksums, restore confirmation, and access-restricted LAN firewall helper.
- Equipment APIs enforce authorizer-role policy, active assigned/replacement custodian checks for physical issue/return, private authenticated photo access, unique individual assets, no direct completed-transaction deletion, per-item condition/status checks, audit events, and row locks on assets during PostgreSQL issue operations.

## Known gaps — not security-certified

1. **HTTPS is not provisioned by the project.** Compose currently maps the app over HTTP. A signed cookie and CSRF do not encrypt passwords/traffic. Obtain an institution-approved certificate and configure a trusted LAN reverse proxy/TLS path before sending real credentials over Wi-Fi. `APP_ENV=production` marks cookies Secure; plain HTTP would not carry them.
2. No automated antivirus/content-disarm scanning is provided for attachments. Do not upload sensitive/hostile files until the institution accepts this risk or supplies scanning.
3. Login throttle is per-process memory; it resets on restart and is not a distributed rate limiter. Keep a single instance behind LAN firewall; upgrade this control before scaling.
4. Audit records are append-oriented through application routes but not cryptographically tamper-proof against database/server administrators. Restrict PostgreSQL/Windows access and export logs per institutional policy.
5. There is no immutable offsite backup sync, formal retention/privacy schedule, audit alerting, or tested Windows operational recovery run in this environment.
6. Backend permissions are enforced, but the system has not undergone a professional penetration test or Windows/PostgreSQL review. Do not treat it as approved for protected personal data until your institution authorizes it.

## Required before real data

- Review/accept applicable privacy, public-institution ICT, personnel-record retention and incident response rules.
- Configure a trusted HTTPS certificate on the office LAN; verify certificate trust on all seven devices and ensure no WAN exposure.
- Verify Windows firewall scope and guest/VLAN isolation from a separate client; disable database host publishing and keep Windows security updates on.
- Restrict ACLs on `.env`, database volume, `storage/uploads` and `storage/backups`; protect server physical access.
- Set unique production secrets, secure session cookie mode, backup retention, and role account governance.
- Execute two-client workflow checks, simultaneous writes, restart tests and a database-plus-upload restore from an off-host copy.
- Establish attachment scanning, logging retention, staff privacy notice, administrator duties and incident contacts.

Never commit `.env`, backups, database dumps, uploads, real employee data, or credentials. Default development configuration is not an office production profile.

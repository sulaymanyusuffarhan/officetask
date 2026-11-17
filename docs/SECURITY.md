# Security and deployment notes

## Trust boundaries

Treat the host machine and its disk as sensitive. The office LAN is not a substitute for application authentication. Each browser-facing action must be authenticated, authorized for its record scope, validated and audited on the server. PostgreSQL must remain on an internal container network or loopback, never exposed to employee devices. Private uploads and backup archives must not be mounted beneath the static web root.

## Phase-one controls and gaps

Implemented now: `.env`-based configuration, secrets excluded by `.gitignore`, private PostgreSQL service with no host port in Compose, non-root container user, server-side PostgreSQL readiness, local static assets, private storage volume paths not mounted as public files, and clear warning on the foundation page.

Not implemented yet: authentication, session/CSRF controls, role-level and record-level authorization, audit trail, rate limiting, attachment validation/scanning, Windows firewall rules, backup automation, restore verification, TLS policy and production hardening. Consequently this phase is not appropriate for real personnel data or live office workflows.

## Before a deployment

1. Generate unique strong `SECRET_KEY` and database credentials, store `.env` with restrictive Windows ACLs, and keep it out of backups shared broadly.
2. Configure a static address or DHCP reservation; allow only the office LAN subnet to reach the application TCP port in Windows Defender Firewall.
3. Do not publish PostgreSQL's port or enable router port forwarding.
4. Restrict server and backup drive access to authorized administrators. Encrypt backups at rest where supported.
5. Configure system updates, endpoint protection, power/restart behavior, service supervision and physical access.
6. Use HTTPS on the LAN if credentials traverse untrusted Wi-Fi; deployment certificate provisioning is still to be specified.
7. Test restoration before loading live data and schedule periodic recovery drills.

## Incident and data handling

Do not commit `.env`, database dumps, real employee data, session secrets, uploads or backups. Report suspected credential or data exposure to the organization's designated security contact, rotate affected secrets, preserve relevant logs and follow institutional incident procedures. Legal retention, privacy notice, and data-residency requirements must be confirmed with the organization before production rollout.

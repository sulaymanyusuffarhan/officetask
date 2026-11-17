# System architecture

## Deployment context

One Windows 11 computer hosts Docker Compose. Up to six office client browsers access FastAPI over the approved office subnet. PostgreSQL remains private to the Compose network; uploads and backup folders are local server paths. No public cloud or router port forwarding is part of the design.

```text
Office browser ── office LAN TCP 8000 ──> FastAPI/Uvicorn
                                             ├── local HTML / CSS / JavaScript / logos
                                             ├── SQLAlchemy ── Compose-private PostgreSQL
                                             └── private uploads / timestamped paired backups
```

The current HTTP Compose endpoint needs an organization-approved TLS reverse proxy before production credentials are sent over Wi-Fi; no certificate automation is shipped.

## Repository layout

- `app/api/routes.py`: role-guarded auth, administration, timetable/task, attachment, shift report, attendance and reporting routes.
- `app/api/export_routes.py`, `analytics.py`: PDF/Excel and aggregated management reports.
- `app/api/equipment.py`, `app/schemas_equipment.py`: role-enforced equipment register, authorizations, shift custody, issues/returns, handovers, QR labels and audit/report endpoints.
- `app/core`: configuration, session-derived current user, CSRF and role policy, Argon2 password hashing.
- `app/db`, `app/models`: SQLAlchemy 2 sessions and normalized domain entities.
- `alembic/versions`: reviewed database schema versions.
- `app/templates`, `app/static`: server page shell, responsive local CSS/JS, official supplied assets.
- `storage/uploads`: private random-name task evidence and equipment-photo store; neither is mounted as a static web directory.
- `scripts/`, root `.bat`: Windows setup, run/stop, backup/restore and scheduled-task helpers.

## Persistence and workflow invariants

Normalized PostgreSQL entities cover users/roles, departments/shifts, weekly timetable versions and assignments, tasks, status history, submissions, private attachment metadata, verifications, attendance exceptions, handover reports, and equipment assets/accessories, dated custodian assignments/replacements, authorization policy, issue/item rows, immutable item events and handover snapshots. Each employee on a shared piece of work has an independent task row. Timetable versions use `(week_start, version)` uniqueness; week allocations must fall inside the seven-day week and the server rejects overlapping shifts. Published plans are locked; revisions require a cloned version and recorded reason. State transitions and reviewer identity are audited.

Equipment requests stay pending until an authorizer whose role is configured by the Head records a method, remarks and timestamp. Issue/return routes separately verify the actual actor against the dated shift custodian/replacement roster; authorization never implies the authorizer physically issued an item. Each physical device/accessory has its own unique asset row and issue item. A shift handover snapshots all live loans and acknowledgements, but does not close or return them. Partial returns leave unreceived assets outstanding; missing assets stay unavailable; damaged assets require an explicit inspection disposition. App routes do not delete completed equipment events.

A submission is not a verified result. Only the assigning editor or Head may verify/reject/request correction, and nobody may verify their own task. Reported submission and verified rates use separate numerators/denominator. Attendance exceptions (leave, absent, reassigned) are shown separately rather than turning a missing submission into an automatic performance failure.

## Authentication, authorization and network protections

The browser receives a signed, HttpOnly, SameSite=Strict cookie containing the authenticated user ID/CSRF token; the backend reloads the account and role from the database each request. Mutating requests require the session CSRF token in `X-CSRF-Token`. Passwords are Argon2id-hashed, sign-in failures are rate-limited per app process, and permission checks execute on API routes. Technical administrator access does not imply workflow approval. Production cookies require `APP_ENV=production` (Secure), which requires HTTPS to work.

Attachments use allowlisted file extensions/content signatures, a per-file size ceiling, randomized paths and authorization-gated downloads. The original filename is metadata only. Antivirus scanning is not included. Audit rows are not editable through ordinary app routes but are not immutable against a database administrator.

## Operational boundary

Compose maps application TCP 8000 configurable through `APP_PORT`/`APP_BIND_IP`, while PostgreSQL has no host port. Windows scripts can create a subnet-scoped firewall rule and pause the web service briefly during paired database/file backup. Docker restart policies start containers only when Docker Desktop is running. The optional logon task is not a service running before Windows user logon. Windows scripts have not been executed in this Linux environment.

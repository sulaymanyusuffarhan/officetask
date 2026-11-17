# System architecture (initial target)

## Context

The application serves a small office on one trusted local network. A single Windows 11 computer is the application host; employee devices use a browser over office Wi-Fi. The host owns the only database connection and the private file store. Employee browsers must never connect to PostgreSQL or access upload paths directly. Public-cloud hosting and inbound router port forwarding are out of scope.

## Phase-one structure

```text
Browser (office LAN)
  └── HTTP :8000 ──> FastAPI / Uvicorn
                         ├── local HTML, CSS, JS and supplied logos
                         ├── SQLAlchemy ──> PostgreSQL (Compose private network only)
                         └── private storage volumes (uploads / backups; not web-mounted)
```

```text
app/
  api/            HTTP route modules (domain routes are added in later phases)
  core/           configuration and cross-cutting application services
  db/             SQLAlchemy declarative base and session lifecycle
  models/         normalized ORM entities (added with schema migrations)
  services/       business rules (added with workflows)
  static/         locally served assets; no CDN dependency
  templates/      server-rendered page shells
alembic/          versioned PostgreSQL schema changes
 tests/           automated test suite
 docs/             architecture, operations, security, testing and roadmap
```

## Selected technology

- **Python 3.11+ / FastAPI / Uvicorn:** asynchronous-capable HTTP service with server-side permission checks.
- **PostgreSQL / SQLAlchemy 2 / Alembic:** transactional relational store, ORM and versioned schema evolution.
- **HTML/CSS/JavaScript:** lightweight browser UI. Bootstrap may be vendored locally if adopted; no production dependence on a CDN.
- **Private local files:** generated storage path is outside static web serving; database records will hold metadata and ownership references.
- **Docker Compose:** repeatable development setup and a candidate Windows 11 deployment route (Docker Desktop prerequisites). A native Windows installation alternative is still to be evaluated.

## Domain boundaries planned

The normalized model is expected to separate identity and authorization (users, roles, permissions), organization (employees, departments, shifts), weekly planning (week, immutable/versioned timetable, assignments and approvals), execution (task/project, accountable per-person assignment, state history, submissions, private attachments, verification), operations (attendance/leave, shift/day reports, handovers), and governance (notifications, audit events, settings). Domain entities and constraints will be introduced with tested migrations rather than pre-creating speculative tables.

A published timetable is a versioned record. Changes after publication must create a new version with actor, timestamp, reason and before/after values. Each staff member gets an accountable assignment even for collaborative work. Submission is distinct from verification; only an authorized reviewer can mark work verified. These invariants belong in backend services and database constraints where practical, not only UI controls.

## Request and authorization model

Browser requests will use secure server-side sessions with CSRF protection for state-changing forms. Passwords will be Argon2-hashed. Authorization is deny-by-default and enforced on every backend operation, with role and record-scope checks. Admin technical privileges do not grant workflow approval automatically. Audit events are append-only for ordinary application roles. File download routes will authorize the requesting user against the associated task/submission before streaming a file.

These controls are architectural requirements, **not yet implemented in phase one**.

## LAN deployment

The service binds to the LAN-facing interface in deployment. The Windows firewall is the network boundary: permit the application port only from the office subnet; do not expose port 5432; do not configure router forwarding. Use a DHCP reservation or static address and distribute the host URL internally. Server-only backups must include PostgreSQL and uploads from a consistent snapshot. Operational scripts and restore drills are later milestones.

## Operational properties

- Health endpoints distinguish process liveness from database readiness.
- PostgreSQL data, uploads and backups use persistent storage in Compose.
- Environment-specific secrets are provided out-of-band in `.env`, excluded from source control.
- Browser-facing assets are local; once installed the web UI does not require a CDN.
- Logs must avoid passwords, session IDs and sensitive report contents; retention and redaction policy will be set before production use.

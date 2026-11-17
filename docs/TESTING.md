# Testing guide

## Automated local tests

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The tests use an isolated file-backed SQLite database per test (with SQLite foreign keys enabled) and exercise authentication, Argon2 login, CSRF rejection, representative allowed/denied API access for all six roles, planner-to-head timetable approval/publication/versioning, task assignment/submission/verification, performance/analytics and PDF/XLSX exports, file upload validation/private download, audit access and throttling, and seven independent in-process sessions reading concurrently. Role checks are representative rather than exhaustive for every route; the concurrent-session test uses SQLite and performs reads, not PostgreSQL write-load testing.

`tests/test_equipment.py` covers unique physical asset registration (including optional serials), accessory linking and automatic issue-line expansion, configured authorizer roles, denial of issue before authorization, actual custodian validation, distinct authorizer/issuer/borrower/receiver IDs, borrower acknowledgement, morning-to-evening shift handover with both acknowledgements, and the required partial-return/missing-charger scenario with asset history and report verification. The handover test asserts an open equipment loan remains open across the shift change. This is database-backed API coverage, not a browser or network-load test.

## Migration checks

When a PostgreSQL service is available:

```bash
alembic upgrade head
alembic current
alembic check
```

For syntax/DDL generation without applying to a database:

```bash
alembic upgrade head --sql
```

Do not generate production migrations against SQLite and assume that is proof of PostgreSQL compatibility. Review every migration and test upgrades and downgrades against the intended PostgreSQL version.

## Compose/Windows smoke checks

On a Windows 11 server with Docker Desktop:

```powershell
docker compose config
docker compose up --build -d
docker compose ps
Invoke-WebRequest http://localhost:8000/api/health/live
Invoke-WebRequest http://localhost:8000/api/health/ready
```

Verify TCP 5432 is not bound on the Windows host. Test allowed/denied client subnet access, sign-in/session expiration, role boundaries and access to private attachments. Restore a paired DB/files backup into a test environment, verify hashes and at least one downloaded attachment.

## Audit evidence

See [`AUDIT_REPORT.md`](AUDIT_REPORT.md) for the dated execution results, PASS/FAIL/NOT TESTED/BLOCKED status table, deployment blockers and go-live decision. On the audit branch, the local checks were run with:

```bash
.venv/bin/pytest -q
node --check app/static/js/app.js
.venv/bin/python -m compileall -q app alembic tests
.venv/bin/alembic heads
.venv/bin/alembic upgrade head --sql
```

Offline migration SQL generation does not apply the migrations to PostgreSQL.

## Not tested here

The scripts and Compose deployment could not be run in this environment because Docker/Windows are not installed. Unit tests do not prove seven simultaneous users, production TLS, firewall correctness, persistent-volume recovery, backup schedule behavior, or PostgreSQL locking under simultaneous edits. These are required acceptance tests before live use.

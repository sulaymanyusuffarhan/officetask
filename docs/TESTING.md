# Testing guide

## Automated local tests

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The tests use an isolated file-backed SQLite database per test (with SQLite foreign keys enabled) and exercise authentication, Argon2 login, CSRF rejection, the six-role API access matrix, planner-to-head timetable approval/publication/versioning, task assignment/submission/verification, performance/analytics and PDF/XLSX exports, file upload validation/private download, audit access and throttling, and seven independent in-process sessions reading concurrently.

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

## Not tested here

The scripts and Compose deployment could not be run in this environment because Docker/Windows are not installed. Unit tests do not prove seven simultaneous users, production TLS, firewall correctness, persistent-volume recovery, backup schedule behavior, or PostgreSQL locking under simultaneous edits. These are required acceptance tests before live use.

# Testing guide

## Automated local tests

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The tests use an isolated file-backed SQLite database per test (with SQLite foreign keys enabled) and exercise authentication, Argon2 login, CSRF rejection, a six-role API access matrix, planner-to-head timetable review/publication/version locking and conflict detection, task assignment/progress/submission/verification, self-review prevention, performance/analytics and PDF/XLSX generation, file upload validation/private download, admin/business-role separation, audit access, login throttling, and seven independent authenticated TestClient sessions reading concurrently. This concurrency check is a lightweight application/session check, not a network load test or proof of PostgreSQL locking behavior.

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

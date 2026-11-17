# Testing guide

## Run phase-one tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

These tests use FastAPI's test client and do not require a running PostgreSQL instance. They cover the status page's non-operational warning, liveness and availability of local logo assets. The readiness endpoint expects a real PostgreSQL connection; validate it with Compose once migrations and deployment setup are in place.

## Compose smoke check

After configuring `.env` as in the README:

```bash
docker compose config
# Once built and started:
docker compose ps
# Visit /api/health/live and /api/health/ready from the server.
```

Confirm port 5432 is not listening on the Windows host. Confirm the app is reachable from an authorized office client, and inaccessible from outside the allowed subnet. Do not run destructive Compose volume deletion against office data.

## Planned test coverage

Add focused tests in their implementation phase for passwords/sessions, each role/record scope, CSRF, timetable constraints and versioning, task state transitions, upload security, independent reviewer verification, report calculations, append-only audit events, simultaneous writes, and backup/restore. End-to-end deployment tests must include multiple client sessions and a restore into a clean environment. No such coverage is claimed in phase one.

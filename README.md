# Office Task & Performance Management System

A private, self-hosted office application for weekly duty planning, daily task assignment, employee submissions, editorial verification and management reporting. The target installation is one Windows 11 office server and up to six other devices on the same trusted Wi-Fi/LAN; it is not designed for public internet exposure.

> **Current delivery status — Phase 1 foundation only.** The repository now has the application skeleton, branded local landing page, database connection/migration scaffolding, container configuration and smoke tests. Authentication, roles, employee workflows, reports, Windows operations scripts and production backup/restore are **not implemented yet**. Do not enter real employee or confidential information into this phase's application. Work will proceed in the phases in `docs/ROADMAP.md`.

## What is in this phase

- FastAPI service, configuration from environment variables, SQLAlchemy 2 base/session and PostgreSQL connectivity/readiness checks.
- Alembic migration scaffolding; no business schema has been created yet.
- Docker Compose setup with a private PostgreSQL container (no database host port) and persistent database/upload/backup volumes.
- Local static CSS and the two supplied, unmodified brand images.
- A clear foundation status page, liveness/readiness endpoints and tests.
- Architecture, deployment boundary, roadmap and security decisions documented under `docs/`.

## Quick start (Docker Compose)

Requirements: Docker Desktop with Compose v2, a Windows 11/Linux/macOS development computer, and a LAN firewall policy appropriate for the office. First-run image builds need registry access; once built, the application and assets are served locally without a browser internet connection.

1. Copy `.env.example` to `.env`.
2. Edit `.env`. Set a unique strong `SECRET_KEY` (at least 32 random bytes) and a unique `POSTGRES_PASSWORD`. Use URL-safe letters and digits for the database password unless you correctly URL-encode special characters in `DATABASE_URL` for direct Python runs. **Never commit `.env`.**
3. Run `docker compose up --build -d`.
4. Check `docker compose ps` and open `http://localhost:8000`. `/api/health/live` checks the process; `/api/health/ready` checks PostgreSQL.
5. Stop with `docker compose down`. This preserves named volumes. `docker compose down -v` deletes the data volumes and is destructive; do not use it on an office installation.

`APP_BIND_IP` controls the host interface Docker publishes to. Its default is `0.0.0.0` to allow LAN clients. In an office deployment, use the server's reserved LAN address where possible, and configure Windows Defender Firewall to allow TCP 8000 **only from the office subnet**. Do not enable router port forwarding. PostgreSQL has no published port.

## Local Python development

Python 3.11 or newer and a reachable PostgreSQL server are required. Create a virtual environment, install `requirements-dev.txt`, copy `.env.example` to `.env`, and adjust `DATABASE_URL` for the local database. Then run:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The only interactive page at this stage is a branded status page. API docs are at `/api/docs` in non-production configuration. Do not use the development configuration or reload server as the hardened office deployment.

## Configuration

See `.env.example` for the environment variable catalogue. Settings can be supplied through environment variables or a local `.env` file. The local storage directories are intentionally not exposed as public static content. Upload authorization, file validation, session security and the operational backup scheduler are future phases; the values and volumes are scaffolding, not a claim that those capabilities are already active.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The phase-one tests exercise the root status page, local branding URLs and process liveness. Business workflow, concurrency, security, Windows LAN and recovery tests will be added alongside their implementation. A passing smoke-test suite is not production acceptance.

## Windows 11 status

The planned Windows install/start/stop/backup/restore scripts and first-run administrator workflow are tracked for later delivery (`docs/ROADMAP.md`). The current repository does **not** yet satisfy the final Windows installation or office operational acceptance criteria. For now, Docker Compose is the development/deployment foundation, not a finished Windows installer.

## Project documentation

- [System architecture and trust boundaries](docs/ARCHITECTURE.md)
- [Development roadmap and phase exit criteria](docs/ROADMAP.md)
- [Security and deployment decisions](docs/SECURITY.md)
- [Testing guide](docs/TESTING.md)
- [Change log](CHANGELOG.md)

## License and branding

The supplied images are placed in `app/static/images/` without alteration. Confirm the organization's rights and usage requirements before external redistribution. A project license has not yet been selected.

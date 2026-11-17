# Office Task & Performance Management System

A self-hosted FastAPI/PostgreSQL web application for an office LAN. The repository includes local sign-in, role-scoped accounts, weekly timetable and task workflows, performance reporting, equipment custody, and a manual-first TBC Digital social media reporting module for YouTube, Facebook, Instagram, X and TikTok. Social reports do not require APIs or credentials; weekly entry/import, private evidence, approval, quarterly consolidation, charts and PDF/XLSX exports are included. API tests and chart-renderer tests are available, but Windows/PostgreSQL/browser/LAN acceptance remains required before production use.

> **Deployment status:** Core workflows and tests are implemented, but the complete seven-device Windows 11 acceptance exercise, Docker Compose runtime, firewall restrictions, HTTPS on the office Wi-Fi, scheduled-task behavior, backup/restore drill and simultaneous-user load test have **not** been validated in this development environment. Do not treat this branch as security-certified or put real personnel records into production until your IT administrator has followed the hardening and recovery gates in `docs/WINDOWS_INSTALLATION.md` and `docs/SECURITY.md`.

The official supplied images are stored unmodified under `app/static/images/`. The browser uses local CSS and JavaScript; no CDN is required.

## Included functionality

- Argon2 password hashing, signed HttpOnly session cookie, CSRF token on state-changing requests, session expiry, login throttling, and backend role checks.
- Six roles: Head of Office, Weekly Timetable Planner, Editor, Shift Leader, Staff/Employee, System Administrator. The technical admin role does not receive business review rights.
- PostgreSQL tables and Alembic migrations for users, roles, departments, shifts, timetable versions/allocations, tasks/status history, submissions, attendance, audit events, individual equipment assets/accessory links, custodian roster/replacements, issue authorizations, item-level loan/return events and shift handovers, plus social profiles/officers, weekly evidence-backed reports and quarterly snapshots.
- Weekly schedule creation/copy, allocation conflict checks, submit/review/return/approve/publish workflow, and required reasons/audit when creating published versions or editing allocations.
- Individual task rows per employee, acknowledgment/progress, written submissions, validated private attachments, review/correction/rejection/resubmission, verified status and management reopen with a reason.
- Shift handover reports, attendance exceptions, date-filtered planned-vs-actual performance, submission vs verified rates, and PDF/Excel/CSV exports.
- Equipment inventory with unique asset numbers (optional serials), private asset photos, QR labels, accessories tracked as separate assets, head-configured authorizer roles, actual issuing/receiving custodians, issue conditions, borrower acknowledgement, partial returns, missing/damaged states, custody handover acknowledgements, inspection and individual asset history.
- Database-backed equipment dashboard and JSON reports for custodian assignments/replacements, issuances, returns, current/external/overdue borrowing, missing/damaged items and handovers. Equipment changes and physical actions write application audit and per-item event records; completed transactions have no delete/edit route.
- Manual-first social media statistics for YouTube, Facebook, Instagram, X and TikTok; verified account-profile setup, designated officer access, explicit N/A metrics, private evidence uploads, CSV/XLSX import preview, source attribution, approval/correction workflows, quarterly snapshot reports, filtered SVG analytics charts and PDF/XLSX exports. No API credentials, scraping, or platform passwords are required; the official profile handles must be supplied and verified by the office.
- Database-backed dashboards, local responsive UI, Windows batch wrappers and PowerShell installation/start/stop/backup/restore/task-scheduling scripts.

The UI provides task creation/submission, schedule and review workflows, reports, account setup, and audit history. The API is documented at `/api/docs` when `APP_ENV` is not `production`.

## Windows 11 installation

See the beginner-oriented [Windows 11 installation guide](docs/WINDOWS_INSTALLATION.md). This deployment uses Docker Desktop and Docker Compose, not native PostgreSQL/Python services.

1. Install Docker Desktop for Windows 11; start it and wait for the engine to be ready.
2. Download/extract the repository on the server computer.
3. Run `install_windows.bat` from an elevated terminal. It creates `.env` with random secrets when missing, asks for the trusted office LAN subnet for a restricted firewall rule, starts containers, migrates the schema, seeds roles, and prompts for the first technical administrator.
4. Sign in locally and create the Head of Office, planner, editors, shift leaders, and staff accounts. Share temporary passwords securely, not through source control or chat.
5. In Equipment & custody, the Head configures authorized borrowing roles (until configured, all issue authorizations are blocked), and Head/System Administrator assigns custodians to the Morning, Afternoon and Evening shifts with effective dates. Record any absence as a dated replacement with a reason.
6. Register every physical item separately with a unique asset number; add accessories as separate assets and link them to parent devices. Capture photos, location, condition and optional serial/warranty/purchase fields. Create test issue requests, authorize them, physically issue as the assigned custodian, record borrower acknowledgement, create/acknowledge a shift handover, and test partial returns/missing items.
7. The Head opens **TBC Digital social media**, registers each verified public account profile (name/handle only, no password or token), and designates the reporting officer. The officer enters each platform's weekly figures from its analytics screen or uses the preview-and-validate Excel/CSV import; attach evidence and submit. The Head reviews; quarterly reports consolidate approved weekly records. See [Social media reporting](docs/SOCIAL_MEDIA_REPORTING.md). Do not enter invented sample statistics.
8. Configure a static IP or DHCP reservation. From office devices, open `http://<reserved-server-ip>:8000` only after firewall/network checks and temporarily use test records.
9. Configure HTTPS with an organization-approved certificate before sending credentials over Wi-Fi or entering real data; see the security guide.

Initial Docker image/package downloads require network access. After installation, the application and UI assets are local; PostgreSQL remains private to Docker and the browser does not need internet connectivity. Docker Desktop must be configured to start when the server user's Windows session starts. Container `restart: unless-stopped` restarts services when Docker is available; the optional logon task is not a Windows service and does not start Docker before user logon.

## First-time database and administrator commands

The Windows installer runs these inside the app container:

```powershell
docker compose exec -T web python -m app.cli init-db
docker compose exec web python -m app.cli create-admin
```

Never publish a bootstrap administrator endpoint to the network. The CLI prompts for the password without echoing it. Admin accounts configure the system but do not approve timetables or verify tasks unless they also have an explicitly assigned business account/role.

## Development and tests

Python 3.11+, PostgreSQL for full local development, and Docker Compose for the server stack are intended. Create a virtual environment before installing packages:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --test tests/test_social_charts.cjs
```

Tests use an isolated file-backed SQLite database per test and cover auth/CSRF/role separation, timetable approval/versioning, task submission/review, equipment custody, and manual social media workflows: all five platform accounts, source attribution, N/A and calculations, evidence uploads, weekly correction/approval, CSV import preview/duplicate prevention, quarterly roll-up/approval, and PDF/XLSX exports. `node --test tests/test_social_charts.cjs` tests the generated SVG chart output. These automated tests use synthetic fixtures in isolated test databases and do **not** prove live social profile correctness, browser appearance, PostgreSQL/Docker/Windows deployment, or office-network acceptance.

To use Compose, copy `.env.example` to `.env`, replace both example secrets, choose `APP_BIND_IP` and an office `APP_PORT`, then run `docker compose up --build -d`. PostgreSQL port 5432 is never published. Do not run `docker compose down -v` on a working installation; it deletes the database volume.

## Backups and recovery

`backup_database.bat` captures a custom-format PostgreSQL dump and uploads ZIP in one timestamped folder, verifies the dump/archive, records SHA-256 hashes and applies `BACKUP_RETENTION_DAYS`. The service is paused briefly to keep the database/files snapshot paired. `restore_database.bat` verifies the manifest, requires typing `RESTORE`, restores both parts and preserves the previous uploads folder. See [Backup and recovery](docs/BACKUP_RECOVERY.md). `install_backup_task.bat` registers a daily scheduled backup (requires an administrator terminal and local Windows account password prompt). **Backups are not a substitute for a second protected off-host copy. Run a restore drill before live data.**

## Project documentation

- [Windows 11 installation and LAN setup](docs/WINDOWS_INSTALLATION.md)
- [User manual](docs/USER_MANUAL.md)
- [Equipment & shift custody module](docs/EQUIPMENT_MANAGEMENT.md)
- [TBC Digital social media reporting](docs/SOCIAL_MEDIA_REPORTING.md)
- [System architecture](docs/ARCHITECTURE.md)
- [Security and deployment gates](docs/SECURITY.md)
- [Backup and recovery](docs/BACKUP_RECOVERY.md)
- [Tests and coverage](docs/TESTING.md)
- [Roadmap / acceptance status](docs/ROADMAP.md)

## Branding, privacy and license

The supplied emblem and TBC Digital logo are kept at their original proportions in local assets. Confirm institutional rights before redistribution. Use only fake/test information in development. No project license has been selected yet.

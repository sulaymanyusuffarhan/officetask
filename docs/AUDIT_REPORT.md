# Office Task system technical audit and QA report

**Audit date:** 2026-11-17 (UTC)  
**Repository:** `sulaymanyusuffarhan/officetask`  
**Audited branch:** `arena/d97c4ec5-officetask`  
**Base:** merged PR #4 commit `62a9816e94503eca6f6a33418937b4580680dfe3`  
**Overall decision: BLOCKED for production acceptance.** Available code-level checks passed, but production deployment criteria below have not been exercised. This report is not a security certification or a claim of Windows/PostgreSQL/LAN acceptance.

## Status key

- **PASS** — the stated check was executed in this audit and passed.
- **FAIL** — an executed check failed or a verified defect remains.
- **NOT TESTED** — no execution/evidence was available for the check.
- **BLOCKED** — acceptance is prevented by an unavailable prerequisite or environment.

## Executed checks and results

| Area | Status | Evidence and scope |
|---|---|---|
| Automated application tests | **PASS** | `.venv/bin/pytest -q`: **17 passed**, 1 Starlette/httpx deprecation warning, in 22.60 seconds. Tests use isolated SQLite databases; this is not a PostgreSQL compatibility result. |
| Python syntax/bytecode compilation | **PASS** | `.venv/bin/python -m compileall -q app alembic tests` completed successfully. |
| Browser JavaScript syntax | **PASS** | `node --check app/static/js/app.js` completed successfully. No browser was available for visual or interactive testing. |
| Alembic revision graph | **PASS** | `.venv/bin/alembic heads` reports one head, `bf8103392858`. |
| Migration SQL generation | **PASS** | `.venv/bin/alembic upgrade head --sql` generated 508 lines of PostgreSQL-dialect offline SQL, ending at `bf8103392858`. This generated SQL was **not applied** to a live PostgreSQL server. |
| Auth and selected backend role gates | **PASS** | Automated tests cover unauthenticated access, CSRF rejection, rate limiting, selected allowed/denied reads for all six roles, employee self-verification denial, and system-admin separation from business workflow permissions. These tests are not an exhaustive per-route authorization proof. |
| Timetable workflow | **PASS** | API test creates/edits a weekly plan, rejects overlapping assignments, submits, approves and publishes it, confirms a published plan cannot be edited, creates version 2, and checks the employee-facing published view. |
| Task workflow and reports | **PASS** | API tests cover assignment from a published shift, employee acknowledge/start/submit, separate editor verification, correction/resubmission and management reopen audit; performance/analytics, CSV/PDF/XLSX endpoints are exercised. |
| Attachment controls | **PASS** | API test rejects an executable extension, accepts a signature-checked PNG fixture, checks authorized download and private test-directory storage. Not antivirus testing or real browser upload testing. |
| Equipment custody and accountability scenarios | **PASS** | API tests exercise unique assets/accessories, authorization policy, actual custodian and replacement restrictions, separate requester/authorizer/issuer/borrower/receiver identities, internal and external acknowledgement, shift handover acknowledgements, partial return, missing item, damage hold, inspection, event history and reports. These are API tests with SQLite and fixtures, not a physical device trial. |
| Seven independent application sessions | **PASS (limited)** | Test opens seven independent in-process `TestClient` sessions and concurrently performs reads using a thread pool against SQLite. This is not a network, PostgreSQL lock-contention, or office load test. |
| Security headers and local branding | **PASS** | Test verifies CSP-related response security headers and loads local emblem/logo endpoints with PNG/JPEG content types. The supplied `app/static/images/emblem.png` (tracked, 880×870) and `app/static/images/tbc-digital-logo.jpg` (tracked, 1028×1028) were left unchanged. |
| Sensitive-file exclusion | **PASS (source inspection)** | `.gitignore` excludes `.env`, storage uploads/backups, SQL dumps and SQLite database files. No credentials, real staff records, backup, or dump were added by this audit. |
| Source defects requiring changes | **PASS / none reproduced** | The executed checks did not reproduce a source-code defect; no code fix was warranted by this audit run. This does not establish absence of defects outside the tested coverage. |

## Unverified acceptance criteria and blockers

| Area | Status | Why / required next evidence |
|---|---|---|
| Windows 11 install/start/stop/update and scheduled tasks | **BLOCKED** | This audit host is Linux and has no `powershell`, `pwsh`, or Docker CLI. Run the beginner steps in [`WINDOWS_INSTALLATION.md`](WINDOWS_INSTALLATION.md) on the intended Windows 11 server; capture Compose health, startup-after-reboot, firewall scope, and task scheduler results. |
| Docker Compose image build and deployment runtime | **BLOCKED** | Docker is unavailable here. `docker-compose.yml`, scripts and their instructions were inspected, but they were not run. |
| PostgreSQL migrations and live application readiness | **BLOCKED** | No live PostgreSQL service was available. Offline SQL generation is not an applied upgrade, migration rollback, or `alembic check`. Test upgrade/current/check and application readiness on the intended PostgreSQL 16 deployment. |
| Real browser UI and accessibility | **NOT TESTED** | No Chromium/Chrome browser binary was available. `TestClient` and JavaScript syntax checks do not verify layout, keyboard/screen reader behavior, all UI paths or browser compatibility. |
| All six roles across every route/action | **NOT TESTED (exhaustively)** | Existing API tests prove representative positive and negative backend permissions, not a complete route-by-route authorization matrix. Complete route coverage with the deployment's finalized user/role policy before go-live. |
| Seven physical computers / office Wi-Fi / subnet restrictions | **BLOCKED** | No Windows server, office network, client devices or separate untrusted network were available. Verify permitted and denied client access and confirm TCP 5432 is not host-published; do not use router port forwarding. |
| Simultaneous PostgreSQL writes, races and transaction/locking behavior | **NOT TESTED** | The seven-session test uses concurrent reads on SQLite. It does not simulate concurrent issue/return, planner edits, or PostgreSQL row locks/unique races. |
| Backup, off-host copy, and destructive restore drill | **BLOCKED** | PowerShell/Docker and a deployment database/upload set are unavailable. Script inspection and checksum code are not evidence of a successful backup or restore. Run a paired database-and-upload restore against a disposable test deployment, verify a real attachment, and retain an off-host protected copy. |
| HTTPS and production cookie behavior on the office network | **NOT TESTED** | No TLS reverse proxy/certificate or network endpoint was available. Compose defaults to HTTP; do not send real credentials/data over untrusted Wi-Fi. |
| Penetration test, antivirus, privacy/legal approval | **NOT TESTED** | No independent security assessment, malware scanning service, or institutional privacy approval was performed. See [`SECURITY.md`](SECURITY.md) for known gaps and go-live gates. |

## Findings and go-live decision

1. No reproducible defect emerged from this execution; there are no claimed fixes or hidden test failures.
2. The automated suite is useful code-level workflow evidence, but its test database is SQLite. It cannot establish the behavior of the intended PostgreSQL deployment, Windows networking, browser UX, backups, or operational recovery.
3. HTTP is not encrypted. Configure institution-approved HTTPS and trusted certificates before real passwords or personal data are entered. Keep PostgreSQL private to the Compose network and restrict the app firewall rule to the approved office subnet. Never add router port forwarding.
4. Backup/restore tools must be run and a restore drill completed before operational reliance. Keep paired database/uploads off-host in protected storage.
5. **Do not mark the system production-ready based on this audit.** The overall acceptance remains **BLOCKED** until the deployment-specific checks in this table and the final checklist in [`WINDOWS_INSTALLATION.md`](WINDOWS_INSTALLATION.md) are completed and documented by the responsible IT operator.

## Reproduction commands used

```bash
.venv/bin/pytest -q
node --check app/static/js/app.js
.venv/bin/python -m compileall -q app alembic tests
.venv/bin/alembic heads
.venv/bin/alembic upgrade head --sql > /tmp/officetask-migrations.sql
```

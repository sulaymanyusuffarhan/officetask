# Delivery and acceptance status

Implementation exists for the following workflows, but passing a unit test or having a script in Git does not equal production acceptance.

| Phase | Scope | Status |
|---|---|---|
| 1 | Repository foundation, architecture, supplied assets, environment and Compose scaffolding | Implemented |
| 2 | Normalized schema/migrations, Argon2 password login, signed sessions, CSRF, role checks, bootstrap CLI | Implemented; Windows/PostgreSQL sign-off pending |
| 3 | Accounts, roles, departments and shifts | Implemented in MVP; permission catalogue is code-defined, not an admin-editable permission matrix |
| 4 | Weekly plan creation/copy, allocation, conflict validation, review/approval/publication/versioning | Implemented in MVP; acceptance exercise pending |
| 5 | Individual task assignments, accountability, due dates/priorities and status history | Implemented in MVP |
| 6 | Employee progress, written submission, private attachments and resubmission | Implemented in MVP; malware scanning not included |
| 7 | Editor/head review, correction/rejection/verification and audit actions | Implemented in MVP |
| 8 | Attendance exceptions and shift/day handovers | Implemented in MVP; compare-by-date endpoint available |
| 9 | Live management counters, planned-vs-actual, filters and PDF/Excel/CSV output | Implemented in MVP; chart-level client visualization is basic, live metrics are DB-backed |
| 10 | Audit history and paired DB/uploads backup/restore utilities | Code implemented; Windows restore drill/off-host backup integration pending |
| 11 | Windows installer/start/stop/firewall/backup/restore/scheduled-task scripts | Scripts provided; not executed on Windows 11 in this environment |
| 12 | Full PostgreSQL/Windows/seven-device acceptance and operational documentation | Incomplete; unit/API tests run, but production and concurrent-user acceptance still required |

## Remaining go-live blockers

1. Configure institution-approved HTTPS on the LAN (default Compose service is HTTP).
2. Execute Windows 11 install, firewall and auto-start procedure on the actual server.
3. Verify PostgreSQL migrations and all scripts against the supported Docker Desktop/PostgreSQL versions.
4. Exercise at least two simultaneous clients and all six roles, including restricted network testing.
5. Restore both database and files from an off-host backup and verify representative records/attachments.
6. Have institutional security/privacy staff approve handling, TLS, retention, attachment scanning and audit practices.

Do not mark the product production-ready until every blocker has evidence and the acceptance test suite is expanded.

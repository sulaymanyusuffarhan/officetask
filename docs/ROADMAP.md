# Delivery roadmap and phase gates

This list tracks implementation truthfully. Mark a milestone complete only after its tests and documentation exist.

| Phase | Scope | Status |
|---|---|---|
| 1 | Repository foundation, architecture, local branding, configuration, PostgreSQL/Compose/Alembic scaffolding, smoke tests | **Implemented in this change** |
| 2 | Database schema, migrations, secure authentication, sessions, role/permission enforcement and bootstrap administrator | Not started |
| 3 | User, employee, department and shift administration | Not started |
| 4 | Weekly timetable draft/copy, conflict checks, submission/review/return, approval, publication and version history | Not started |
| 5 | Individual accountable task assignments, priorities, deadlines and task-state history | Not started |
| 6 | Employee acknowledgment/progress, written submissions, secure attachments and resubmission | Not started |
| 7 | Editor/head review, correction/rejection/verification workflow and audit events | Not started |
| 8 | Attendance/absence inputs, shift handovers and end-of-shift/day reporting | Not started |
| 9 | Database-backed management dashboard, planned-vs-actual, filters and PDF/Excel reports | Not started |
| 10 | Security hardening, append-only audit policy, scheduled paired DB/file backups and tested restore | Not started |
| 11 | Windows 11 install/start/stop/firewall/auto-start and backup/restore documentation/scripts | Not started |
| 12 | End-to-end authorization, workflow, concurrency, recovery and deployment acceptance tests; user/system documentation | Not started |

## Exit gates

Each phase must add its own automated tests and update the user/deployment documentation. Before live use, the complete acceptance plan must demonstrate a fresh Windows 11 installation, restricted LAN access from multiple clients, no direct employee database access, role separation, timetable version safety, task submission and review, report accuracy, auditability, and a successful database-plus-file restore. Existing phase-one smoke tests do not satisfy these gates.

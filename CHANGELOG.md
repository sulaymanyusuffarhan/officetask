# Changelog

## Unreleased — operational MVP workflows

- Added the normalized office workflow schema and Alembic migrations for users, roles, shifts, schedules, tasks, submissions, attachments, reporting and audit records.
- Implemented Argon2 authentication, signed sessions, CSRF checks, role authorization, CLI initialization and admin account management.
- Added weekly timetable editing/review/publication/versioning and individual employee task assignment/submission/verification APIs plus browser screens.
- Added private validated attachment upload/download, shift handover/attendance, management analytics and PDF/Excel/CSV exports.
- Added Windows 11 PowerShell/batch setup, start/stop, restricted firewall, backup/restore and scheduled-task utilities.
- Expanded tests and documentation. Actual Docker Desktop/Windows, LAN, TLS, concurrency and recovery acceptance remain pending.

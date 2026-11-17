# Backup and recovery operations

## Backup contents

Each timestamped directory under `storage/backups/` contains:

- `database.dump`: PostgreSQL custom-format full logical dump.
- `uploads.zip`: paired private upload-folder archive.
- `manifest.json`: UTC creation time and SHA-256 for both artifacts.

`backup_database.bat` pauses the web container briefly to avoid capturing database metadata and uploaded files at different points in a submission; PostgreSQL remains online. It verifies the dump with `pg_restore --list`, archives uploads, records hashes and prunes timestamped backup directories older than `BACKUP_RETENTION_DAYS` (default 30). If the backup fails, the script attempts to restart the web container and retains the incomplete folder for inspection.

## Run manually

1. Confirm Docker Desktop is running and disk space is adequate.
2. Run `backup_database.bat` from the server. Expect a short web interruption while writes are paused.
3. Check that a new folder has database.dump, uploads.zip and manifest.json. Check output for successful verification.
4. Copy the completed folder to a separate protected/offline location. Keep confidentiality controls and encryption appropriate to personnel data.
5. A local copy on the server is not disaster recovery if that disk fails or is stolen.

## Daily schedule

Run `install_backup_task.bat` from an elevated PowerShell/Command Prompt. It asks for the Windows account password locally (never send it to anyone); Windows Task Scheduler uses this account at 11 PM daily. Docker Desktop must be available in this account. After registering, run the task once manually and check Task Scheduler's Last Run Result and backup output. The task does not prove an off-host copy exists.

## Restore (destructive)

Restore overwrites current database state and upload files. Plan a maintenance window and notify users.

1. Confirm the selected timestamp folder contains all three files and copy it from protected backup media into `storage/backups/`.
2. Verify the backup folder path and check that `.env`/Compose services refer to the intended database.
3. Run `restore_database.bat`, provide the backup folder path when prompted, inspect the manifest verification, and type exactly `RESTORE` to confirm.
4. The script verifies both SHA-256 hashes and expands the uploads archive before stopping the web service. PostgreSQL restore uses a single transaction; on completion, the former uploads directory is preserved as `uploads-pre-restore-<timestamp>`.
5. Check `/api/health/live` and `/api/health/ready`, sign in, verify representative schedules/tasks/attachments, and retain the old directory until approved.

If restore fails, the application may remain stopped for safety. Inspect the PowerShell error, `docker compose logs db`, and the preserved data; escalate to the server administrator rather than deleting a volume. Test the procedure against a copy before live data is entered.

## Retention and verification

The script automatically removes only correctly named timestamp directories older than configured retention. Adjust policy with the institution's records/security officer. Review disk usage, successful runs, checksums, and a sample restore at least quarterly. Add off-host copying/encryption in an IT-approved process; that automation is intentionally not included because credentials and external backup targets are organization-specific.

param([Parameter(Mandatory=$false)][string]$BackupPath)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not $BackupPath) { $BackupPath = Read-Host 'Path to the timestamped backup folder (for example storage/backups/2026-11-17_23-00-00)' }
$root = (Resolve-Path 'storage/backups').Path
$folder = (Resolve-Path $BackupPath).Path
if (-not $folder.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { throw 'Restore path must be inside this repository storage/backups folder.' }
$manifestPath = Join-Path $folder 'manifest.json'
$dbDump = Join-Path $folder 'database.dump'
$uploadsZip = Join-Path $folder 'uploads.zip'
if (-not (Test-Path $manifestPath) -or -not (Test-Path $dbDump) -or -not (Test-Path $uploadsZip)) { throw 'Backup set is incomplete; restore cancelled.' }
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
if ((Get-FileHash $dbDump -Algorithm SHA256).Hash -ne $manifest.database_sha256 -or
    (Get-FileHash $uploadsZip -Algorithm SHA256).Hash -ne $manifest.uploads_sha256) { throw 'Backup checksums do not match manifest; restore cancelled.' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop is required.' }
$confirmation = Read-Host 'This OVERWRITES live database and uploaded files. Type RESTORE to continue'
if ($confirmation -cne 'RESTORE') { Write-Host 'Restore cancelled.'; exit 0 }

$extract = Join-Path (Get-Location) ("storage/restore-tmp-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force $extract | Out-Null
try {
  Expand-Archive -Path $uploadsZip -DestinationPath $extract -Force
  $restoredUploads = Join-Path $extract 'uploads'
  if (-not (Test-Path $restoredUploads -PathType Container)) { throw 'Backup archive did not contain expected uploads directory.' }
  docker compose stop web
  if ($LASTEXITCODE -ne 0) { throw 'Could not stop the application before restore.' }
  $relativeDump = (Resolve-Path $dbDump).Path.Substring($root.Length).TrimStart('\','/') -replace '\\','/'
  $containerDump = '/backups/' + $relativeDump
  $restoreCommand = "pg_restore --clean --if-exists --no-owner --exit-on-error --single-transaction -U `"`$POSTGRES_USER`" -d `"`$POSTGRES_DB`" `"$containerDump`""
  docker compose exec -T db sh -c $restoreCommand
  if ($LASTEXITCODE -ne 0) { throw 'Database restore failed; application remains stopped for safety.' }
  $uploadsPath = Join-Path (Get-Location) 'storage/uploads'
  $oldPath = Join-Path (Get-Location) ("storage/uploads-pre-restore-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
  if (Test-Path $uploadsPath) { Move-Item $uploadsPath $oldPath }
  Move-Item $restoredUploads $uploadsPath
  docker compose start web
  if ($LASTEXITCODE -ne 0) { throw "Data restored but app did not restart. Old uploads retained at $oldPath" }
  Write-Host 'Database and upload files restored together. Verify /api/health/ready and perform an application check.' -ForegroundColor Green
} finally {
  if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
}

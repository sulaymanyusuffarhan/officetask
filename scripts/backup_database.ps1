$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path '.env')) { throw '.env missing; backup aborted.' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop is required.' }
$stamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$backup = Join-Path (Get-Location) "storage/backups/$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
$containerPath = "/backups/$stamp/database.dump"
$stopped = $false
try {
  # Quiesce writes so database and upload snapshots represent the same point in time.
  docker compose stop web
  if ($LASTEXITCODE -ne 0) { throw 'Could not pause the web service for a consistent backup.' }
  $stopped = $true
  $dumpCommand = "pg_dump -Fc -U `"`$POSTGRES_USER`" `"`$POSTGRES_DB`" -f `"$containerPath`""
  docker compose exec -T db sh -c $dumpCommand
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL dump failed; incomplete backup directory retained.' }
  $dumpHost = Join-Path $backup 'database.dump'
  if (-not (Test-Path $dumpHost) -or (Get-Item $dumpHost).Length -lt 100) { throw 'Database dump is missing or unexpectedly small.' }
  docker compose exec -T db pg_restore --list $containerPath | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL backup verification failed.' }
  $uploadsZip = Join-Path $backup 'uploads.zip'
  Compress-Archive -Path (Join-Path (Get-Location) 'storage/uploads') -DestinationPath $uploadsZip -CompressionLevel Optimal -Force
  if (-not (Test-Path $uploadsZip) -or (Get-Item $uploadsZip).Length -lt 20) { throw 'Upload archive verification failed.' }
  $manifest = [ordered]@{
    created_utc = [DateTime]::UtcNow.ToString('o')
    database_dump = 'database.dump'
    database_sha256 = (Get-FileHash $dumpHost -Algorithm SHA256).Hash
    uploads_archive = 'uploads.zip'
    uploads_sha256 = (Get-FileHash $uploadsZip -Algorithm SHA256).Hash
    note = 'Restore the database and uploads archive together. Keep an additional protected off-host copy.'
  }
  $manifest | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $backup 'manifest.json')
  Write-Host "Verified paired database + upload backup: $backup" -ForegroundColor Green
} finally {
  if ($stopped) {
    docker compose start web
    if ($LASTEXITCODE -ne 0) { Write-Error 'Backup finished but the web service did not restart; inspect Docker Compose immediately.' }
  }
}

$retention = 30
$line = Get-Content '.env' | Where-Object { $_ -match '^BACKUP_RETENTION_DAYS=' } | Select-Object -First 1
if ($line) { $parsed = 0; if ([int]::TryParse(($line -split '=',2)[1], [ref]$parsed) -and $parsed -ge 1) { $retention = $parsed } }
$cutoff = (Get-Date).AddDays(-$retention)
Get-ChildItem 'storage/backups' -Directory | Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$' -and $_.LastWriteTime -lt $cutoff } | Remove-Item -Recurse -Force
Write-Host "Retention cleanup complete (older than $retention days). Verify backup media and keep an off-host copy."

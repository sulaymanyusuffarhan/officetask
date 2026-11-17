$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop is required.' }
docker compose stop
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the application containers.' }
Write-Host 'Containers stopped; persistent data volumes and local uploaded files were preserved.'

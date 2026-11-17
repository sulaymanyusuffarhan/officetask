$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path '.env')) { throw '.env is missing. Run install_windows.bat first.' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop is required. Install and start it first.' }
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw 'Could not start the application containers.' }
docker compose ps

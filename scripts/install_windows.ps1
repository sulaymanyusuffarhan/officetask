$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

function Assert-Docker {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker CLI is not installed. Install Docker Desktop for Windows 11, start it, then rerun.' }
  docker compose version | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Docker Compose v2 is required.' }
}
function New-UrlSafeSecret([int]$Length) {
  $bytes = New-Object byte[] $Length
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','A').Replace('/','B')
}

Assert-Docker
New-Item -ItemType Directory -Force -Path 'storage\uploads','storage\backups' | Out-Null
if (-not (Test-Path '.env')) {
  Copy-Item '.env.example' '.env'
  $text = Get-Content '.env' -Raw
  $text = $text.Replace('replace-this-with-at-least-32-random-bytes', (New-UrlSafeSecret 48))
  $text = $text.Replace('replace-with-a-unique-long-password', (New-UrlSafeSecret 32))
  Set-Content -Path '.env' -Value $text -Encoding ascii
  Write-Host 'Created .env with generated random secrets. Restrict this file with Windows ACLs; do not share it.' -ForegroundColor Yellow
} else {
  Write-Host 'Keeping existing .env unchanged.' -ForegroundColor Yellow
}
$subnet = Read-Host 'Office Wi-Fi subnet in CIDR (example 192.168.1.0/24); leave empty to configure firewall manually'
if ($subnet) {
  if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this installer as Administrator to create the restricted Windows Firewall rule.'
  }
  if ($subnet -notmatch '^\d{1,3}(\.\d{1,3}){3}/\d{1,2}$') { throw 'Enter a subnet in IPv4 CIDR format.' }
  Get-NetFirewallRule -DisplayName 'Office Task Server (office LAN only)' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
  New-NetFirewallRule -DisplayName 'Office Task Server (office LAN only)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -RemoteAddress $subnet -Profile Domain,Private | Out-Null
  Write-Host "Firewall allows TCP 8000 only from $subnet. Verify this matches the trusted office network."
} else {
  Write-Warning 'No firewall rule was created. Configure Windows Defender Firewall to permit TCP 8000 only from your office subnet before client access.'
}

docker compose config | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'docker compose configuration is invalid; inspect .env and docker-compose.yml.' }
Write-Host 'Building and starting application and PostgreSQL; first build requires network access to download container images/packages.'
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed to start.' }
docker compose exec -T web python -m app.cli init-db
if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed.' }
Write-Host ''
Write-Host 'Create the first technical administrator. This account does not get timetable approval or task verification rights.' -ForegroundColor Cyan
docker compose exec web python -m app.cli create-admin
if ($LASTEXITCODE -ne 0) { throw 'Administrator account creation failed.' }
Write-Host 'Installation foundation ready. Open http://<server-LAN-IP>:8000 from the server and office clients.' -ForegroundColor Green
Write-Host 'Next: create a Head of Office account and planner/editor/staff accounts from Accounts & setup. Restrict access and complete the security/backup checks before entering real data.'

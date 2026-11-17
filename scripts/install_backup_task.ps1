$ErrorActionPreference = 'Stop'
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw 'Open PowerShell as Administrator to register a daily protected backup task.'
}
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot 'backup_database.ps1'
$taskName = 'OfficeTask-Daily-Verified-Backup'
$account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$password = Read-Host "Windows password for $account (needed by Task Scheduler when nobody is signed in)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($password)
try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At '11:00 PM'
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Password -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -User $account -Password $plain -Force | Out-Null
$plain = $null
Write-Host "Registered $taskName to run daily at 11:00 PM as $account. Run it once manually and verify its backup before relying on it." -ForegroundColor Green

# Windows 11 installation and office LAN guide

## Important readiness warning

Windows scripts in this repository are authored but have not been executed on a Windows 11 + Docker Desktop host in this development environment. Before live use, have an administrator review the generated firewall rule, test seven client sessions, configure trusted TLS for the office network and complete a restore drill. The default Compose endpoint is HTTP; do not send passwords over untrusted Wi-Fi until HTTPS is configured.

## 1. Server and network preparation

1. Select one office Windows 11 computer with supported virtualization enabled, reliable power, enough disk for the database and growing attachment/backups, and restricted physical access.
2. Install Docker Desktop for Windows and allow its supported WSL 2 / virtualization setup. Start Docker Desktop and wait for `docker info` to work. Docker Desktop is external software and is not bundled in the repository.
3. Reserve the server address in the office router's DHCP settings (recommended), or assign a static address approved by IT. Record the network name, address, gateway and subnet. Never create a public router port-forward.
4. Keep PostgreSQL private. Compose intentionally exposes only the app port; employee PCs must not connect to TCP 5432.
5. Do not connect the application to a public Wi-Fi network. Prefer a trusted WPA2/WPA3 office network and firewall it to the office subnet.

## 2. Install

1. Download the repository ZIP from GitHub, extract it to a stable path such as `C:\OfficeTask`, and keep the folder in place (scheduled tasks refer to its path).
2. Right-click **Windows PowerShell → Run as administrator**, `cd` to the extracted folder, and run `install_windows.bat`.
3. The script checks Docker Compose, creates local storage directories, creates `.env` with random non-placeholder secrets if it does not exist, and asks for the office IPv4 CIDR (for example `192.168.1.0/24`). It adds an inbound TCP 8000 allow rule scoped to that remote subnet on Domain/Private profiles. Use the subnet confirmed by IT, not the example. If left blank, configure the firewall manually before client access.
4. The script validates Compose, builds/starts containers, runs Alembic migrations, seeds roles/departments/shifts and asks for the initial system administrator username/name/password.
5. Protect `.env` in File Explorer → Properties → Security. Only the server operator and authorized Windows administrators should read it. Never upload it to GitHub or send it in chat.
6. In Docker Desktop, enable **Start Docker Desktop when you sign in** for the Windows account that owns the app. The containers use `restart: unless-stopped`; they restart when the Docker engine starts. Optional `install_autostart_task.bat` starts Compose at that account's logon, but does not run Docker before sign-in.

The script may need outbound internet on first build to fetch container images and Python packages. Once built, browser access and the application assets are served locally.

## 3. HTTPS and credentials

The default compose mapping is `http://<server-ip>:8000`. Session cookies are HttpOnly, SameSite=Strict, and CSRF-protected, but HTTP does not encrypt network traffic. Obtain/configure an organization-approved certificate and HTTPS reverse proxy for the office server name/IP before sending real passwords over Wi-Fi. The application container does not yet provision LAN certificates or distribute a trusted CA to the six employee computers. Do not expose the service to the internet or router WAN while configuring TLS.

## 4. Verify firewall and local operation

On the server, run:

```powershell
docker compose ps
Invoke-WebRequest http://localhost:8000/api/health/live
Invoke-WebRequest http://localhost:8000/api/health/ready
Get-NetFirewallRule -DisplayName 'Office Task Server (office LAN only)' | Format-List
```

Both health endpoints should return 200 (readiness confirms PostgreSQL). Check that no host listener exposes port 5432. Keep Docker Desktop firewall integration and Windows Defender Firewall enabled.

From an authorized office computer, browse to `http://<reserved-server-ip>:8000`. Test a device outside the allowed subnet (where policy permits) and confirm it cannot connect. If clients cannot connect, check the server address, Wi-Fi isolation/VLAN policy, firewall remote subnet/profile, Docker Desktop status and TCP 8000; do not solve this by opening the firewall to all networks.

## 5. First accounts and setup

1. Sign in with the CLI-created System Administrator account.
2. In **Accounts & setup**, create the Head of Office, timetable planner, editors, shift leaders and employees. Use unique usernames and temporary passwords of at least 12 characters. Give passwords to staff using the institution's approved secure channel.
3. Create departments and configure shift names/hours. Avoid assigning the System Administrator to business workflows.
4. Sign in as the planner, create Monday-starting weekly plans, allocate staff, editors and leaders, then submit.
5. Sign in as the Head of Office, review/return/approve and publish. Once published, use a reasoned new version for corrections.
6. Editors create one task record per accountable employee. Employees acknowledge, progress, submit written reports and allowed attachments. Editors verify, request corrections or reject with a reason. Head dashboard and reports distinguish submitted from verified work.

## 6. Start, stop and scheduled tasks

- Start: `start_server.bat` (Compose `up -d`, persistent data retained).
- Stop: `stop_server.bat` (stops containers without deleting data).
- Optional start at user logon: run `install_autostart_task.bat`; configure Docker Desktop to start at sign-in too.
- Do not use `docker compose down -v` except when intentionally destroying all database data.

## 7. Update procedure

Before a code update, create and verify a paired backup, ensure an off-host copy exists, stop the service, replace application source with a reviewed release, start/build containers, apply migrations, and check health/workflows. Never overwrite `.env`, `storage/uploads`, or backup folders with a repository ZIP. Test updates against a copy of the database first.

## Troubleshooting

- **Docker engine unavailable:** open Docker Desktop and wait; reboot only after confirming persistence and backups.
- **HTTP 503 readiness:** check `docker compose logs db`, database volume health and `.env`; do not delete volumes as a troubleshooting shortcut.
- **Address/port in use:** edit `APP_PORT` and firewall rule consistently, then run `docker compose up -d`.
- **Client blocked:** validate the correct server IPv4/subnet and Windows network profile; keep the rule subnet-restricted.
- **Login fails after changing secret:** `SECRET_KEY` change invalidates existing signed sessions; sign in again. Do not rotate DB credentials without updating all Compose environment settings in the same maintenance window.
- **Restore required:** use the tested procedure in `BACKUP_RECOVERY.md` and verify both health endpoints before allowing staff back in.

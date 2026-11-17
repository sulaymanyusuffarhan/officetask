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

The script may need outbound internet on first build to fetch container images and Python packages. Once built, browser access and the application assets are served locally. `.env` defaults `OFFICE_TIMEZONE=Africa/Dar_es_Salaam`; change it to the office's valid IANA timezone before staff use shift dashboards and issue/return dates. Transaction timestamps are stored in UTC.

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
6. In **Equipment & custody**, the Head first saves the authorized-borrower roles (until configured, authorization is denied), then the Head/System Administrator assigns dated custodians for Morning/Afternoon/Evening shifts. Register each device and accessory as a separate asset with a unique asset number; link accessories and add photo, current location, condition, optional serial, purchase and warranty details. Test request → authorization → actual custodian issue → borrower acknowledgement → cross-shift handover → partial return/missing → inspection with test records.
7. Editors create one task record per accountable employee. Employees acknowledge, progress, submit written reports and allowed attachments. Editors verify, request corrections or reject with a reason. Head dashboard and reports distinguish submitted from verified work.
8. In **TBC Digital social media**, the Head registers the verified public account profile for YouTube, Facebook, Instagram, X and TikTok and designates the reporting officer. Do not enter social passwords or API credentials. The officer copies weekly figures from official platform analytics, marks unavailable values N/A, attaches screenshot/report evidence and submits; the Head reviews. Quarterly reports consolidate approved weekly submissions. No official handles or statistics are prefilled. See [Social media reporting](SOCIAL_MEDIA_REPORTING.md).

See [Equipment & shift custody](EQUIPMENT_MANAGEMENT.md) for detailed role permissions, workflow, reports and scenario test. Migration `a1b2c3d4e5f6` adds the manual-first social reporting tables; the normal installer / `python -m app.cli init-db` update path applies it.

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
- **Restore required:** follow the documented procedure in `BACKUP_RECOVERY.md` only after your IT administrator has completed a restore drill on a disposable deployment. Verify both health endpoints and a representative attachment before allowing staff back in.

## 8. Setup on the other six office computers (no app install)

The six client computers do **not** need Python, Docker, PostgreSQL or a downloaded application. They use a supported, updated browser over the same trusted office Wi-Fi/LAN.

On **each of the six** computers:

1. Connect to the approved office Wi-Fi/VLAN. Do not use guest Wi-Fi if it is isolated from the server, and do not connect through a public network/VPN unless IT has approved the route.
2. In a browser, enter the same server URL: `https://<office-server-name-or-reserved-IP>/` once IT has configured trusted HTTPS. During an isolated test only, the current unencrypted app is at `http://<reserved-server-ip>:8000/`; never enter real passwords over HTTP on an untrusted network.
3. If IT configured a private certificate authority, have IT install/trust its certificate using the organization's managed device policy. Do not click through certificate warnings or install a certificate file from an unverified source.
4. Bookmark the approved internal URL. Confirm the institutional emblem and TBC Digital logo display.
5. Sign in with that person's individual username/password. The administrator creates accounts on the server; do not share credentials or use the system administrator account for daily work.
6. Verify the role-appropriate pages (employee tasks/timetable; editor assignment/review; planner draft; head approvals/reports; shift leader handover; admin setup). Sign out on a shared computer.
7. Ask IT to test an unauthorized subnet and confirm the app is blocked there. Do not open PostgreSQL port 5432 or add router port forwarding.

The office URL and accounts are the same across all six clients; database and uploads remain on the Windows server. Client-side caches must not be used for confidential documents.

## 9. Final installation checklist

- [ ] Windows 11 server reserved/static IP and approved trusted LAN.
- [ ] Docker Desktop starts and Compose reports healthy services after a Windows restart/login.
- [ ] `.env` contains generated unique secrets and has restricted ACLs.
- [ ] `docker compose exec -T web python -m app.cli init-db` succeeds; `/api/health/ready` returns 200.
- [ ] No host-published PostgreSQL port; firewall allows only the office subnet.
- [ ] Trusted HTTPS configured and verified on all seven computers before entering actual credentials/data.
- [ ] One individual account for each person, correct role and department, no shared daily-admin login.
- [ ] Planner/head/editor/staff workflows checked with test records.
- [ ] Daily paired database/uploads backup verified and copied off-host.
- [ ] Restore drill passed; application/data reopened and sample attachment retrieved.

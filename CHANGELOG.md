# Changelog

All notable changes to PatchPilot are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.1] - 2026-03-25

### Changed
- Dashboard "Update All Agents" button replaced with "Patch All VMs" — only targets VMs with pending updates
- Patch All button highlighted (primary variant) when updates are available, ghost when none
- Register key no longer leaked as hash on page reload — shows "Active key expires in X:XX" instead
- Deploy page shows oneliner and full script immediately with `<KEY>` placeholder (no double-generate needed)

### Fixed
- Register key hash was returned to UI on GET /api/register-key (now returns `key: null`)

## [1.0.0] - 2026-03-25

First stable release.

### Features
- **Dual-port architecture** — separate UI port (default 8443) and agent port (default 8050), both SSL-capable
- **SSL by default** — 3-year self-signed certificate auto-generated during install
- **Encrypted secrets** — Telegram token and SMTP password encrypted at rest (Fernet/AES-128-CBC, keyed from PATCHPILOT_ADMIN_KEY via PBKDF2)
- **Session-based auth** — username/password login with 3 roles (admin, user, readonly)
- **Legacy auth** — PATCHPILOT_ADMIN_KEY env var as fallback
- **Pull-based agents** — zero-dependency Python agents poll the server every 10s, heartbeat every 60s
- **Dashboard** — real-time VM status, connection protocol (HTTP/TLS), OS distro icons (font-logos), row hover highlight, sortable columns
- **Patch management** — apt-get upgrade, autoremove, reboot scheduling per VM
- **Job system** — create, cancel individual jobs, bulk-cancel all pending jobs per agent
- **Schedules** — cron-based patch schedules with multi-VM targeting and presets
- **SSL deployment** — generate cert → deploy to agents → enable HTTPS (3-step flow with progress modal)
- **Notifications** — Telegram + Email with per-channel event toggles (offline, updates, job failed, job completed)
- **Agent self-update** — push new agent code to all VMs from Settings page
- **Deploy page** — one-liner and full install script with rotating registration key (5 min TTL)
- **Settings** — split into Notifications and Server tabs
- **User management** — create/edit/delete users with role assignment
- **Prometheus metrics** — /metrics endpoint for monitoring
- **Sci-fi UI** — Arwes-themed React frontend, fully responsive (mobile bottom tab bar)

### Security
- PBKDF2-SHA256 password hashing (100k iterations)
- SHA-256 hashed agent tokens and register keys in DB
- Fernet encryption for sensitive settings (Telegram token, SMTP password)
- Timing-safe token comparison (hmac.compare_digest)
- Rate limiting (20 req/min per IP, 5000 IP cap)
- TLS 1.2 minimum enforcement on agent connections
- Input validation (parameterized SQL, regex allowlists, field length limits)
- SSRF protection (SMTP hostname checked against private IP ranges)
- systemd hardening (NoNewPrivileges, PrivateTmp, ProtectHome, MemoryMax, CPUQuota)

---

## Release Process

1. Update version in:
   - `frontend/src/components/Layout.tsx` (sidebar display)
   - `frontend/package.json`
2. Add changelog entry above under `[X.Y.Z] - YYYY-MM-DD`
3. Build frontend: `cd frontend && npm run build`
4. Commit: `git commit -am "Bump version to vX.Y.Z"`
5. Tag: `git tag -a vX.Y.Z -m "PatchPilot vX.Y.Z"`
6. Push: `git push && git push origin vX.Y.Z`
7. Create release: `gh release create vX.Y.Z --title "PatchPilot vX.Y.Z" --notes-file -` (paste release notes)
8. Deploy: `PATCHPILOT_HOST=root@<server> bash deploy.sh`

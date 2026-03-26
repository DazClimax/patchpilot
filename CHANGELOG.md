# Changelog

All notable changes to PatchPilot are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.5.0] - 2026-03-27

### Added
- RPM groundwork for Linux fleet support, including `dnf`/`yum` detection in the agent
- Dashboard and VM detail now show the detected package manager (`apt`, `dnf`, `yum`)
- Config review warnings for package-managed config file conflicts, including acknowledge flow in the VM detail page
- UI sound effects with local bundled Arwes assets and settings controls
- Configurable login animation under `Settings > Effects`
- GitHub contribution templates and improved repository onboarding docs
- README screenshots moved into the top preview area for a stronger GitHub first impression

### Changed
- Version bumped to `1.5.0`
- Settings `Effects` panel renamed to `Sound Effects`
- Deploy/bootstrap flow hardened around authenticated UI-generated installers
- Login animation timing and presentation refined for the current sci-fi fullscreen transition
- README and install docs now describe Linux/RPM support more clearly instead of only Debian/Ubuntu
- Sidebar product copy already reflects Linux-wide positioning instead of Debian-only wording

### Fixed
- Agent token hashes are no longer exposed in dashboard/detail API responses
- Fedora/RPM reboot detection is more robust and less noisy, especially for container-like environments
- Users page now surfaces failure states instead of silently rendering an empty view
- Offline VM visuals are clearer with red status text/pulse and dimmed TLS badge styling

### Security
- Refreshed `SECURITY.md` to reflect the current hardened bootstrap, agent auth, SMTP delivery checks, and latest review outcome

## [1.0.3] - 2026-03-25

### Added
- One-liner server installation: `curl -fsSL .../setup.sh | sudo bash`
- `setup.sh` — automated installer (deps, Node.js 20, clone, build, install)
- README: one-liner + manual install instructions

### Changed
- `deploy.sh` installs pip requirements before restart
- `install-server.sh` generates PATCHPILOT_ADMIN_KEY if missing

## [1.0.2] - 2026-03-25

### Changed
- Dashboard: "Update All Agents" replaced with "Patch All VMs" — only targets VMs with pending updates
- Dashboard: Patch All button highlighted (primary variant) when updates available
- Dashboard: Updates column shows spinning indicator when a patch job is pending/running
- Dashboard: last_job API now includes pending/running jobs (not just completed)

### Fixed
- Double spinner on job history "Running" status (removed redundant ⟳ character)

## [1.0.1] - 2026-03-25

### Changed
- Deploy page: oneliner and full script visible immediately with `<KEY>` placeholder (no double-generate needed)
- Deploy page: active but hidden register key shows expiry countdown instead of hash

### Fixed
- Register key SHA-256 hash was leaked to UI on page reload (GET /api/register-key now returns `key: null`)

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

# Changelog

All notable changes to PatchPilot are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.7.2] - 2026-04-13

### Changed
- Fresh installations now start with e-mail, Telegram, and notification event toggles disabled by default. SSL remains enabled by default for the server and agent path.
- Version references in the installer, Docker examples, README, and wiki now point consistently at `v1.7.2`.

### Fixed
- Saving settings no longer crashes when the scheduler timezone was left unchanged. This restores reliable saving for toggles such as disabling Telegram from the GUI.

## [1.7.1] - 2026-04-12

### Added
- Disk usage monitoring: agents now report root filesystem usage (`disk_total`, `disk_used`, `disk_free`) in every heartbeat. The dashboard shows a compact colour-coded progress bar per host (green → yellow at 75 % → red at 90 %). The VM detail page shows a full disk card with used / total / free values. Hosts above 90 % usage appear in the alerts API.
- `fmtBytes` utility added to the frontend format helpers.

### Changed
- Agent version bumped `1.3 → 1.4` to carry the new disk usage payload.
- Uptime column removed from the dashboard overview table (still visible on the VM detail page).
- `AmbientCapabilities=CAP_NET_RAW` and `CapabilityBoundingSet=CAP_NET_RAW` restored in `patchpilot.service` so ping-only monitors work correctly on a clean install without requiring manual `setcap` on the system `ping` binary.

### Fixed
- Ping-only monitors went offline after a fresh deployment because `AmbientCapabilities=CAP_NET_RAW` had been removed from the service file. The capability is now part of the versioned service definition.

## [1.7.0] - 2026-04-12

### Added
- Ping-only targets can now be added from the dashboard to monitor systems such as routers or appliances that PatchPilot cannot manage directly.
- Mobile push notifications now have a dedicated admin-controlled settings panel with relay URL, enable/disable toggle, and test delivery action.
- Home Assistant `update.*` entity updates, including HACS/frontend-style updates, are now fully surfaced as targeted update actions.

### Changed
- Version bumped to `1.7.0`
- Docker, compose, setup, and install documentation now point consistently at the `v1.7.0` release.
- Frontend fonts are now bundled locally instead of loading from Google Fonts at runtime.
- Ping-only monitoring now follows a retry-based reachability model instead of a fixed offline window.
- The secure SSL rollout flow is now documented more clearly around **Deploy Trust to Agents**, signed CA rollover, and HAOS recovery.

### Fixed
- Ping-only targets are now excluded consistently from schedules, bulk patch actions, reboot actions, and other managed-job flows.
- Dashboard, detail view, alerts, badges, and offline notifications now agree on ping-target connectivity state.
- Manual ping checks on the VM detail page now provide direct user feedback through toasts.
- Mobile push activation no longer provisions secrets implicitly through normal settings reads and remains admin-only.
- Home Assistant update feedback and HA add-on rollout behavior are more consistent across dashboard, detail, and deployment flows.

## [1.6.5] - 2026-04-02

### Added
- Home Assistant detail views can now trigger individual `update.*` entities such as `Power Flow Card Plus` instead of falling back to unsupported generic patch jobs
- Home Assistant package records now persist `source_kind` and `source_id` metadata so targeted HA entity updates can be mapped safely

### Changed
- Version bumped to `1.6.5`
- Docker, compose, installer, and release references now point consistently at the `v1.6.5` release
- HA OS updates now always create a backup before the OS update is started
- Dashboard and VM detail screens show running jobs more consistently instead of only highlighting package patch jobs

### Fixed
- Pending update counts now come from the live `packages` table instead of stale cached agent counters
- Home Assistant update jobs that already completed on the HA side no longer stay stuck as `running` in PatchPilot after the next heartbeat
- Home Assistant agent/add-on update feedback is more accurate across dashboard and detail flows
- VM detail pages no longer leak numeric `0` values into the UI when boolean-like backend flags are unset

## [1.6.3] - 2026-03-29

### Added
- Agent fleet visibility now includes a server-provided target version plus clearer `Agent Current` status on the dashboard
- Runtime file logging is now first-class for both bare metal and Docker installs, including shipped `patchpilot.logrotate`

### Changed
- Version bumped to `1.6.3`
- Docker, setup, and install docs now point consistently at the new `v1.6.3` release paths
- `Patch All` and `Update Agents` now target only the correct online systems instead of sweeping in unrelated or unsupported hosts
- Dashboard stat cards and confirmation dialogs were polished for more consistent visual feedback

### Fixed
- Initial bootstrap credentials are no longer written to journal or container logs; they are exposed through a restricted bootstrap file instead
- The bootstrap password file is now removed automatically after the first successful login on both bare-metal and Docker installs
- Docker startup now avoids the earlier SSL permission race and first-boot SQLite lock race
- Bare-metal and Docker installs both persist runtime logs in the documented locations and rotate host logs for seven days
- Deploy host validation is stricter, reducing the risk of malformed `PATCHPILOT_HOST` values being interpreted as command options

## [1.6.2] - 2026-03-29

### Added
- Docker packaging for the PatchPilot server, including `Dockerfile`, `docker-compose.yml`, persistent `/data` storage, and GHCR publishing workflow support

### Changed
- Version bumped to `1.6.2`
- Docker docs now explain more clearly how the initial admin password is generated on first startup and how to set fixed container credentials

### Fixed
- Docker runtime now drops privileges to the dedicated `patchpilot` user after preparing the mounted data directory
- Docker build context now excludes common local secret material such as `.env` files, certificates, and private keys
- Sample compose configuration now enables `no-new-privileges` by default
- Container server startup now runs reliably from the correct working directory

## [1.6.1] - 2026-03-29

### Changed
- Version bumped to `1.6.1`
- Server bootstrap docs now use versioned installer URLs consistently instead of `main`
- README and install docs now explain more clearly that RPM/Fedora support currently applies to managed clients and agents, while the PatchPilot server installer still targets Debian/Ubuntu-style hosts

### Fixed
- `setup.sh` now clones the configured release ref instead of always pulling the moving `main` branch
- `setup.sh` and `install-server.sh` now fail early when run without root or on unsupported non-`apt` systems
- Both server installers now write structured logs and print clearer step-by-step status output for easier debugging

## [1.6.0] - 2026-03-28

### Added
- Home Assistant OS support as a dedicated add-on, including `HA Backup`, `HA Core`, `HA Supervisor`, `HA OS`, and add-on update workflows
- Home Assistant add-on onboarding on the Deploy page with repository URL, generated config, decoded CA PEM, and LAN IP override support
- Home Assistant add-on changelog, branding assets, and sidebar/dashboard visual polish around the latest artwork

### Changed
- Version bumped to `1.6.0`
- About page, README, favicon, Telegram avatar, and HA add-on branding now use the current PatchPilot artwork
- Dashboard/VM detail UI now treats Home Assistant OS as its own management surface rather than a generic Linux VM
- Home Assistant docs now describe the add-on as the supported path instead of an early preview

### Fixed
- Pending jobs now expire after 30 minutes instead of lingering forever; running jobs still time out after 15 minutes
- Job timestamps are written explicitly in local time even on older SQLite schemas that still default `created` to UTC
- HA add-on update visibility no longer disappears; PatchPilot’s own HA add-on stays visible as pending but is excluded from unsafe self-update flows
- HAOS uptime reporting is more robust across different `boot_timestamp` formats
- HAOS IP detection now handles primary interfaces, nested Supervisor network fields, address lists, and filters Docker/bridge-style virtual interfaces

### Security
- Queue cleanup is stricter, reducing the risk of stale pending jobs being mistaken for live operations

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

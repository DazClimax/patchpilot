# PatchPilot

Self-hosted patch management for Debian/Ubuntu VMs with a sci-fi themed UI.

PatchPilot uses a pull-based agent model — lightweight agents on each VM poll the server for jobs. No SSH required. The server runs on any Linux host (Raspberry Pi, Proxmox VM, etc.) and manages patching, reboots, and agent updates across your fleet.

## Features

- **Dashboard** — real-time overview of all VMs with online status, pending updates, reboot indicators
- **Patch Management** — trigger `apt-get upgrade` on individual VMs or all at once
- **Scheduled Jobs** — cron-based schedules for automated patching and reboots
- **Agent Self-Update** — push new agent versions from the server with SHA-256 verification
- **Notifications** — Telegram and SMTP email alerts for offline VMs, patch completions, and failures
- **User Management** — role-based access with admin, user, and read-only roles
- **Arwes UI** — sci-fi themed responsive interface, works on desktop and mobile
- **Zero-Dependency Agent** — Python 3 stdlib only, installs with a one-liner

## Screenshots

*Coming soon*

## Quick Start

### Server

```bash
# Install dependencies
cd server
pip install -r requirements.txt

# Start the server
uvicorn app:app --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run build   # Production build → frontend/dist/
```

### Agent (on each VM)

```bash
curl -fsSL http://<SERVER_IP>:8000/agent/install.sh | \
  sudo PATCHPILOT_SERVER=http://<SERVER_IP>:8000 \
  PATCHPILOT_REGISTER_KEY=<KEY> bash
```

Generate the registration key from the Deploy page in the web UI.

## Architecture

```
Server (any Linux host)               Agents (Debian/Ubuntu VMs)
├── FastAPI + SQLite                   agent.py (stdlib Python)
├── APScheduler (cron jobs)            ├── polls for jobs every 10s
├── React + Arwes (frontend)           ├── heartbeat every 60s
├── Telegram / SMTP notifications      └── self-update capable
└── Prometheus metrics
```

**Pull model:** Agents initiate all connections. The server never SSHes into VMs.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Server | Python 3.10+, FastAPI, SQLite (WAL), APScheduler, uvicorn |
| Frontend | React 18, TypeScript, Vite, Arwes |
| Agent | Python 3 stdlib only (zero pip dependencies) |
| Notifications | Telegram Bot API, SMTP |
| Deployment | rsync + systemd |

## Security

- **User auth:** Username + password (PBKDF2-SHA256) with session tokens
- **Agent auth:** 32-byte hex tokens, SHA-256 hashed in DB
- **Registration:** Rotating keys with 5-minute TTL
- **Roles:** Admin (full access), User (view + trigger jobs), Read-only (view only)
- **Service hardening:** Dedicated system user, `NoNewPrivileges`, `PrivateTmp`
- **SSRF protection:** SMTP hosts validated against private IP ranges

## Configuration

All configuration is via environment variables in `/opt/patchpilot/.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `PORT` | No | Server port (default: 8000) |
| `PATCHPILOT_ADMIN_KEY` | No | Legacy admin key for API access |
| `PATCHPILOT_ADMIN_PASSWORD` | No | Initial admin password (auto-generated if not set) |
| `PATCHPILOT_ALLOWED_ORIGINS` | No | CORS origins (comma-separated) |
| `PATCHPILOT_TRUSTED_PROXY` | No | Trusted reverse proxy IP for X-Forwarded-For |

## Documentation

- [Installation Guide](docs/INSTALL.md)
- [Agent Documentation](docs/AGENT.md)
- [API Reference](docs/API.md)

## License

This project is licensed under the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.html).

## Author

**DazClimax** — [github.com/DazClimax](https://github.com/DazClimax)

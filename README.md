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

### Server (automated)

```bash
# Clone and install (on Debian/Ubuntu host)
git clone https://github.com/DazClimax/patchpilot.git
cd patchpilot
cd frontend && npm install && npm run build && cd ..
sudo bash install-server.sh
```

This installs dependencies, creates a system user, sets up the systemd service (enabled for boot), and starts PatchPilot.

### Server (manual)

```bash
cd server
pip install -r requirements.txt
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
| `SSL_CERTFILE` | No | Path to SSL certificate (enables HTTPS) |
| `SSL_KEYFILE` | No | Path to SSL private key |

### SSL / HTTPS

SSL can be configured entirely from the Settings page in the web UI:

1. **Generate Certificate** — creates a self-signed cert (1/3/5/10 year validity)
2. **Deploy to Agents** — pushes the CA cert to all agents via the job system (agents are updated first automatically)
3. **Enable HTTPS** — activates SSL and restarts the server; agents migrate automatically via `canonical_url`

Alternatively, configure manually in `/opt/patchpilot/.env`:

```bash
SSL_CERTFILE=/opt/patchpilot/ssl/cert.pem
SSL_KEYFILE=/opt/patchpilot/ssl/key.pem
```

For self-signed certificates, agents need the CA bundle. The "Deploy to Agents" button handles this automatically, or set `PATCHPILOT_CA_BUNDLE` on the agent manually.

## Documentation

- [Installation Guide](docs/INSTALL.md)
- [Agent Documentation](docs/AGENT.md)
- [API Reference](docs/API.md)

## License

This project is licensed under the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.html).

## Author

**DazClimax**

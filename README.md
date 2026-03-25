# PatchPilot

Self-hosted patch management for Debian/Ubuntu VMs with a sci-fi themed UI.

Pull-based agent model — lightweight agents on each VM poll the server for jobs. No SSH required. The server runs on any Linux host and manages patching, reboots, and agent updates across your fleet.

## Features

- **Dashboard** — real-time VM overview with online status, pending updates, reboot indicators, and connection type (HTTP/TLS)
- **Patch Management** — trigger `apt-get upgrade` on individual VMs or all at once
- **Scheduled Jobs** — cron-based schedules for automated patching and reboots
- **Agent Self-Update** — push new agent versions with SHA-256 verification
- **Notifications** — Telegram and SMTP email with per-channel event configuration (offline, patch complete, failure, etc.)
- **User Management** — session-based auth with 3 roles: admin, user, read-only
- **Settings** — split into Notifications and Server tabs for SSL, ports, timezone, and more
- **Arwes UI** — sci-fi themed responsive interface with font-logos distro icons, works on desktop and mobile
- **Zero-Dependency Agent** — Python 3 stdlib only, installs with a one-liner

## Quick Start

### Server (One-liner)

```bash
curl -fsSL https://raw.githubusercontent.com/DazClimax/patchpilot/main/setup.sh | sudo bash
```

Custom ports:
```bash
curl -fsSL https://raw.githubusercontent.com/DazClimax/patchpilot/main/setup.sh | sudo PORT=443 AGENT_PORT=8050 bash
```

This installs all dependencies (git, Node.js 20, Python 3, OpenSSL), builds the frontend, generates a 3-year self-signed SSL certificate, and starts PatchPilot on two ports: UI (default 8443) and Agent API (default 8050).

### Server (Manual)

```bash
apt-get install -y git curl python3 python3-venv openssl nodejs npm
git clone https://github.com/DazClimax/patchpilot.git
cd patchpilot
cd frontend && npm install && npm run build && cd ..
sudo bash install-server.sh
```

### Agent (on each VM)

```bash
curl -fsSLk https://<SERVER_IP>:8050/agent/install.sh | \
  sudo PATCHPILOT_SERVER=https://<SERVER_IP>:8050 \
  PATCHPILOT_REGISTER_KEY=<KEY> bash
```

Generate the registration key from the Deploy page in the web UI. The `-k` flag is needed for the initial download when using self-signed certificates.

## Architecture

```
Server (any Linux host)               Agents (Debian/Ubuntu VMs)
├── FastAPI (dual-port)                agent.py (stdlib Python)
│   ├── UI port (HTTPS)                ├── polls for jobs every 10s
│   └── Agent port (HTTPS)             ├── heartbeat every 60s
├── SQLite (WAL mode)                  └── self-update capable
├── APScheduler (cron jobs)
├── React + Arwes (frontend)
├── Telegram / SMTP notifications
└── Prometheus metrics (/metrics)
```

**Dual-port model:** The UI and agent API run on separate ports, each independently SSL-capable. Agents initiate all connections — the server never SSHes into VMs.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Server | Python 3.10+, FastAPI, SQLite (WAL), APScheduler, uvicorn |
| Frontend | React 18, TypeScript, Vite, Arwes, font-logos |
| Agent | Python 3 stdlib only (zero pip dependencies) |
| Notifications | Telegram Bot API, SMTP |
| Deployment | rsync + systemd |

## Security

- **Encryption:** Fernet encryption for secrets stored in the database (SMTP passwords, Telegram tokens), keyed from PATCHPILOT_ADMIN_KEY via PBKDF2
- **User auth:** Session-based with PBKDF2-SHA256 password hashing, 3 roles (admin / user / read-only)
- **Agent auth:** 32-byte hex tokens, SHA-256 hashed in DB
- **Registration:** Rotating 12-char register keys with 5-minute TTL
- **SSL:** Auto-generated 3-year self-signed certificate during install; replaceable via Settings UI
- **Service hardening:** Dedicated system user, `NoNewPrivileges`, `PrivateTmp`
- **SSRF protection:** SMTP hosts validated against private IP ranges

## Configuration

All configuration is in `/opt/patchpilot/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 8443 | UI port (HTTPS) |
| `AGENT_PORT` | 8050 | Agent API port (HTTPS) |
| `AGENT_SSL` | 1 | Enable SSL on agent port (`1` = on) |
| `SSL_CERTFILE` | (auto) | Path to SSL certificate |
| `SSL_KEYFILE` | (auto) | Path to SSL private key |
| `PATCHPILOT_ADMIN_KEY` | (auto) | Secret key for API auth and Fernet encryption |
| `PATCHPILOT_ADMIN_PASSWORD` | (auto) | Initial admin password |
| `PATCHPILOT_ALLOWED_ORIGINS` | localhost | CORS origins (comma-separated) |
| `PATCHPILOT_TRUSTED_PROXY` | | Trusted reverse proxy IP for X-Forwarded-For |

### SSL / HTTPS

SSL is enabled by default with a self-signed certificate generated during install. From the Settings UI you can:

1. **Generate Certificate** — create a new self-signed cert (1/3/5/10 year validity)
2. **Deploy to Agents** — push the CA cert to all agents via the job system
3. **Enable/Disable HTTPS** — toggle SSL per port; agents migrate automatically via `canonical_url`

## Documentation

- [Installation Guide](docs/INSTALL.md)
- [Agent Documentation](docs/AGENT.md)
- [API Reference](docs/API.md)

## License

This project is licensed under the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.html).

## Author

**DazClimax**

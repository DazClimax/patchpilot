# PatchPilot — Installation Guide

## Contents

1. [Prerequisites](#prerequisites)
2. [Server Installation](#server-installation)
3. [Agent Installation](#agent-installation)
4. [Configuration](#configuration)
5. [Managing the Service](#managing-the-service)
6. [Upgrading](#upgrading)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Server (Raspberry Pi or any Linux host)

- Raspberry Pi OS (Bullseye/Bookworm) **or** Debian 11/12 **or** Ubuntu 22.04/24.04
- Python 3.10 or newer
- Network access from managed Linux VMs to the server
- `sudo` privileges

PatchPilot server installation currently targets Debian/Ubuntu-style hosts and uses `apt` during bootstrap. Fedora/RPM support currently applies to managed client systems and agents, not to the PatchPilot server installer itself.

**Optional** (for frontend build on dev machine):
- Node.js 18+ and npm

### Agent (Managed VM)

- Debian 11+, Ubuntu 22.04+, or Fedora with `dnf`
- Python 3 (stdlib only, no pip needed)
- `root` privileges (agent calls the system package manager)
- HTTPS (or HTTP) connection to the PatchPilot server agent port

---

## Server Installation

### Quick Install

Versioned one-liner:

```bash
curl -fsSL https://raw.githubusercontent.com/DazClimax/patchpilot/v1.6.0/setup.sh | sudo bash
```

Inspect before running:

```bash
curl -fsSL https://raw.githubusercontent.com/DazClimax/patchpilot/v1.6.0/setup.sh -o setup.sh
less setup.sh
sudo bash setup.sh
```

With custom ports:

```bash
curl -fsSL https://raw.githubusercontent.com/DazClimax/patchpilot/v1.6.0/setup.sh | sudo PORT=9443 AGENT_PORT=9050 bash
```

The bootstrap script will:

1. Install required system packages with `apt`
2. Install Node.js 20 if it is missing or too old
3. Clone the PatchPilot release to a temporary directory
4. Build the frontend
5. Run `install-server.sh`

### Step 1: Get the Code

```bash
git clone https://github.com/DazClimax/patchpilot.git
cd patchpilot
```

### Step 2: Build the Frontend (optional)

On your dev machine (requires Node.js 18+):

```bash
cd frontend && npm install && npm run build && cd ..
```

This creates `frontend/dist/`. The install script copies it automatically. Without it, the server runs API-only.

### Step 3: Run the Install Script

```bash
sudo bash install-server.sh
```

With custom ports:

```bash
sudo PORT=9443 AGENT_PORT=9050 bash install-server.sh
```

The script:
1. Installs `python3`, `python3-pip`, `python3-venv`, `openssl` via apt
2. Creates the system user `patchpilot` (no login shell)
3. Copies server, agent, and frontend files to `/opt/patchpilot/`
4. Creates a Python venv at `/opt/patchpilot-venv/` and installs dependencies (including `cryptography` for Fernet encryption of sensitive settings)
5. Generates a self-signed SSL certificate (RSA 2048-bit, 3-year validity) at `/opt/patchpilot/ssl/` if none exists
6. Creates `/opt/patchpilot/.env` with dual-port configuration and SSL enabled (preserves existing config on re-install)
7. Installs, **enables** (`systemctl enable` — survives reboot), and starts the systemd service `patchpilot`
8. Sets up sudoers entry for service self-restart (needed for port/SSL changes from the Settings UI)

### Step 4: Retrieve the Initial Admin Credentials

On first start, PatchPilot creates a default `admin` user automatically.

- If `PATCHPILOT_ADMIN_PASSWORD` is already set in the environment before installation, that value becomes the initial password.
- Otherwise, PatchPilot generates a password and writes it to the service logs.

To retrieve the generated password:

```bash
journalctl -u patchpilot | grep "Default admin user created"
```

PatchPilot also uses `PATCHPILOT_ADMIN_KEY` for legacy admin-key authentication and to derive the Fernet encryption key for sensitive settings.

For production, set a fixed admin key:

```bash
# Generate a key
openssl rand -hex 32

# Add to .env
echo "PATCHPILOT_ADMIN_KEY=your-key-here" >> /opt/patchpilot/.env
sudo systemctl restart patchpilot
```

Changing the admin key after secrets have already been stored will require re-entering those encrypted values.

### Step 5: Open the Web UI and Sign In

```
https://<server-ip>:8443
```

The default UI port is 8443 (HTTPS). Your browser will warn about the self-signed certificate on first access. Sign in with `admin` and the password from the previous step.

---

## Agent Installation

### Option A: One-Liner (Recommended)

1. Sign in to the PatchPilot UI as an admin
2. Open the **Deploy** page
3. Set the correct server URL (internal IP + agent port)
4. Click **Generate Key** — a registration key valid for 5 minutes appears
5. Copy the generated secure installer command and run it on the target VM:

```bash
printf '%s' '<DEPLOY_PAGE_BASE64_INSTALLER>' | base64 -d | sudo bash
```

The Deploy page installer is generated inside the authenticated UI session. For HTTPS deployments it embeds the server CA certificate, so the agent can verify downloads immediately without using an insecure `curl -k | bash` bootstrap. The installer supports `apt`, `dnf`, and limited legacy `yum` environments.

### Option B: Manual Installation

```bash
# Copy the installer generated by the Deploy page to the VM
scp install-patchpilot-agent.sh user@vm:~/

# Run installer
sudo bash install-patchpilot-agent.sh
```

### Verify Registration

```bash
journalctl -u patchpilot-agent -f
# Expected: [agent] Registered as <hostname>
```

The VM should appear on the dashboard within 30 seconds.

---

## Configuration

### Agent Config: `/etc/patchpilot/agent.conf`

```ini
PATCHPILOT_SERVER=https://192.168.1.10:8050
PATCHPILOT_INTERVAL=60
# PATCHPILOT_AGENT_ID=my-vm  (set automatically)
# PATCHPILOT_CA_BUNDLE=/etc/patchpilot/ca.pem  (set by deploy_ssl job)
```

### Agent State: `/etc/patchpilot/state.json`

Stores `agent_id`, `token`, and `server` URL. Permissions: `chmod 600`. Do not delete — the agent would need to re-register.

### Server Environment: `/opt/patchpilot/.env`

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8443` | UI port (HTTPS) |
| `AGENT_PORT` | `8050` | Agent API port (HTTPS) |
| `AGENT_SSL` | `1` | Enable SSL on agent port (`1` = on) |
| `SSL_CERTFILE` | (auto) | Path to SSL certificate |
| `SSL_KEYFILE` | (auto) | Path to SSL private key |
| `PATCHPILOT_ADMIN_KEY` | (auto) | Admin key for legacy auth and Fernet encryption |
| `PATCHPILOT_ALLOWED_ORIGINS` | `http://localhost:5173,http://localhost:8000` | CORS origins |

### SSL / HTTPS

SSL is enabled by default with a self-signed certificate generated during installation. Both the UI port and agent port can independently have SSL enabled.

From the **Settings** page in the web UI you can:

1. **Generate Certificate** — creates a self-signed cert (1-10 year validity) under `/opt/patchpilot/ssl/`
2. **Deploy to Agents** — pushes the CA cert to all agents via the job system (agents are auto-updated first)
3. **Enable/Disable HTTPS** — activates or deactivates SSL; agents migrate automatically via `canonical_url`

No SSH access to VMs required. The agent stores the CA bundle at `/etc/patchpilot/ca.pem` and trusts HTTPS connections automatically. The agent enforces TLS 1.2 as the minimum protocol version.

### Dual-Port Architecture

The server runs two uvicorn processes on separate ports:

- **UI port** (default 8443): Serves the web dashboard, settings, auth, static files
- **Agent port** (default 8050): Serves agent registration, heartbeat, jobs, file downloads

Endpoint routing is enforced by middleware — agent-only endpoints return 404 on the UI port and vice versa. If both ports are configured to the same value, the server runs a single process in backward-compatible single-port mode.

---

## Managing the Service

### Server

```bash
sudo systemctl status patchpilot
sudo journalctl -u patchpilot -f          # Live logs
sudo systemctl restart patchpilot
sudo systemctl stop patchpilot
```

The service is enabled by default (`systemctl enable`), so it starts automatically on boot.

### Agent (on each VM)

```bash
sudo systemctl status patchpilot-agent
sudo journalctl -u patchpilot-agent -f
sudo systemctl restart patchpilot-agent
```

---

## Upgrading

### Server

```bash
cd patchpilot && git pull
cd frontend && npm install && npm run build && cd ..
bash deploy.sh
```

`deploy.sh` rsyncs files to the server and restarts the service. The database is never touched.

### Agents

Use the **Update All Agents** button on the dashboard, or trigger `update_agent` jobs via schedules. Agents download the latest code, verify SHA-256, and restart automatically.

### Notes On Platform Scope

- PatchPilot server installation is currently documented and supported on Debian/Ubuntu-style hosts
- Managed clients can already be Debian/Ubuntu or Fedora/RPM systems, depending on the current agent capabilities
- Home Assistant OS is handled through the dedicated add-on, not through the regular Linux agent path

---

## Troubleshooting

### Server won't start

```bash
journalctl -u patchpilot -n 50 --no-pager
```

Common causes:
- Port already in use: `sudo ss -tlnp | grep <port>`
- Missing dependencies: `sudo /opt/patchpilot-venv/bin/pip install -r /opt/patchpilot/server/requirements.txt`
- Permission issue: `sudo chown -R patchpilot:patchpilot /opt/patchpilot/`
- SSL cert missing: Check that `/opt/patchpilot/ssl/cert.pem` and `key.pem` exist

### Agent not appearing on dashboard

```bash
journalctl -u patchpilot-agent -n 30 --no-pager
```

Common causes:
- Wrong server URL in `/etc/patchpilot/agent.conf` (should point to the agent port, e.g., `https://192.168.1.10:8050`)
- Registration key expired — generate a new one from the Deploy page
- Firewall blocking the connection: `curl -k https://<server-ip>:<agent-port>/api/ping`
- SSL certificate not trusted: Check `/etc/patchpilot/ca.pem` exists and `PATCHPILOT_CA_BUNDLE` is set in `agent.conf`

### Agent re-registering with new ID on every restart

`/etc/patchpilot/state.json` was deleted or has wrong permissions:

```bash
ls -la /etc/patchpilot/state.json
# Must exist and be owned by root (600)
```

### "Authentication required" in browser

Log in with your username and password. If you have not created a user account yet, use the legacy admin key:

```bash
# Get current key from log
journalctl -u patchpilot | grep "ephemeral key"

# Or set a permanent key
echo "PATCHPILOT_ADMIN_KEY=$(openssl rand -hex 32)" >> /opt/patchpilot/.env
sudo systemctl restart patchpilot
```

### apt-get fails with permission denied

The agent service must run as `root`:

```bash
systemctl cat patchpilot-agent | grep User
# Should show User=root or no User line
```

### Config file conflict during patching

PatchPilot uses `--force-confdef --force-confold`:
- Unmodified config files are updated to the new version
- Manually modified config files are kept as-is

When a config file is kept, the job output includes a warning and a Telegram notification is sent (if configured). Check the job log for details on which config file was affected.

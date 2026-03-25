# PatchPilot Agent — Technical Documentation

## How the Agent Works

The PatchPilot agent uses a **pull model**: the agent always initiates connections to the server — the server never connects to the VMs.

### Why Pull Model?

- No inbound connections needed on the VMs
- Firewalls only need to allow outbound HTTPS (or HTTP) traffic
- The server needs no SSH credentials for VMs
- Agents behind NAT work without port forwarding

### Main Loop

```
Startup
  │
  ▼
Register with server
(POST /api/agents/register + x-register-key header)
  │
  ▼
Store agent_id + token in /etc/patchpilot/state.json
  │
  ▼
┌─────────────────────────────────────────────┐
│ Every 60s (PATCHPILOT_INTERVAL):            │
│   apt-get update -qq                        │
│   apt-get --just-print upgrade              │
│   → List of pending updates                 │
│   POST /heartbeat (system info + packages)  │
│   → Check canonical_url (URL migration)     │
│   → Check canonical_port (port migration)   │
│   → Check canonical_id (agent rename)       │
└───────────────────┬─────────────────────────┘
                    │
┌───────────────────▼─────────────────────────┐
│ Every 10s:                                  │
│   GET /api/agents/{id}/jobs                 │
│   For each pending job:                     │
│     → execute_job()                         │
│     → POST /jobs/{id}/result                │
│   After patch job: immediate heartbeat      │
└─────────────────────────────────────────────┘
```

### Job Types

| Type | What it does |
|------|-------------|
| `patch` | `DEBIAN_FRONTEND=noninteractive apt-get upgrade -y --force-confdef --force-confold` + auto `apt-get autoremove` + config conflict detection |
| `autoremove` | `apt-get autoremove -y` |
| `reboot` | `shutdown -r +1 "PatchPilot scheduled reboot"` |
| `update_agent` | Downloads latest `agent.py` from server, verifies SHA-256 hash, atomically replaces the file, exits so systemd restarts with new code |
| `deploy_ssl` | Downloads CA certificate from server, verifies SHA-256, installs to `/etc/patchpilot/ca.pem`, updates `agent.conf` with `PATCHPILOT_CA_BUNDLE` path, and reloads the SSL context in-process |

### Registration

On startup, the agent loads state from `/etc/patchpilot/state.json`. If `agent_id` and `token` exist, it re-registers with the existing token. Otherwise, it requires a valid `PATCHPILOT_REGISTER_KEY` for first-time registration.

### URL Migration

When the server URL changes (port, protocol, or host), the heartbeat response includes `canonical_url`. The agent automatically switches to the new URL and persists it in `state.json`. A legacy `canonical_port` field is also supported for backward compatibility with older servers.

### Protocol Fallback

If an HTTP request fails, the agent automatically tries HTTPS (and vice versa). This handles the transition period when the server switches protocol (e.g., SSL enabled or disabled) and the agent has not migrated yet.

### Agent Rename

When an admin renames an agent via the UI, the heartbeat response includes `canonical_id`. The agent updates its ID in both `agent.conf` and `state.json`.

### Self-Update

When the agent receives an `update_agent` job:
1. Downloads `agent.py` and `agent.py.sha256` from the server
2. Verifies the SHA-256 hash matches
3. Writes to a temp file, then atomically replaces itself via `os.replace()`
4. Calls `os.fork()` + `sys.exit(0)` after 4 seconds, allowing the job result to be posted first
5. systemd's `Restart=always` relaunches with the new code

The server can also inline the agent code in the job payload (base64-encoded with SHA-256), which is used during the SSL bootstrap flow to update agents before they have the CA certificate.

If an SSL error occurs during the download (e.g., the server certificate has changed), the agent automatically calls `_bootstrap_ca_cert` to re-fetch the CA certificate before retrying.

---

## SSL / TLS Support

### TLS 1.2 Minimum

The agent enforces a minimum of TLS 1.2 for all HTTPS connections. This is set via `ssl.TLSVersion.TLSv1_2` in the SSL context. Older protocols (SSLv3, TLS 1.0, TLS 1.1) are rejected.

### CA Certificate Trust

For HTTPS deployments with self-signed certificates, the agent needs the server's CA certificate. This is managed automatically:

1. **Via `deploy_ssl` job:** The server pushes the CA cert to all agents through the job system. The agent downloads `ca.pem` and `ca.pem.sha256` from the server, verifies integrity, and installs to `/etc/patchpilot/ca.pem`.

2. **Via `_bootstrap_ca_cert`:** If the agent encounters an SSL error (e.g., after a certificate change), it automatically re-downloads the CA cert using an unverified TLS connection. Both the certificate and its SHA-256 hash are downloaded and compared. PEM format is validated before writing.

3. **Via environment variable:** Set `PATCHPILOT_CA_BUNDLE` in `agent.conf` or as an environment variable to point to a custom CA certificate file.

After installing a new CA cert, the agent reloads its global SSL context in-process without requiring a restart.

### HTTP Warning

When connecting over plain HTTP, the agent logs a warning that the agent token is sent unencrypted and recommends HTTPS for production deployments.

---

## Configuration

The agent reads config from two sources (later overrides earlier):

1. `/etc/patchpilot/agent.conf` (KEY=VALUE format, `#` comments)
2. Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PATCHPILOT_SERVER` | yes | — | Server URL, e.g. `https://192.168.1.10:8050` |
| `PATCHPILOT_INTERVAL` | no | `60` | Seconds between heartbeats (minimum 10) |
| `PATCHPILOT_AGENT_ID` | no | auto | Fixed agent ID |
| `PATCHPILOT_REGISTER_KEY` | first run | — | Registration key from Deploy page (5 min validity) |
| `PATCHPILOT_CA_BUNDLE` | no | — | Path to CA certificate for self-signed HTTPS (auto-set by `deploy_ssl` job) |

**File paths:**

| Path | Contents |
|------|----------|
| `/etc/patchpilot/agent.conf` | Configuration file |
| `/etc/patchpilot/state.json` | Persisted `agent_id`, `token`, `server` (chmod 600) |
| `/etc/patchpilot/ca.pem` | CA certificate for HTTPS trust (chmod 644) |
| `/opt/patchpilot/agent/agent.py` | Agent script |

---

## Security Model

### Token Security

- Tokens are generated **server-side only** (`secrets.token_hex(32)` = 64 hex chars)
- Client-supplied tokens in register requests are silently ignored
- Token stored in `state.json` with `chmod 600` — only root can read
- Server stores tokens as SHA-256 hashes in the database
- Server uses `hmac.compare_digest` for timing-safe comparison
- Dummy comparison performed for unknown agent IDs to prevent timing oracle

### Registration Key

- Generated on-demand from the Deploy page (not always active)
- 12-character hex key, SHA-256 hashed in the database, valid for 5 minutes
- Required for first-time agent registration
- Re-registration of existing IDs uses the agent token instead

### Package Name Validation

Package names received from the server are validated against the Debian package-name grammar (`^[a-zA-Z0-9][a-zA-Z0-9.+\-]{0,127}$`). Invalid names are rejected and logged. This prevents a compromised server from injecting shell metacharacters into `apt-get` invocations. Additionally, `subprocess` is called with a list (not `shell=True`), providing structural defense against shell injection.

### What the Agent Can Do

- Run `apt-get update`, `apt-get upgrade`, `apt-get autoremove`
- Run `shutdown -r +1`
- Update its own `agent.py` (verified by SHA-256)
- Install a CA certificate to `/etc/patchpilot/ca.pem`
- Read system info (hostname, IP, `/etc/os-release`, uptime, reboot status)

### What the Agent Cannot Do

- Execute arbitrary shell commands — only the hardcoded job types are processed
- Write files other than its own state, config, CA cert, and self-update
- Access other agents or the server's internal state

---

## Dual-Port Architecture

The server runs on two separate ports:

| Port | Default | Purpose |
|------|---------|---------|
| UI port | 8443 | Web dashboard, settings, auth, static files |
| Agent port | 8050 | Agent registration, heartbeat, jobs, file downloads |

The agent communicates exclusively with the **agent port**. Each port can independently have SSL enabled or disabled, controlled by the `AGENT_SSL` environment variable on the server. If both ports are set to the same value, the server runs in single-port mode.

The heartbeat response includes `canonical_url` which always points to the agent port with the correct protocol (HTTP or HTTPS). This allows agents to automatically migrate when the server's port or protocol changes.

---

## Manual Testing

### Start agent directly

```bash
sudo PATCHPILOT_SERVER=https://192.168.1.10:8050 \
     PATCHPILOT_REGISTER_KEY=abc123 \
     python3 /opt/patchpilot/agent/agent.py
```

### Check agent logs

```bash
journalctl -u patchpilot-agent -f
```

### Test registration

```bash
curl -sk -X POST https://192.168.1.10:8050/api/agents/register \
  -H "Content-Type: application/json" \
  -H "x-register-key: abc123" \
  -d '{"id": "test-vm", "hostname": "test"}'
```

Note: Use `-k` to skip certificate verification when using self-signed certificates.

# PatchPilot Agent — Technical Documentation

## How the Agent Works

The PatchPilot agent uses a **pull model**: the agent always initiates connections to the server — the server never connects to the VMs.

### Why Pull Model?

- No inbound connections needed on the VMs
- Firewalls only need to allow outbound HTTP traffic
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

### Registration

On startup, the agent loads state from `/etc/patchpilot/state.json`. If `agent_id` and `token` exist, it re-registers with the existing token. Otherwise, it requires a valid `PATCHPILOT_REGISTER_KEY` for first-time registration.

### Port Migration

When the server port changes, the heartbeat response includes `canonical_port`. The agent automatically switches to the new URL and persists it in `state.json`.

### Agent Rename

When an admin renames an agent via the UI, the heartbeat response includes `canonical_id`. The agent updates its ID in both `agent.conf` and `state.json`.

### Self-Update

When the agent receives an `update_agent` job:
1. Downloads `agent.py` and `agent.py.sha256` from the server
2. Verifies the SHA-256 hash matches
3. Writes to a temp file, then atomically replaces itself via `os.replace()`
4. Calls `os.fork()` + `sys.exit(0)` after 4 seconds, allowing the job result to be posted first
5. systemd's `Restart=always` relaunches with the new code

---

## Configuration

The agent reads config from two sources (later overrides earlier):

1. `/etc/patchpilot/agent.conf` (KEY=VALUE format, `#` comments)
2. Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PATCHPILOT_SERVER` | yes | — | Server URL, e.g. `http://192.168.1.10:8000` |
| `PATCHPILOT_INTERVAL` | no | `60` | Seconds between heartbeats |
| `PATCHPILOT_AGENT_ID` | no | auto | Fixed agent ID |
| `PATCHPILOT_REGISTER_KEY` | first run | — | Registration key from Deploy page (5 min validity) |

**File paths:**

| Path | Contents |
|------|----------|
| `/etc/patchpilot/agent.conf` | Configuration file |
| `/etc/patchpilot/state.json` | Persisted `agent_id`, `token`, `server` (chmod 600) |
| `/opt/patchpilot/agent/agent.py` | Agent script |

---

## Security Model

### Token Security

- Tokens are generated **server-side only** (`secrets.token_hex(32)` = 64 hex chars)
- Client-supplied tokens in register requests are silently ignored
- Token stored in `state.json` with `chmod 600` — only root can read
- Server uses `hmac.compare_digest` for timing-safe comparison
- Dummy comparison performed for unknown agent IDs to prevent timing oracle

### Registration Key

- Generated on-demand from the Deploy page (not always active)
- 12-character hex key, valid for 5 minutes
- Required for first-time agent registration
- Re-registration of existing IDs uses the agent token instead

### What the Agent Can Do

- Run `apt-get update`, `apt-get upgrade`, `apt-get autoremove`
- Run `shutdown -r +1`
- Update its own `agent.py` (verified by SHA-256)
- Read system info (hostname, IP, `/etc/os-release`, uptime, reboot status)

### What the Agent Cannot Do

- Execute arbitrary shell commands — only the four hardcoded job types are processed
- Write files other than its own state and self-update
- Access other agents or the server's internal state

---

## Manual Testing

### Start agent directly

```bash
sudo PATCHPILOT_SERVER=http://192.168.1.10:8000 \
     PATCHPILOT_REGISTER_KEY=abc123 \
     python3 /opt/patchpilot/agent/agent.py
```

### Check agent logs

```bash
journalctl -u patchpilot-agent -f
```

### Test registration

```bash
curl -s -X POST http://192.168.1.10:8000/api/agents/register \
  -H "Content-Type: application/json" \
  -H "x-register-key: abc123" \
  -d '{"id": "test-vm", "hostname": "test"}'
```

# PatchPilot REST API

Complete reference for all API endpoints.

## Base URL

The server runs on two ports (configurable via `.env`):

| Port | Default | Purpose |
|------|---------|---------|
| UI port (`PORT`) | 8443 | Web dashboard, settings, auth, static files |
| Agent port (`AGENT_PORT`) | 8050 | Agent registration, heartbeat, jobs, file downloads |

```
https://<server-host>:<UI-port>      # Web UI endpoints
https://<server-host>:<agent-port>   # Agent endpoints
```

If both ports are the same, all endpoints are served on a single port. Both ports can independently have SSL enabled or disabled.

Shared endpoints available on both ports: `/api/ping`, `/api/server-time`.

---

## Authentication

PatchPilot supports two authentication mechanisms for web UI endpoints.

### Session Auth (Primary)

Users log in with username + password via `POST /api/auth/login`, which returns a session token. All subsequent requests include:

```
Authorization: Bearer <session-token>
```

Sessions expire after 24 hours. Three roles control access: `admin`, `user`, `readonly`.

### Legacy Admin Key

For backward compatibility, the `x-admin-key` header is accepted on all web UI endpoints and treated as an `admin` session:

```
x-admin-key: <PATCHPILOT_ADMIN_KEY>
```

### Agent Token (Agent Endpoints)

Each agent receives a server-generated token (64 hex chars) at registration. All subsequent requests include:

```
x-token: <agent-token>
```

### Registration Key (New Agent Registration)

New agents must include a time-limited registration key:

```
x-register-key: <key>
```

Registration keys are generated on-demand from the Deploy page and expire after 5 minutes. The key is SHA-256 hashed in the database.

**Token Flow:**
```
1. Admin generates registration key via UI (Deploy page)
2. Agent  -> POST /api/agents/register  (Header: x-register-key)
3. Server -> { agent_id, token }
4. Agent stores token in /etc/patchpilot/state.json (chmod 600)
5. Agent  -> POST /api/agents/{id}/heartbeat  (Header: x-token)
6. Agent  -> GET  /api/agents/{id}/jobs       (Header: x-token)
7. Agent  -> POST /api/agents/{id}/jobs/{id}/result (Header: x-token)
```

Re-registration of an existing agent ID requires the current valid token (not the registration key).

---

## Auth Endpoints

### POST /api/auth/login

Authenticate with username and password. Returns a session token.

**Auth:** None (public)

**Request Body (JSON):**

| Field      | Type   | Required | Description |
|------------|--------|----------|-------------|
| `username` | string | yes      | Username |
| `password` | string | yes      | Password (max 1024 chars) |

**Response (200):**

```json
{
  "token": "a1b2c3d4e5f6...",
  "role": "admin",
  "username": "admin"
}
```

---

### POST /api/auth/logout

Invalidate the current session.

**Auth:** `Authorization: Bearer <token>`

**Response (200):**

```json
{ "status": "ok" }
```

---

### GET /api/auth/me

Return the current user's info.

**Auth:** Any role (admin, user, readonly)

**Response (200):**

```json
{ "username": "admin", "role": "admin" }
```

---

## Agent API

### POST /api/agents/register

Registers a new agent. Requires a valid registration key for new agents.

**Auth:** Header `x-register-key: <key>` (new agents) or `x-token: <token>` (re-registration of existing ID)

**Request Body (JSON):**

| Field       | Type   | Required | Description |
|-------------|--------|----------|-------------|
| `id`        | string | no       | Desired agent ID (validated: `^[a-zA-Z0-9._-]{1,64}$`); random if omitted |
| `hostname`  | string | no       | Hostname of the VM |
| `ip`        | string | no       | IP address |
| `os_pretty` | string | no       | From `/etc/os-release` PRETTY_NAME |
| `kernel`    | string | no       | Kernel version (`uname -r`) |
| `arch`      | string | no       | Architecture (`uname -m`) |

**Response (200):**

```json
{
  "agent_id": "my-vm",
  "token": "d4e5f6a7b8c9d0e1..."
}
```

---

### POST /api/agents/{agent_id}/heartbeat

Sends current system status. Called every 60 seconds by the agent.

**Auth:** Header `x-token: <token>`

**Request Body (JSON):**

| Field              | Type    | Description |
|--------------------|---------|-------------|
| `hostname`         | string  | Current hostname |
| `ip`               | string  | Current IP address |
| `os_pretty`        | string  | OS name |
| `kernel`           | string  | Kernel version |
| `arch`             | string  | Architecture |
| `uptime_seconds`   | int     | System uptime in seconds |
| `reboot_required`  | bool    | Whether `/var/run/reboot-required` exists |
| `packages`         | array   | List of pending updates (max 2000) |

**Response (200):**

```json
{
  "status": "ok",
  "canonical_url": "https://192.168.1.10:8050",
  "canonical_port": "8050",
  "canonical_id": "my-vm"
}
```

`canonical_url` signals a full URL migration (protocol + host + port). `canonical_port` is the legacy field for port-only migration. `canonical_id` signals an agent rename.

---

### GET /api/agents/{agent_id}/jobs

Returns all pending jobs. Jobs are marked `running` server-side when fetched.

**Auth:** Header `x-token: <token>`

**Response (200):**

```json
[
  {
    "id": 42,
    "type": "patch",
    "params": { "packages": ["libssl3"] }
  }
]
```

Job types include Linux actions such as `patch`, `dist_upgrade`, `refresh_updates`, `autoremove`, `reboot`, `update_agent`, and `deploy_ssl`, plus Home Assistant actions such as `ha_backup`, `ha_core_update`, `ha_backup_update`, `ha_supervisor_update`, `ha_os_update`, `ha_addon_update`, `ha_addons_update`, `ha_entity_update`, and `ha_trigger_agent_update`.

---

### POST /api/agents/{agent_id}/jobs/{job_id}/result

Reports job result.

**Auth:** Header `x-token: <token>`

**Request Body (JSON):**

| Field    | Type   | Description |
|----------|--------|-------------|
| `status` | string | `"done"` or `"failed"` |
| `output` | string | Combined stdout + stderr (max 65536 chars) |

---

## Agent File Downloads

These endpoints serve files needed by agents. Available on the **agent port** only.

### GET /agent/agent.py

Download the latest agent script.

### GET /agent/agent.py.sha256

Download the SHA-256 checksum for agent.py.

### GET /agent/install.sh

Download the agent installer script.

### GET /agent/ca.pem

Download the server's SSL CA certificate (for agent trust of self-signed certs).

### GET /agent/ca.pem.sha256

Download the SHA-256 checksum for ca.pem.

---

## Web API

All following endpoints require session auth (`Authorization: Bearer <token>`) or legacy admin key (`x-admin-key`). Role requirements are noted per endpoint.

---

### GET /api/ping

Unauthenticated liveness check. Available on both ports.

**Response (200):**

```json
{ "status": "ok", "utc": "2026-03-25T12:00:00+00:00" }
```

---

### GET /api/server-time

Return the server's local time and timezone. No auth required.

**Response (200):**

```json
{
  "local": "2026-03-25 14:00:00",
  "tz": "CET",
  "iso": "2026-03-25T14:00:00+01:00"
}
```

---

### GET /api/dashboard

Returns all agents with aggregated statistics.

**Auth:** admin, user, or readonly

**Response (200):**

```json
{
  "agents": [
    {
      "id": "my-vm",
      "hostname": "web-server-01",
      "ip": "192.168.1.101",
      "os_pretty": "Debian GNU/Linux 12 (bookworm)",
      "kernel": "6.1.0-21-amd64",
      "arch": "x86_64",
      "reboot_required": 0,
      "pending_count": 3,
      "last_seen": "2026-03-22T14:22:00+00:00",
      "seconds_ago": 45.2,
      "uptime_seconds": 345600,
      "tags": "prod,web",
      "last_job_type": "patch",
      "last_job_status": "done",
      "last_job_finished": "2026-03-22 14:00:00"
    }
  ],
  "stats": {
    "online": 5,
    "total": 6,
    "reboot_needed": 1,
    "total_pending": 12
  }
}
```

Managed agents use heartbeat + job-grace logic. Ping-only targets use retry-based reachability checks and can appear as `online`, `busy`, or `offline`.

---

### GET /api/agents/{agent_id}

Returns detailed info for a single agent including packages and recent jobs.

**Auth:** admin, user, or readonly

**Response (200):**

```json
{
  "agent": { ... },
  "packages": [ ... ],
  "jobs": [ ... ]
}
```

---

### POST /api/agents/ping-targets

Create a ping-only monitoring target.

**Auth:** admin

**Request Body (JSON):**

| Field      | Type   | Description |
|------------|--------|-------------|
| `hostname` | string | Display name shown in PatchPilot |
| `address`  | string | Hostname or IP address to ping |
| `id`       | string | Optional fixed ID |

**Response (200):**

```json
{
  "status": "created",
  "reachable": true,
  "agent": { ... }
}
```

---

### POST /api/agents/{agent_id}/ping-check

Run an immediate manual reachability check for a ping-only target.

**Auth:** admin or user

**Response (200):**

```json
{
  "status": "ok",
  "reachable": true
}
```

This endpoint is only valid for ping-only targets.

---

### POST /api/agents/{agent_id}/jobs

Creates a new job for an agent.

**Auth:** admin or user

**Request Body (JSON):**

| Field    | Type   | Description |
|----------|--------|-------------|
| `type`   | string | Any allowlisted job type from the server, including Linux, SSL, and HA-specific jobs |
| `params` | object | Optional parameters |

Ping-only targets reject managed jobs on this endpoint.

---

### POST /api/agents/{agent_id}/jobs/{job_id}/cancel

Cancels a pending or running job.

**Auth:** admin or user

**Response (200):**

```json
{ "status": "ok" }
```

---

### POST /api/agents/{agent_id}/jobs/cancel-pending

Cancels all pending jobs for an agent.

**Auth:** admin or user

**Response (200):**

```json
{ "status": "ok", "cancelled": 3 }
```

---

### PATCH /api/agents/{agent_id}/rename

Renames an agent. The agent picks up the new ID on its next heartbeat via `canonical_id`. All references (jobs, packages, schedules) are updated atomically.

**Auth:** admin

**Request Body (JSON):**

| Field    | Type   | Description |
|----------|--------|-------------|
| `new_id` | string | New agent ID (validated: `^[a-zA-Z0-9._-]{1,64}$`) |

---

### PATCH /api/agents/{agent_id}/tags

Set tags for an agent (comma-separated string).

**Auth:** admin or user

**Request Body (JSON):**

| Field  | Type   | Description |
|--------|--------|-------------|
| `tags` | string | Comma-separated tags, max 512 chars total |

---

### POST /api/agents/update-all

Queues `update_agent` jobs for all agents that have been seen within the last 24 hours.

**Auth:** admin

**Response (200):**

```json
{ "status": "queued", "count": 5 }
```

---

### DELETE /api/agents/{agent_id}

Deletes an agent and all associated packages and jobs (CASCADE).

**Auth:** admin

---

### POST /api/register-key

Generates a new registration key valid for 5 minutes.

**Auth:** admin

**Response (200):**

```json
{
  "key": "a0b1c2d3e4f5",
  "expires_in": 300
}
```

---

### GET /api/register-key

Returns the current registration key if one is active, or null.

**Auth:** admin

---

## Schedules

### GET /api/schedules

Returns all configured schedules and the agent list.

**Auth:** admin or user

---

### POST /api/schedules

Creates a new schedule.

**Auth:** admin

**Request Body (JSON):**

| Field    | Type   | Required | Description |
|----------|--------|----------|-------------|
| `name`   | string | yes      | Display name |
| `cron`   | string | yes      | Cron expression (5 fields, server local time) |
| `action` | string | yes      | `"patch"`, `"reboot"`, `"autoremove"`, or `"update_agent"` |
| `target` | string | yes      | Agent ID or `"all"` for all agents |

---

### PATCH /api/schedules/{sid}

Toggle a schedule on/off.

**Auth:** admin

---

### PUT /api/schedules/{sid}

Update a schedule (name, cron, action, target).

**Auth:** admin

---

### POST /api/schedules/{sid}/run

Manually trigger a schedule now.

**Auth:** admin or user

---

### DELETE /api/schedules/{sid}

Deletes a schedule.

**Auth:** admin

---

## Settings

### GET /api/settings

Returns current server settings. Sensitive values (`smtp_password`, `telegram_token`) are replaced with `"***"`. Also includes computed `internal_url`, `agent_url`, and `ssl_enabled` fields.

**Auth:** admin, user, or readonly

---

### POST /api/settings

Updates server settings. Values equal to `"***"` are kept unchanged (masked fields are not overwritten). Sensitive values are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) before storing in the database, keyed from `PATCHPILOT_ADMIN_KEY` via PBKDF2. Unknown keys are rejected.

**Auth:** admin

**Allowed keys:** `telegram_token`, `telegram_chat_id`, `telegram_enabled`, `telegram_notify_offline`, `telegram_notify_patches`, `telegram_notify_failures`, `telegram_notify_success`, `email_enabled`, `smtp_host`, `smtp_port`, `smtp_security`, `smtp_user`, `smtp_password`, `smtp_to`, `notify_offline`, `notify_offline_minutes`, `notify_patches`, `notify_failures`, `server_port`, `agent_port`, `agent_ssl`

Port or SSL changes trigger a server restart automatically.

---

### POST /api/settings/test/{channel}

Test a notification channel. Channel is `telegram` or `email`.

**Auth:** admin

---

## SSL Management

### POST /api/settings/generate-cert

Generate a self-signed SSL certificate (RSA 2048-bit) with configurable validity.

**Auth:** admin

**Request Body (JSON, optional):**

| Field   | Type | Default | Description |
|---------|------|---------|-------------|
| `years` | int  | 3       | Certificate validity (1-10 years) |

**Response (200):**

```json
{
  "status": "generated",
  "certfile": "/opt/patchpilot/ssl/cert.pem",
  "keyfile": "/opt/patchpilot/ssl/key.pem",
  "info": { "subject": "CN=hostname", "expires": "Mar 25 2029", "path": "..." },
  "restart_pending": false
}
```

---

### POST /api/settings/ssl-enable

Enable SSL with the specified certificate and key paths. Paths must be within the SSL directory. Triggers a server restart.

**Auth:** admin

**Request Body (JSON):**

| Field      | Type   | Description |
|------------|--------|-------------|
| `certfile` | string | Path to SSL certificate (must be in `/opt/patchpilot/ssl/`) |
| `keyfile`  | string | Path to SSL private key (must be in `/opt/patchpilot/ssl/`) |

---

### POST /api/settings/ssl-disable

Disable SSL and restart the server on plain HTTP.

**Auth:** admin

---

### GET /api/settings/ssl-info

Return current SSL status and certificate info.

**Auth:** admin

**Response (200):**

```json
{
  "enabled": true,
  "certfile": "/opt/patchpilot/ssl/cert.pem",
  "keyfile": "/opt/patchpilot/ssl/key.pem",
  "info": { "subject": "CN=hostname", "expires": "Mar 25 2029", "path": "..." }
}
```

---

### POST /api/settings/deploy-ssl

Deploy the CA trust bundle to all agents via the job system. Linux agents receive chained `update_agent` + `deploy_ssl` jobs. HAOS agents receive a direct `deploy_ssl` job with the signed CA rollover payload. Returns a batch ID for tracking progress.

**Auth:** admin

**Request Body (JSON, optional):**

| Field         | Type   | Description |
|---------------|--------|-------------|
| `retry_batch` | string | Previous batch ID to retry only failed agents |

**Response (200):**

```json
{ "status": "deployed", "agent_count": 5, "batch_id": "a1b2c3d4e5f6" }
```

---

### GET /api/settings/deploy-ssl/status?batch={batch_id}

Return progress of SSL deployment for a specific batch. Shows per-agent status (updating, deploying, done, failed).

**Auth:** admin

---

## User Management

### GET /api/users

List all users.

**Auth:** admin

**Response (200):**

```json
{
  "users": [
    { "id": 1, "username": "admin", "role": "admin", "created": "2026-03-20 10:00:00" }
  ]
}
```

---

### POST /api/users

Create a new user.

**Auth:** admin

**Request Body (JSON):**

| Field      | Type   | Required | Description |
|------------|--------|----------|-------------|
| `username` | string | yes      | Username (max 64 chars) |
| `password` | string | yes      | Password (4-1024 chars) |
| `role`     | string | no       | `"admin"`, `"user"`, or `"readonly"` (default: `"user"`) |

---

### PATCH /api/users/{user_id}

Update a user's role or password. Active sessions for the user are invalidated immediately.

**Auth:** admin

---

### DELETE /api/users/{user_id}

Delete a user. Active sessions are invalidated.

**Auth:** admin

---

## Monitoring

### GET /api/alerts

Return all VMs that have been offline for more than 5 minutes.

**Auth:** admin, user, or readonly

---

### GET /api/status/badge

Return a shields.io-style SVG badge showing X/Y online agents.

**Auth:** admin, user, or readonly

---

### GET /metrics

Prometheus-compatible metrics endpoint. No auth required.

```
patchpilot_agents_total 6
patchpilot_agents_online 5
patchpilot_pending_updates_total 12
patchpilot_reboot_required_total 1
patchpilot_jobs_total{status="done"} 47
patchpilot_jobs_total{status="failed"} 2
```

---

## Error Codes

| HTTP Status | Meaning |
|-------------|---------|
| `200` | Success |
| `401` | Invalid or missing token / authentication required |
| `403` | Insufficient permissions / re-registration requires current token |
| `404` | Agent not found |
| `409` | Agent ID or username already exists |
| `422` | Invalid request body or parameters |
| `429` | Rate limit exceeded |
| `500` | Internal server error |

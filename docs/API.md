# PatchPilot REST API

Complete reference for all API endpoints.

## Base URL

```
http://<server-host>:<port>
```

---

## Authentication

PatchPilot uses two authentication mechanisms:

### Admin Key (Web UI Endpoints)

All endpoints under `/api/dashboard`, `/api/schedules`, and most `/api/agents/...` management endpoints require the header:

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

Registration keys are generated on-demand from the Deploy page and expire after 5 minutes.

**Token Flow:**
```
1. Admin generates registration key via UI (Deploy page)
2. Agent  → POST /api/agents/register  (Header: x-register-key)
3. Server → { agent_id, token }
4. Agent stores token in /etc/patchpilot/state.json (chmod 600)
5. Agent  → POST /api/agents/{id}/heartbeat  (Header: x-token)
6. Agent  → GET  /api/agents/{id}/jobs       (Header: x-token)
7. Agent  → POST /api/agents/{id}/jobs/{id}/result (Header: x-token)
```

Re-registration of an existing agent ID requires the current valid token (not the registration key).

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
  "canonical_port": "8050",
  "canonical_id": "new-name"
}
```

`canonical_port` signals port migration. `canonical_id` signals an agent rename.

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

Job types: `patch`, `reboot`, `autoremove`, `update_agent`

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

## Web API (Admin)

All following endpoints require the header `x-admin-key: <PATCHPILOT_ADMIN_KEY>`.

---

### GET /api/dashboard

Returns all agents with aggregated statistics.

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

An agent is considered "online" when `seconds_ago < 120`.

---

### POST /api/agents/{agent_id}/jobs

Creates a new job for an agent.

**Request Body (JSON):**

| Field    | Type   | Description |
|----------|--------|-------------|
| `type`   | string | `"patch"`, `"reboot"`, `"autoremove"`, or `"update_agent"` |
| `params` | object | Optional parameters |

---

### POST /api/agents/{agent_id}/jobs/{job_id}/cancel

Cancels a pending or running job.

**Response (200):**

```json
{ "status": "cancelled" }
```

---

### PUT /api/agents/{agent_id}/rename

Renames an agent. The agent picks up the new ID on its next heartbeat via `canonical_id`.

**Request Body (JSON):**

| Field    | Type   | Description |
|----------|--------|-------------|
| `new_id` | string | New agent ID (validated: `^[a-zA-Z0-9._-]{1,64}$`) |

---

### POST /api/agents/update-all

Queues `update_agent` jobs for all agents that have been seen within the last 24 hours.

**Response (200):**

```json
{ "status": "queued", "count": 5 }
```

---

### DELETE /api/agents/{agent_id}

Deletes an agent and all associated packages and jobs (CASCADE).

---

### POST /api/register-key

Generates a new registration key valid for 5 minutes.

**Response (200):**

```json
{
  "key": "a0b1c2d3e4f5",
  "expires_in": 300
}
```

---

### GET /api/schedules

Returns all configured schedules and the agent list.

---

### POST /api/schedules

Creates a new schedule.

**Request Body (JSON):**

| Field    | Type   | Required | Description |
|----------|--------|----------|-------------|
| `name`   | string | yes      | Display name |
| `cron`   | string | yes      | Cron expression (5 fields, server local time) |
| `action` | string | yes      | `"patch"`, `"reboot"`, `"autoremove"`, or `"update_agent"` |
| `target` | string | yes      | Agent ID or `"all"` for all agents |

---

### PATCH /api/schedules/{sid}

Toggle or update a schedule.

---

### DELETE /api/schedules/{sid}

Deletes a schedule.

---

### GET /api/settings

Returns current server settings (Telegram, SMTP, port).

---

### PUT /api/settings

Updates server settings.

---

## Monitoring

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
| `401` | Invalid or missing token / admin key |
| `403` | Re-registration requires current token / invalid registration key |
| `404` | Agent not found |
| `409` | Agent ID already exists (registration) |
| `422` | Invalid request body |
| `429` | Rate limit exceeded |
| `500` | Internal server error |

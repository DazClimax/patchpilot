# PatchPilot — Agent Instructions

Self-hosted patch management for Debian/Ubuntu VMs. Pull-based: agents poll the server, the server never SSH-es into VMs.

---

## Repository Layout

```
server/          FastAPI backend (Python)
  app.py         Main app — all REST endpoints (~1900 lines)
  db.py          SQLite schema + migrations + password hashing
  scheduler.py   APScheduler cron engine
  notifications.py  Telegram + SMTP routing
  telegram_bot.py   Telegram bot commands
  metrics.py     Prometheus /metrics endpoint
  crypto.py      Fernet encryption for DB secrets
  start.sh       Dual-port launch script (UI port + Agent port)
  requirements.txt
  tests/
    conftest.py       Shared pytest fixtures (in-memory SQLite)
    test_agents.py    Agent registration, heartbeat, jobs
    test_schedules.py Schedule CRUD + toggle/update behaviour
    test_security.py  Token isolation, cross-agent access

frontend/        React 18 + TypeScript + Vite + Arwes
  src/
    pages/       Dashboard, VmDetail, Schedule, Settings, Deploy,
                 Login, Users, About
    components/  Button, Badge, Card, Toast, ConfirmModal, LogModal,
                 Layout, Dropdown, SectionHeader, ErrorBoundary
    api/client.ts  Typed API client (session auth)
    theme.ts       Colors, glow effects, glass backgrounds

agent/
  agent.py       VM agent — stdlib only, no pip deps
  install.sh     One-liner installer

docs/            Markdown documentation
docker/          Docker support files
home-assistant-addons/  HA addon manifest + config
deploy.sh        rsync-based deploy to production server
patchpilot.service  systemd unit
```

---

## Setup & Running

### Backend

```bash
cd server
pip install -r requirements.txt
pip install -r requirements-dev.txt     # pytest, httpx
uvicorn app:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # localhost:5173, proxies API to :8000
npm run build        # production build → frontend/dist/
```

### Deploy to production

```bash
cd frontend && npm run build && cd ..
PATCHPILOT_HOST=root@<server-ip> bash deploy.sh
```

---

## Tests

```bash
cd server
python3 -m pytest tests/ -v
```

All 54 tests must pass. Tests use in-memory SQLite — no real DB needed.

**Key fixture rules (conftest.py):**
- `client` patches `get_db_ctx`, `init_db`, `_verify_register_key`, `scheduler`, `_load_schedules`, `register_system_jobs`
- `_reset_app_state` autouse fixture clears `_RATE_LIMIT`, `_AGENT_RATE_LIMIT`, `_sessions`, `_CACHE`, `_last_heartbeat` between tests
- `registered_agent` registers a real agent via the API and returns `(agent_id, token)`
- Tests authenticate via `x-admin-key: test-admin-key-fixed` (set on client by default)

---

## Key Constants (server/app.py)

| Constant | Value | Purpose |
|----------|-------|---------|
| `ALLOWED_JOB_TYPES` | set of strings (line ~270) | All valid job type strings — validate before inserting |
| `_UI_PORT` | env `PORT`, default `8443` | UI + admin endpoints |
| `_AGENT_PORT` | env `AGENT_PORT`, default `8050` | Agent-facing endpoints (always HTTP) |
| `_HEARTBEAT_MIN_INTERVAL` | `30` seconds | Throttle: ignore duplicate heartbeats |
| `_CACHE_TTL_DASHBOARD` | `10` seconds | Dashboard response cache TTL |
| `_CACHE_TTL_AGENT` | `5` seconds | Per-agent detail cache TTL |
| `_SENSITIVE_KEYS` | `smtp_password`, `telegram_token` | Encrypted at rest with Fernet (`crypto.py`) |

---

## Auth Model

| Layer | Mechanism |
|-------|-----------|
| UI login | Username + PBKDF2-SHA256 password → session token (UUID) in `_sessions` dict |
| Admin fallback | `x-admin-key` header vs `PATCHPILOT_ADMIN_KEY` env var |
| Agent auth | `x-token` header vs SHA-256 hash in DB (via `hmac.compare_digest`) |
| Agent registration | `x-register-key` header vs SHA-256 hash in `settings` table |
| Roles | `admin` / `user` / `readonly` — enforced via `require_role()` dependency |

---

## Port Routing (Dual-Port Architecture)

Agent-only endpoints are blocked on the UI port and vice versa:

```
Agent-only  (AGENT_PORT only):
  POST /api/agents/register
  POST /api/agents/{id}/heartbeat
  GET  /api/agents/{id}/jobs
  POST /api/agents/{id}/jobs/{job_id}/result
  GET  /agent/*

Shared on both ports:
  GET /api/ping
  GET /api/server-time

All other endpoints: UI port only
```

`_is_agent_only_request(path, method)` — used by the `_port_routing` middleware.

---

## Database

SQLite at `server/patchpilot.db`. WAL mode, permissions 0600.

**Tables:** `agents`, `jobs`, `packages`, `schedules`, `settings`, `users`, `rename_aliases`

**Migrations** run at startup via `db.py:init_db()`. Always add columns with `ALTER TABLE … ADD COLUMN IF NOT EXISTS` — never recreate tables.

---

## Schedules

- `schedule_job(sid, name, cron, action, target)` — registers a job in APScheduler
- `toggle_schedule` PATCH: sets DB `enabled` flag AND calls `schedule_job` (enable) or `scheduler.remove_job(str(sid))` (disable)
- `update_schedule` PUT: re-registers with APScheduler **only if `enabled=1`**; if disabled, calls `scheduler.remove_job`
- `action` must be a value from `ALLOWED_JOB_TYPES`

---

## Frontend Conventions

- **Theme:** import from `../theme` — use `colors`, `glow`, `glassBg`, `controlStyles`
- **API calls:** use `api` from `../api/client` — never raw `fetch`
- **Breakpoint:** 640px — sidebar becomes bottom tab bar on mobile
- **Font sizes:** min 9px mobile, 10px desktop
- **Toast durations:** errors 8000ms, success/info 4000ms
- **Arwes:** use `<Animator>` + `<Text>` + `<FrameSVGCorners>` for sci-fi styling
- **No Google Fonts** — fonts loaded via `@fontsource` packages only

---

## Crypto (server/crypto.py)

Secrets in the `settings` table are encrypted at rest:

```python
from crypto import encrypt, decrypt

stored = encrypt("my-secret")    # → "enc:<base64-fernet-token>"
plain  = decrypt(stored)          # → "my-secret"
decrypt("plain-text")             # → "plain-text" (no-op if not prefixed)
```

Key is derived from `PATCHPILOT_ADMIN_KEY` via PBKDF2 (100k iterations). Changing the admin key breaks decryption of existing secrets.

---

## Agent (agent/agent.py)

- Pure Python stdlib — **zero pip dependencies**
- Uses `os.fork()` (not threading) for self-update restart
- Polls `GET /api/agents/{id}/jobs` every 10 seconds
- Sends heartbeat `POST /api/agents/{id}/heartbeat` every 60 seconds
- TLS minimum: TLSv1.2 (`ssl.TLSVersion.TLSv1_2`)
- Self-update: downloads new `agent.py`, verifies SHA-256, replaces self, forks restart

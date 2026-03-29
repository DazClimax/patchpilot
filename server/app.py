import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from apscheduler.triggers.cron import CronTrigger as _CronTrigger
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader

from db import init_db, db as get_db_ctx, hash_password, verify_password
from scheduler import scheduler, schedule_job, register_system_jobs
from notifications import notification_manager
import metrics as metrics_module

app = FastAPI(title="PatchPilot API")

_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'"
)

# ---------------------------------------------------------------------------
# CORS — restrict to specific origins in production.
# Read PATCHPILOT_ALLOWED_ORIGINS from env (comma-separated) or
# fall back to localhost defaults. Wildcard "*" is not allowed.
# ---------------------------------------------------------------------------
_raw_origins = os.environ.get(
    "PATCHPILOT_ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:8000",
)
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "x-token", "x-admin-key", "Authorization"],
)

# ---------------------------------------------------------------------------
# Dual-port routing — restrict endpoints to the correct port.
# UI port (PORT) serves dashboard, settings, auth, static files.
# Agent port (AGENT_PORT) serves agent heartbeat, jobs, downloads.
# Both ports serve /api/ping.  If both ports are the same, no filtering.
# ---------------------------------------------------------------------------
_UI_PORT = int(os.environ.get("PORT", "8443"))
_AGENT_PORT = int(os.environ.get("AGENT_PORT", "8050"))
_AGENT_SSL = os.environ.get("AGENT_SSL", "") == "1" and bool(os.environ.get("SSL_CERTFILE"))
_AGENT_SCHEME = "https" if _AGENT_SSL else "http"

# Prefixes that are agent-only (served on AGENT_PORT)
_AGENT_PREFIXES = ("/api/agents/", "/agent/")

@app.middleware("http")
async def _port_routing(request: Request, call_next):
    """Block requests that arrive on the wrong port."""
    if _UI_PORT != _AGENT_PORT:
        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        path = request.url.path
        is_agent_path = any(path.startswith(p) for p in _AGENT_PREFIXES)
        is_shared = path in ("/api/ping", "/api/server-time")

        # Agent-only paths: heartbeat, job polling, result reporting, registration
        _agent_only = ("/api/agents/register", "/agent/")
        is_agent_only = any(path.startswith(p) or path == p.rstrip("/") for p in _agent_only) or \
            (path.startswith("/api/agents/") and ("/heartbeat" in path or "/jobs" in path and "/result" in path))

        if not is_shared:
            if port == _AGENT_PORT and not is_agent_path:
                return JSONResponse(status_code=404, content={"detail": "Not available on agent port"})
            if port == _UI_PORT and path.startswith("/agent/"):
                # Block raw file downloads on UI port
                return JSONResponse(status_code=404, content={"detail": "Not available on UI port"})
    return await call_next(request)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy", _CONTENT_SECURITY_POLICY)
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

# ---------------------------------------------------------------------------
# Admin-Key — protects all Web-UI endpoints (Dashboard, Jobs, Schedules …).
# Set PATCHPILOT_ADMIN_KEY as an environment variable on the server.
# If not set, a random key is generated at startup and logged
# (safe for initial installation).
# ---------------------------------------------------------------------------
_ADMIN_KEY_ENV = os.environ.get("PATCHPILOT_ADMIN_KEY", "")
if not _ADMIN_KEY_ENV:
    _ADMIN_KEY_ENV = secrets.token_hex(32)
    import sys
    print(
        f"[patchpilot] WARNING: PATCHPILOT_ADMIN_KEY not set. "
        f"Using ephemeral key for this session: {_ADMIN_KEY_ENV}",
        file=sys.stderr,
    )

_admin_key_header = APIKeyHeader(name="x-admin-key", auto_error=False)


def require_admin(x_admin_key: str = Depends(_admin_key_header)):
    """Dependency: validates the admin key for web-UI endpoints."""
    if not x_admin_key or not hmac.compare_digest(
        x_admin_key.encode(), _ADMIN_KEY_ENV.encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing admin key")


# ---------------------------------------------------------------------------
# Session-based auth (username + password)
# ---------------------------------------------------------------------------
_sessions: dict[str, dict] = {}  # token → {user_id, username, role, created}
_SESSION_MAX_AGE = 86400  # 24h

_auth_header = APIKeyHeader(name="authorization", auto_error=False)


_session_last_cleanup = 0.0


def _cleanup_sessions():
    """Evict expired sessions periodically (every 5 min)."""
    global _session_last_cleanup
    now = time.monotonic()
    if now - _session_last_cleanup < 300:
        return
    _session_last_cleanup = now
    expired = [t for t, s in _sessions.items() if now - s["created"] >= _SESSION_MAX_AGE]
    for t in expired:
        _sessions.pop(t, None)


def _get_session(request: Request) -> dict | None:
    """Extract session from Authorization: Bearer <token> header."""
    _cleanup_sessions()
    auth_val = request.headers.get("authorization", "")
    if auth_val.startswith("Bearer "):
        token = auth_val[7:]
        session = _sessions.get(token)
        if session and (time.monotonic() - session["created"]) < _SESSION_MAX_AGE:
            return session
        _sessions.pop(token, None)  # expired
    return None


def require_role(*roles: str):
    """Dependency factory: require user to have one of the given roles.
    Also accepts legacy x-admin-key header (treated as admin)."""
    def dependency(request: Request, x_admin_key: str = Depends(_admin_key_header)):
        # Legacy admin key check
        if x_admin_key and hmac.compare_digest(
            x_admin_key.encode(), _ADMIN_KEY_ENV.encode()
        ):
            request.state.user = {"username": "admin", "role": "admin", "user_id": 0}
            return
        # Session token check
        session = _get_session(request)
        if session and session["role"] in roles:
            request.state.user = session
            return
        if session:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        raise HTTPException(status_code=401, detail="Authentication required")
    return dependency


# Register monitoring router — must be after require_admin is defined
app.include_router(metrics_module.router, dependencies=[Depends(require_role("admin"))])

STATIC_DIR = Path(os.environ.get("PATCHPILOT_STATIC_DIR", str(Path(__file__).parent.parent / "frontend" / "dist")))

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
_AGENT_ID_RE = re.compile(r'^[a-zA-Z0-9._-]{1,64}$')
_TG_TOKEN_RE  = re.compile(r'^\d+:[A-Za-z0-9_-]{35,}$')
ALLOWED_JOB_TYPES = {"patch", "dist_upgrade", "force_patch", "refresh_updates", "reboot", "update_agent", "autoremove", "deploy_ssl", "ack_config_review", "ha_backup", "ha_core_update", "ha_backup_update", "ha_supervisor_update", "ha_os_update", "ha_addon_update", "ha_addons_update"}

def _validate_agent_id(agent_id: str):
    if not _AGENT_ID_RE.match(agent_id):
        raise HTTPException(status_code=422, detail="Invalid agent ID: use a-z A-Z 0-9 . _ - (max 64 chars)")

# MED-6: Field length limits for agent-reported strings
_FIELD_LIMITS = {
    "hostname": 64,    # DNS label limit — covers virtually all real hostnames
    "ip":        45,   # max IPv6 length
    "os_pretty": 128,
    "kernel":    64,
    "arch":      16,
    "package_manager": 16,
    "agent_version": 32,
    "agent_type": 16,
    "capabilities": 512,
}

def _sanitize_agent_fields(data: dict) -> dict:
    """Truncate free-form agent fields to their maximum allowed length."""
    return {k: (str(data[k])[:lim] if data.get(k) else data.get(k))
            for k, lim in _FIELD_LIMITS.items()}


def _infer_package_manager(fields: dict) -> str | None:
    package_manager = fields.get("package_manager")
    if package_manager:
        return package_manager
    os_pretty = (fields.get("os_pretty") or "").lower()
    if any(name in os_pretty for name in ("debian", "ubuntu", "raspbian", "mint", "pop!_os", "pop os")):
        return "apt"
    if any(name in os_pretty for name in ("fedora", "rhel", "red hat", "redhat", "rocky", "alma", "centos", "nobara")):
        return "dnf"
    if "home assistant os" in os_pretty:
        return "haos"
    return None


def _infer_agent_type(fields: dict) -> str:
    agent_type = (fields.get("agent_type") or "").strip().lower()
    if agent_type in {"linux", "haos"}:
        return agent_type
    os_pretty = (fields.get("os_pretty") or "").lower()
    if "home assistant os" in os_pretty:
        return "haos"
    return "linux"


def _normalize_capabilities(fields: dict) -> str:
    raw = str(fields.get("capabilities") or "").strip()
    if not raw:
        return ""
    parts = []
    for item in raw.split(","):
        name = item.strip().lower()
        if name and re.fullmatch(r"[a-z0-9_.-]{1,64}", name):
            parts.append(name)
    deduped = []
    for item in parts:
        if item not in deduped:
            deduped.append(item)
    return ",".join(deduped)[:512]

def _validate_cron(cron: str):
    """MED-8: Validate cron expression using APScheduler before DB insert."""
    parts = cron.strip().split()
    if len(parts) != 5:
        raise HTTPException(status_code=422, detail="Invalid cron expression (must have 5 fields)")
    minute, hour, day, month, dow = parts
    try:
        _CronTrigger(minute=minute, hour=hour, day=day, month=month,
                     day_of_week=dow, timezone="Europe/Berlin")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid cron expression: {exc}") from exc

def _validate_schedule_target(target: str):
    """Accept 'all' or a comma-separated list of valid agent IDs (max 64 VMs)."""
    if target == "all":
        return
    parts = [p.strip() for p in target.split(",") if p.strip()]
    if not parts or len(parts) > 64:
        raise HTTPException(status_code=422, detail="Target must be 'all' or 1–64 comma-separated agent IDs")
    for part in parts:
        if not _AGENT_ID_RE.match(part):
            raise HTTPException(status_code=422, detail=f"Invalid agent ID in target: {part!r}")

def _validate_smtp_host(host: str):
    """Reject loopback, private, link-local, and reserved IPs to block SSRF."""
    if not host:
        return
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_reserved:
            raise HTTPException(status_code=422, detail="SMTP host must be a public address")
        # Explicitly block AWS/GCP metadata endpoints
        if str(addr) == "169.254.169.254":
            raise HTTPException(status_code=422, detail="SMTP host must be a public address")
    except ValueError:
        # It's a hostname — resolve and validate the resulting IP(s)
        if host:
            try:
                infos = socket.getaddrinfo(host, None)
                for info in infos:
                    addr_str = info[4][0]
                    try:
                        addr = ipaddress.ip_address(addr_str)
                        if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_reserved:
                            raise HTTPException(status_code=422, detail="SMTP host resolves to a private/reserved address")
                    except ValueError:
                        pass
            except socket.gaierror:
                pass  # DNS failure — let SMTP connection fail naturally

# ---------------------------------------------------------------------------
# On-demand registration key (generated when requested, valid 5 min)
# No key is active until an admin explicitly requests one.
# ---------------------------------------------------------------------------
_REGISTER_KEY_TTL = 300  # seconds (5 min)


def _hash_register_key(key: str) -> str:
    """SHA-256 hash for register key storage."""
    return hashlib.sha256(key.encode()).hexdigest()


def _generate_register_key() -> tuple[str, float]:
    """Generate a fresh register key (DB-backed, shared across processes).
    Stores SHA-256 hash in DB, returns plaintext only in API response."""
    key = secrets.token_hex(16)  # 32 chars / 128 bits
    key_hash = _hash_register_key(key)
    expires = str(int(time.time() + _REGISTER_KEY_TTL))
    with get_db_ctx() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('register_key', ?)", (key_hash,))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('register_key_ts', ?)", (expires,))
    return key, float(_REGISTER_KEY_TTL)


def _get_active_register_key() -> tuple[str, float] | tuple[None, float]:
    """Return current key hash + remaining seconds, or (None, 0) if expired."""
    with get_db_ctx() as conn:
        row_key = conn.execute("SELECT value FROM settings WHERE key='register_key'").fetchone()
        row_ts = conn.execute("SELECT value FROM settings WHERE key='register_key_ts'").fetchone()
    if not row_key or not row_ts:
        return None, 0.0
    try:
        expires = int(row_ts["value"])
    except (ValueError, TypeError):
        return None, 0.0
    remaining = expires - time.time()
    if remaining > 0:
        return row_key["value"], remaining
    return None, 0.0


def _verify_register_key(submitted: str):
    """Check submitted key against stored hash (DB-backed, timing-safe)."""
    if not submitted:
        raise HTTPException(status_code=403, detail="Registration requires a register key (see Deploy page)")
    key, remaining = _get_active_register_key()
    if key is None or remaining <= 0:
        raise HTTPException(status_code=403, detail="No active register key — generate one from the Deploy page")
    submitted_hash = _hash_register_key(submitted)
    if not hmac.compare_digest(submitted_hash, key):  # key is already a hash from DB
        raise HTTPException(status_code=403, detail="Invalid or expired register key")


# ---------------------------------------------------------------------------
# Simple in-memory rate limiter (M-5)
# ---------------------------------------------------------------------------
_RATE_LIMIT: dict[str, list[float]] = {}
_RATE_WINDOW = 60   # seconds
_RATE_MAX    = 20   # max requests per IP per window

_TRUSTED_PROXY = os.environ.get("PATCHPILOT_TRUSTED_PROXY", "")

def _get_client_ip(request: Request) -> str:
    """MED-2: Extract real client IP.  Only honour X-Forwarded-For when the
    connection comes from the configured trusted proxy address."""
    direct_ip = request.client.host if request.client else ""
    if _TRUSTED_PROXY and direct_ip == _TRUSTED_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "")
        candidate = forwarded.split(",")[0].strip()
        if candidate:
            return candidate
    return direct_ip or "unknown"

def _check_rate_limit(request: Request):
    ip = _get_client_ip(request)
    now = time.monotonic()
    hits = [t for t in _RATE_LIMIT.get(ip, []) if now - t < _RATE_WINDOW]
    hits.append(now)
    if hits:
        _RATE_LIMIT[ip] = hits
    else:
        # MED-3: evict stale entry so the dict doesn't grow unboundedly
        _RATE_LIMIT.pop(ip, None)
    # MED-3 / MEDIUM-9: periodically prune IPs that haven't been seen in 2× the window
    if len(_RATE_LIMIT) > 5000:
        cutoff = now - _RATE_WINDOW * 2
        stale = [k for k, ts in _RATE_LIMIT.items() if not ts or ts[-1] < cutoff]
        for k in stale:
            _RATE_LIMIT.pop(k, None)
    if len(hits) > _RATE_MAX:
        raise HTTPException(status_code=429, detail="Too many requests")

# MEDIUM-5: Tag content validation regex — module-level constant
_TAG_RE = re.compile(r'^[a-zA-Z0-9._-]+$')

# Agent-specific rate limiter (more generous than admin/registration endpoints)
_AGENT_RATE_LIMIT: dict[str, list[float]] = {}
_AGENT_RATE_MAX = 120  # generous for legitimate agents


def _check_agent_rate_limit(request: Request):
    ip = _get_client_ip(request)
    now = time.monotonic()
    hits = [t for t in _AGENT_RATE_LIMIT.get(ip, []) if now - t < _RATE_WINDOW]
    hits.append(now)
    _AGENT_RATE_LIMIT[ip] = hits
    if len(_AGENT_RATE_LIMIT) > 500:
        cutoff = now - _RATE_WINDOW * 2
        stale = [k for k, ts in _AGENT_RATE_LIMIT.items() if not ts or ts[-1] < cutoff]
        for k in stale:
            _AGENT_RATE_LIMIT.pop(k, None)
    if len(hits) > _AGENT_RATE_MAX:
        raise HTTPException(status_code=429, detail="Too many requests")


# PERFORMANCE: Lightweight in-memory response cache (no Redis dependency).
# Each entry: { key: (payload_dict, expires_at_monotonic) }
# Invalidated explicitly on write operations that affect the cached data.
_CACHE: dict = {}
_CACHE_TTL_DASHBOARD = 10   # seconds
_CACHE_TTL_AGENT = 5        # seconds


def _cache_get(key: str):
    """Return cached value if still valid, else None."""
    entry = _CACHE.get(key)
    if entry and time.monotonic() < entry[1]:
        return entry[0]
    _CACHE.pop(key, None)
    return None


def _cache_set(key: str, value, ttl: float):
    _CACHE[key] = (value, time.monotonic() + ttl)


def _cache_invalidate(*keys: str):
    for k in keys:
        _CACHE.pop(k, None)


# PERFORMANCE: Heartbeat throttle — track last accepted heartbeat timestamp
# per agent in memory so we can skip DB writes for agents that check in more
# frequently than every 30 seconds.
_HEARTBEAT_MIN_INTERVAL = 30   # seconds
_last_heartbeat: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Startup / Shutdown
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Port-change helpers
# ---------------------------------------------------------------------------

_ENV_FILE   = Path(os.environ.get("PATCHPILOT_ENV_FILE", str(Path(__file__).parent.parent / ".env")))
_SERVER_PORT = int(os.environ.get("PORT", "8000"))
_LEGACY_PORT = int(os.environ.get("PORT_LEGACY", "0"))


# How long the forwarder waits between migration checks (seconds)
_LEGACY_CHECK_INTERVAL = 30
# Grace period after the last forwarded connection before checking migration.
# Must be > agent poll interval (default 60s) so we're sure idle = migrated.
_LEGACY_AGENT_INTERVAL = 75


def _clear_env_legacy() -> None:
    """Remove PORT_LEGACY from the EnvironmentFile — forwarder no longer needed."""
    try:
        lines = _ENV_FILE.read_text().splitlines() if _ENV_FILE.exists() else []
        content = "\n".join(l for l in lines if not l.startswith("PORT_LEGACY=")) + "\n"
        # MEDIUM-4: Atomic write via temp file to avoid partial writes
        tmp = _ENV_FILE.with_suffix(".env.tmp")
        tmp.write_text(content)
        os.replace(tmp, _ENV_FILE)
    except Exception as exc:
        import sys
        print(f"[patchpilot] Warning: could not clear PORT_LEGACY: {exc}", file=sys.stderr)


def _all_agents_on_new_port(idle_secs: float) -> bool:
    """Return True when it is safe to shut down the legacy forwarder.

    Conditions (both must hold):
    1. The forwarder has been idle for at least _LEGACY_AGENT_INTERVAL seconds.
       If an agent were still using the old port it would have connected by now.
    2. Every agent that has been active in the last 24 h sent a heartbeat
       within the last 3 minutes — meaning they are all reachable on the new
       port and have received the canonical_port redirect.
    """
    if idle_secs < _LEGACY_AGENT_INTERVAL:
        return False
    try:
        with get_db_ctx() as conn:
            # Agents active in last 24 h
            active = conn.execute(
                "SELECT COUNT(*) as n FROM agents "
                "WHERE (julianday('now','localtime') - julianday(last_seen)) * 86400 < 86400"
            ).fetchone()["n"]
            if active == 0:
                return True   # no agents at all — nothing to wait for
            # Of those, how many checked in within the last 3 minutes?
            recent = conn.execute(
                "SELECT COUNT(*) as n FROM agents "
                "WHERE (julianday('now','localtime') - julianday(last_seen)) * 86400 < 180"
            ).fetchone()["n"]
            return recent >= active
    except Exception:
        return False


def _start_legacy_forwarder(from_port: int, to_port: int) -> None:
    """Forward TCP connections from_port → to_port in background threads.

    Every _LEGACY_CHECK_INTERVAL seconds the forwarder checks whether all
    known agents have recently heartbeated on the new port.  Once confirmed,
    it removes PORT_LEGACY from .env and exits so it is not restarted.
    """
    def _pipe(src: socket.socket, dst: socket.socket) -> None:
        try:
            src.settimeout(60)  # MEDIUM-13: idle connection timeout
            while chunk := src.recv(4096):
                dst.sendall(chunk)
        except OSError:
            pass
        finally:
            for s in (src, dst):
                try: s.close()
                except OSError: pass

    # MEDIUM-13: Limit concurrent forwarded connections
    _fwd_sem = threading.BoundedSemaphore(50)

    def _serve() -> None:
        import sys
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.settimeout(_LEGACY_CHECK_INTERVAL)
        last_connection = time.monotonic()
        try:
            srv.bind(("0.0.0.0", from_port))
            srv.listen(128)
            print(f"[patchpilot] Legacy forwarder active: :{from_port} → :{to_port}", file=sys.stderr)
            while True:
                try:
                    client, _ = srv.accept()
                    last_connection = time.monotonic()
                    if _fwd_sem.acquire(blocking=False):
                        def _handle(c, sem=_fwd_sem):
                            try:
                                remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                                remote.connect(("127.0.0.1", to_port))
                                t1 = threading.Thread(target=_pipe, args=(c, remote), daemon=True)
                                t2 = threading.Thread(target=_pipe, args=(remote, c), daemon=True)
                                t1.start(); t2.start()
                                t1.join(); t2.join()
                            except OSError:
                                c.close()
                            finally:
                                sem.release()
                        threading.Thread(target=_handle, args=(client,), daemon=True).start()
                    else:
                        client.close()  # over connection limit
                except socket.timeout:
                    idle = time.monotonic() - last_connection
                    if _all_agents_on_new_port(idle):
                        print(
                            f"[patchpilot] All agents migrated to :{to_port} — "
                            f"deactivating legacy forwarder :{from_port}",
                            file=sys.stderr,
                        )
                        _clear_env_legacy()
                        return
        except OSError as exc:
            print(f"[patchpilot] Legacy forwarder error on :{from_port}: {exc}", file=sys.stderr)
        finally:
            srv.close()

    threading.Thread(target=_serve, daemon=True).start()


def _update_env_port(new_port: str, old_port: str) -> None:
    """Persist PORT=new and PORT_LEGACY=old in the systemd EnvironmentFile."""
    try:
        lines = _ENV_FILE.read_text().splitlines() if _ENV_FILE.exists() else []
        port_ok = legacy_ok = False
        result = []
        for line in lines:
            if line.startswith("PORT=") and not line.startswith("PORT_LEGACY="):
                result.append(f"PORT={new_port}"); port_ok = True
            elif line.startswith("PORT_LEGACY="):
                result.append(f"PORT_LEGACY={old_port}"); legacy_ok = True
            else:
                result.append(line)
        if not port_ok:   result.append(f"PORT={new_port}")
        if not legacy_ok: result.append(f"PORT_LEGACY={old_port}")
        content = "\n".join(result) + "\n"
        # MEDIUM-4: Atomic write via temp file to avoid partial writes
        tmp = _ENV_FILE.with_suffix(".env.tmp")
        tmp.write_text(content)
        os.replace(tmp, _ENV_FILE)
    except Exception as exc:
        import sys
        print(f"[patchpilot] Warning: could not update .env: {exc}", file=sys.stderr)


def _update_env_key(key: str, value: str) -> None:
    """Update or add a KEY=value entry in the systemd EnvironmentFile."""
    try:
        lines = _ENV_FILE.read_text().splitlines() if _ENV_FILE.exists() else []
        found = False
        result = []
        for line in lines:
            if line.startswith(f"{key}="):
                result.append(f"{key}={value}"); found = True
            else:
                result.append(line)
        if not found:
            result.append(f"{key}={value}")
        tmp = _ENV_FILE.with_suffix(".env.tmp")
        tmp.write_text("\n".join(result) + "\n")
        os.replace(tmp, _ENV_FILE)
    except Exception as exc:
        import sys
        print(f"[patchpilot] Warning: could not update .env {key}: {exc}", file=sys.stderr)


def _schedule_restart(delay: float = 1.5) -> None:
    """Restart PatchPilot after *delay* s (systemd by default, process exit in containers)."""
    def _do() -> None:
        time.sleep(delay)
        try:
            if os.environ.get("PATCHPILOT_RESTART_MODE", "systemd") == "process":
                os._exit(0)
            subprocess.run(["sudo", "systemctl", "restart", "patchpilot"], check=False)
        except Exception as exc:
            import sys
            print(f"[patchpilot] Warning: restart failed: {exc}", file=sys.stderr)
    threading.Thread(target=_do, daemon=True).start()


@app.on_event("startup")
def startup():
    init_db()
    with get_db_ctx() as conn:
        try:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'"
            ).fetchone()
            sql = (row["sql"] or "") if row else ""
            if "created     TEXT DEFAULT (datetime('now'))" in sql or "created TEXT DEFAULT (datetime('now'))" in sql:
                conn.execute(
                    "UPDATE jobs SET created=datetime(created,'localtime') "
                    "WHERE created IS NOT NULL AND started IS NULL AND finished IS NULL"
                )
                print("[startup] Adjusted pending job timestamps from UTC schema default to localtime")
        except Exception as exc:
            print(f"[startup] Warning: jobs timestamp schema check failed: {exc}")
    with get_db_ctx() as conn:
        # Mark stale running jobs as failed (stuck for >15 min)
        stale_running = conn.execute(
            "UPDATE jobs SET status='failed', output=COALESCE(output,'') || '\n[server] Marked as failed: stuck in running state', "
            "finished=datetime('now','localtime') "
            "WHERE status='running' AND started IS NOT NULL "
            "AND (julianday('now','localtime') - julianday(started)) * 86400 > 900"
        ).rowcount
        stale_pending = conn.execute(
            "UPDATE jobs SET status='failed', output=COALESCE(output,'') || '\n[server] Marked as failed: expired in pending state', "
            "finished=datetime('now','localtime') "
            "WHERE status='pending' AND created IS NOT NULL "
            "AND (julianday('now','localtime') - julianday(created)) * 86400 > 1800"
        ).rowcount
        if stale_running:
            print(f"[startup] Cleaned up {stale_running} stale running job(s)")
        if stale_pending:
            print(f"[startup] Cleaned up {stale_pending} stale pending job(s)")
    scheduler.start()
    _load_schedules()
    register_system_jobs()
    # If the port was changed, forward the old port → new port so agents reconnect
    if _LEGACY_PORT and _LEGACY_PORT != _SERVER_PORT:
        _start_legacy_forwarder(_LEGACY_PORT, _SERVER_PORT)


@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown(wait=False)


def _load_schedules():
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT id, name, cron, action, target FROM schedules WHERE enabled=1"
        ).fetchall()
    for row in rows:
        schedule_job(row["id"], row["name"], row["cron"], row["action"], row["target"])


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------
def _hash_token(token: str) -> str:
    """CRIT-5: One-way hash tokens before DB storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def _redact_agent_record(row: dict) -> dict:
    """Remove sensitive fields before returning agent data to the UI."""
    row.pop("token", None)
    return row


def verify_agent(agent_id: str, x_token: str):
    """Verify agent token against the stored SHA-256 hash."""
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT token FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()

    # Always compute against a plausible hash so response time doesn't leak
    # whether agent_id exists.
    dummy = _hash_token(secrets.token_hex(32))
    stored = row["token"] if row else dummy
    submitted_hash = _hash_token(x_token)
    hash_ok = hmac.compare_digest(submitted_hash, stored)

    if not row or not hash_ok:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---------------------------------------------------------------------------
# Agent ID rename aliases (old_id → new_id). Persisted in DB.
# ---------------------------------------------------------------------------
def _resolve_alias(agent_id: str) -> str:
    """If agent_id was renamed, return the new ID. Follows chains (A→B→C) with cycle protection."""
    seen = set()
    current = agent_id
    with get_db_ctx() as conn:
        for _ in range(5):  # max 5 hops
            if current in seen:
                break
            seen.add(current)
            row = conn.execute("SELECT new_id FROM rename_aliases WHERE old_id=?", (current,)).fetchone()
            if not row:
                break
            current = row["new_id"]
    return current


def _store_alias(old_id: str, new_id: str):
    """Store a rename alias in the DB."""
    with get_db_ctx() as conn:
        conn.execute("INSERT OR REPLACE INTO rename_aliases (old_id, new_id) VALUES (?,?)", (old_id, new_id))


def _clear_alias(old_id: str = "", new_id: str = ""):
    """Remove alias once the agent has acknowledged its new ID."""
    with get_db_ctx() as conn:
        if old_id:
            conn.execute("DELETE FROM rename_aliases WHERE old_id=?", (old_id,))
        if new_id:
            conn.execute("DELETE FROM rename_aliases WHERE new_id=?", (new_id,))


# ===========================================================================
# AGENT API
# ===========================================================================

@app.post("/api/agents/register")
async def register_agent(request: Request):
    _check_rate_limit(request)
    data = await request.json()
    agent_id = data.get("id") or secrets.token_hex(8)
    _validate_agent_id(agent_id)
    # SEC M-3: Single transaction to avoid TOCTOU race on agent existence check
    fields = _sanitize_agent_fields(data)   # MED-6: cap free-form fields
    fields["package_manager"] = _infer_package_manager(fields)
    fields["agent_type"] = _infer_agent_type(fields)
    fields["capabilities"] = _normalize_capabilities(fields)
    token = secrets.token_hex(32)
    with get_db_ctx() as conn:
        existing = conn.execute("SELECT token FROM agents WHERE id=?", (agent_id,)).fetchone()
        if existing:
            x_token = request.headers.get("x-token", "")
            reg_key = request.headers.get("x-register-key", "") or data.get("register_key", "")
            if x_token:
                submitted_hash = _hash_token(x_token)
                stored = existing["token"]
                hash_ok = hmac.compare_digest(submitted_hash, stored)
                if not hash_ok:
                    raise HTTPException(status_code=403, detail="Invalid token for re-registration")
            elif reg_key:
                # Allow re-registration with a valid register key (fresh install scenario)
                _verify_register_key(reg_key)
            else:
                raise HTTPException(status_code=403, detail="Re-registration requires current token or valid register key")
        else:
            # NEW agent: require valid rotating register key
            reg_key = request.headers.get("x-register-key", "") or data.get("register_key", "")
            _verify_register_key(reg_key)
        conn.execute(
            """INSERT INTO agents (id, hostname, ip, os_pretty, kernel, arch, package_manager, agent_version, agent_type, capabilities, token)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   hostname = excluded.hostname,
                   ip       = excluded.ip,
                   os_pretty= excluded.os_pretty,
                   kernel   = excluded.kernel,
                   arch     = excluded.arch,
                   package_manager = excluded.package_manager,
                   agent_version = excluded.agent_version,
                   agent_type = excluded.agent_type,
                   capabilities = excluded.capabilities,
                   token    = excluded.token""",
            (
                agent_id,
                fields["hostname"] or "unknown",
                fields["ip"],
                fields["os_pretty"],
                fields["kernel"],
                fields["arch"],
                fields["package_manager"],
                fields["agent_version"] or "",
                fields["agent_type"],
                fields["capabilities"],
                _hash_token(token),   # CRIT-5: store hash, return plaintext once
            ),
        )
    return {"agent_id": agent_id, "token": token}


@app.post("/api/agents/{agent_id}/heartbeat")
async def heartbeat(agent_id: str, request: Request, x_token: str = Header(...)):
    # Check if this agent was renamed — resolve alias and verify under new ID
    resolved_id = _resolve_alias(agent_id)
    if resolved_id != agent_id:
        verify_agent(resolved_id, x_token)
        agent_id = resolved_id  # use new ID for all DB operations below
    else:
        verify_agent(agent_id, x_token)
        # Agent is using its current ID directly — clean up any stale alias pointing to it
        _clear_alias(new_id=agent_id)  # no-op if no alias exists
    _check_agent_rate_limit(request)

    # PERFORMANCE: Heartbeat throttling — if the same agent checks in more
    # often than _HEARTBEAT_MIN_INTERVAL seconds we skip the DB write entirely.
    # This protects the Raspberry Pi from agents mis-configured with very short
    # intervals. The agent still gets "ok" so it doesn't error-loop.
    now_mono = time.monotonic()
    last = _last_heartbeat.get(agent_id, 0.0)
    if now_mono - last < _HEARTBEAT_MIN_INTERVAL:
        # Agent canonical URL always points to the agent port (HTTP)
        return {"status": "ok", "canonical_port": str(_AGENT_PORT), "canonical_url": f"{_AGENT_SCHEME}://{_get_internal_ip()}:{_AGENT_PORT}", "canonical_id": agent_id}
    _last_heartbeat[agent_id] = now_mono

    # Heartbeat accepted — also invalidate dashboard + agent caches so the
    # next UI poll sees fresh data rather than a stale snapshot.
    _cache_invalidate("dashboard", f"agent:{agent_id}")

    data = await request.json()
    packages = data.get("packages", [])
    # HIGH-4: Cap packages array to prevent oversized payloads
    if len(packages) > 2000:
        packages = packages[:2000]
    fields = _sanitize_agent_fields(data)   # MED-6: cap free-form fields
    fields["package_manager"] = _infer_package_manager(fields)
    fields["agent_type"] = _infer_agent_type(fields)
    fields["capabilities"] = _normalize_capabilities(fields)
    # MEDIUM-6: Validate uptime_seconds type and range
    raw_uptime = data.get("uptime_seconds")
    uptime_seconds = None
    if raw_uptime is not None:
        try:
            uptime_seconds = int(raw_uptime)
            if not (0 <= uptime_seconds <= 2147483647):
                uptime_seconds = None
        except (ValueError, TypeError):
            uptime_seconds = None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config_review_required = 1 if data.get("config_review_required") else 0
    config_review_note = str(data.get("config_review_note", ""))[:4000] if config_review_required else ""
    # Detect connection protocol from the request
    protocol = "https" if request.url.scheme == "https" else "http"
    with get_db_ctx() as conn:
        conn.execute(
            """UPDATE agents SET
                hostname=?, ip=?, os_pretty=?, kernel=?, arch=?, package_manager=?, agent_version=?, agent_type=?, capabilities=?,
                reboot_required=?, pending_count=?, last_seen=?, uptime_seconds=?,
                protocol=?, config_review_required=?, config_review_note=?
               WHERE id=?""",
            (
                fields["hostname"],
                fields["ip"],
                fields["os_pretty"],
                fields["kernel"],
                fields["arch"],
                fields["package_manager"],
                fields["agent_version"] or "",
                fields["agent_type"],
                fields["capabilities"],
                1 if data.get("reboot_required") else 0,
                len(packages),
                now,
                uptime_seconds,
                protocol,
                config_review_required,
                config_review_note,
                agent_id,
            ),
        )
        conn.execute("DELETE FROM packages WHERE agent_id=?", (agent_id,))
        # SEC M-1: Truncate package fields to prevent storage bloat from compromised agents
        conn.executemany(
            "INSERT OR REPLACE INTO packages (agent_id, name, current_ver, new_ver) VALUES (?,?,?,?)",
            [(agent_id,
              str(p.get("name", ""))[:256],
              str(p.get("current", ""))[:128] if p.get("current") else None,
              str(p.get("new", ""))[:128] if p.get("new") else None,
              ) for p in packages],
        )
    # Agent canonical URL always points to the agent port (HTTP, no SSL)
    return {"status": "ok", "canonical_port": str(_AGENT_PORT), "canonical_url": f"{_AGENT_SCHEME}://{_get_internal_ip()}:{_AGENT_PORT}", "canonical_id": agent_id}


@app.get("/api/agents/{agent_id}/jobs")
def get_jobs(agent_id: str, x_token: str = Header(...)):
    # Resolve rename alias so old agents can still poll jobs under new ID
    agent_id = _resolve_alias(agent_id)
    verify_agent(agent_id, x_token)
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT id, type, params FROM jobs WHERE agent_id=? AND status='pending' ORDER BY id",
            (agent_id,),
        ).fetchall()
        if rows:
            ids = [r["id"] for r in rows]
            # SECURITY: Use only parameterized placeholders — never f-string
            # interpolation — in SQL statements.  The placeholder list itself
            # is built from the length of the id list, not from user input,
            # so this is safe; but we also add an explicit integer cast to be
            # absolutely sure no non-integer value can sneak in.
            placeholders = ",".join("?" * len(ids))
            safe_ids = [int(i) for i in ids]  # enforce integer type
            conn.execute(
                f"UPDATE jobs SET status='running', started=datetime('now','localtime') WHERE id IN ({placeholders})",  # noqa: S608
                safe_ids,
            )
    # If SSL is active and there's an update_agent job, inline the agent code
    # so the agent doesn't need to make a separate HTTPS download (bootstrap problem)
    ssl_active = bool(os.environ.get("SSL_CERTFILE"))
    agent_py = Path(__file__).parent.parent / "agent" / "agent.py"

    result = []
    for r in rows:
        job = {"id": r["id"], "type": r["type"], "params": json.loads(r["params"] or "{}")}
        if r["type"] == "update_agent" and ssl_active and agent_py.exists():
            import base64 as _b64
            code = agent_py.read_bytes()
            job["params"]["inline_code"] = _b64.b64encode(code).decode()
            job["params"]["inline_sha256"] = hashlib.sha256(code).hexdigest()
        result.append(job)
    return result


@app.post("/api/agents/{agent_id}/jobs/{job_id}/result")
async def job_result(
    agent_id: str, job_id: int, request: Request, x_token: str = Header(...)
):
    agent_id = _resolve_alias(agent_id)
    verify_agent(agent_id, x_token)
    data = await request.json()
    # M-4: Cap output at 64 KB to prevent runaway storage on the Pi
    output = (data.get("output") or "")[:65536]
    # CRIT-3: Allowlist job status so agent-reported values can't poison Prometheus metrics
    _raw_status = data.get("status", "done")
    status = _raw_status if _raw_status in {"done", "failed"} else "done"
    with get_db_ctx() as conn:
        conn.execute(
            "UPDATE jobs SET status=?, output=?, finished=datetime('now','localtime') WHERE id=? AND agent_id=?",
            (status, output, job_id, agent_id),
        )
        agent_row = conn.execute(
            "SELECT hostname FROM agents WHERE id=?", (agent_id,)
        ).fetchone()
        job_row = conn.execute(
            "SELECT type, params FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        # Chain: if update_agent succeeded and has a chain param, create the follow-up job
        if job_row and job_row["type"] == "update_agent" and status == "done":
            try:
                params = json.loads(job_row["params"] or "{}")
                chain_type = params.get("chain")
                if chain_type and chain_type in ALLOWED_JOB_TYPES:
                    # Forward batch id to chained job for tracking
                    chain_params = {}
                    if params.get("batch"):
                        chain_params["batch"] = params["batch"]
                    conn.execute(
                        "INSERT INTO jobs (agent_id, type, params, created) VALUES (?, ?, ?, datetime('now','localtime'))",
                        (agent_id, chain_type, json.dumps(chain_params)),
                    )
            except (json.JSONDecodeError, AttributeError):
                pass
    # Notify via Telegram on job completion
    if agent_row and job_row:
        hostname = agent_row["hostname"] or agent_id
        jtype = (job_row["type"] or "job").upper()
        if status == "failed":
            notification_manager.notify_job_failed(
                {"hostname": hostname, "id": agent_id},
                {"id": job_id, "type": job_row["type"], "output": output},
            )
        else:
            notification_manager.notify_job_success(
                {"hostname": hostname, "id": agent_id},
                {"id": job_id, "type": job_row["type"], "output": output},
            )
    return {"status": "ok"}


@app.post("/api/agents/{agent_id}/jobs/{job_id}/cancel", dependencies=[Depends(require_role("admin","user"))])
def cancel_job(agent_id: str, job_id: int):
    """Cancel a pending or running job."""
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT status FROM jobs WHERE id=? AND agent_id=?", (job_id, agent_id)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        if row["status"] not in ("pending", "running"):
            raise HTTPException(status_code=422, detail=f"Cannot cancel job in '{row['status']}' state")
        conn.execute(
            "UPDATE jobs SET status='failed', output=COALESCE(output,'') || '\n[cancelled by user]', "
            "finished=datetime('now','localtime') WHERE id=? AND agent_id=?",
            (job_id, agent_id),
        )
    return {"status": "ok"}


@app.post("/api/agents/{agent_id}/jobs/cancel-pending", dependencies=[Depends(require_role("admin","user"))])
def cancel_pending_jobs(agent_id: str):
    """Cancel all pending jobs for an agent."""
    with get_db_ctx() as conn:
        result = conn.execute(
            "UPDATE jobs SET status='failed', output=COALESCE(output,'') || '\n[cancelled by user]', "
            "finished=datetime('now','localtime') WHERE agent_id=? AND status='pending'",
            (agent_id,),
        )
        count = result.rowcount
    _cache_invalidate("dashboard")
    return {"status": "ok", "cancelled": count}


# ===========================================================================
# WEB API (for React frontend)
# ===========================================================================

@app.get("/api/dashboard", dependencies=[Depends(require_role("admin","user","readonly"))])
def api_dashboard():
    # PERFORMANCE: Cache dashboard response for 10 s to avoid hammering SQLite
    # on every frontend poll.  Invalidated by heartbeat and job-creation writes.
    cached = _cache_get("dashboard")
    if cached is not None:
        return cached

    with get_db_ctx() as conn:
        agents = conn.execute(
            """SELECT *,
               (julianday('now','localtime') - julianday(last_seen)) * 86400 as seconds_ago
               FROM agents ORDER BY hostname"""
        ).fetchall()
        # Last finished job per agent (type + status)
        last_jobs = conn.execute(
            """SELECT j.agent_id, j.type, j.status, j.finished
               FROM jobs j
               INNER JOIN (
                   SELECT agent_id, MAX(id) as max_id
                   FROM jobs
                   GROUP BY agent_id
               ) latest ON j.id = latest.max_id"""
        ).fetchall()
    last_job_map = {r["agent_id"]: dict(r) for r in last_jobs}
    result = []
    for a in agents:
        row = _redact_agent_record(dict(a))
        lj = last_job_map.get(row["id"])
        if lj:
            row["last_job_type"] = lj["type"]
            row["last_job_status"] = lj["status"]
            row["last_job_finished"] = lj["finished"]
        result.append(row)
    online = sum(1 for a in result if (a.get("seconds_ago") or 9999) < 120)
    reboot_needed = sum(1 for a in result if a.get("reboot_required"))
    total_pending = sum(a.get("pending_count") or 0 for a in result)
    payload = {
        "agents": result,
        "stats": {
            "online": online,
            "total": len(result),
            "reboot_needed": reboot_needed,
            "total_pending": total_pending,
        },
    }
    _cache_set("dashboard", payload, _CACHE_TTL_DASHBOARD)
    return payload


@app.post("/api/register-key", dependencies=[Depends(require_role("admin"))])
def api_register_key_generate():
    """Generate a fresh registration key (valid 5 min). Old key is replaced."""
    key, remaining = _generate_register_key()
    return {"key": key, "expires_in": int(remaining)}

@app.get("/api/register-key", dependencies=[Depends(require_role("admin"))])
def api_register_key_status():
    """Check if a register key is currently active.
    Note: key is hashed in DB — we never return the hash to the UI."""
    key, remaining = _get_active_register_key()
    if key is None:
        return {"active": False, "key": None, "expires_in": 0}
    return {"active": True, "key": None, "expires_in": int(remaining)}


@app.get("/api/deploy/bootstrap", dependencies=[Depends(require_role("admin"))])
def api_deploy_bootstrap():
    """Return authenticated bootstrap material for the Deploy page."""
    cert = _SSL_DIR / "cert.pem"
    ca_pem_b64 = ""
    if cert.exists():
        ca_pem_b64 = base64.b64encode(cert.read_bytes()).decode()
    return {
        "ca_pem_b64": ca_pem_b64,
    }


@app.get("/api/ping")
def api_ping():
    """Unauthenticated liveness check — used by the UI status indicator."""
    return {"status": "ok", "utc": datetime.now(timezone.utc).isoformat()}


@app.get("/api/server-time")
def api_server_time():
    """Return current server local time — cron expressions are evaluated
    in the server's timezone (Europe/Berlin)."""
    import zoneinfo
    tz = zoneinfo.ZoneInfo("Europe/Berlin")
    now = datetime.now(tz)
    tz_abbr = now.strftime("%Z")  # CET or CEST
    return {
        "local": now.strftime("%Y-%m-%d %H:%M:%S"),
        "tz": tz_abbr,
        "iso": now.isoformat(),
    }


@app.get("/api/agents/{agent_id}", dependencies=[Depends(require_role("admin","user","readonly"))])
def api_agent(agent_id: str):
    # PERFORMANCE: Cache per-agent detail page for 5 s.  This endpoint joins
    # three tables (agents + packages + jobs) — caching saves the most work.
    # Invalidated on heartbeat (packages change) and job creation.
    cache_key = f"agent:{agent_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    with get_db_ctx() as conn:
        agent = conn.execute(
            """SELECT *,
               (julianday('now','localtime') - julianday(last_seen)) * 86400 as seconds_ago
               FROM agents WHERE id=?""",
            (agent_id,),
        ).fetchone()
        if not agent:
            raise HTTPException(status_code=404)
        packages = conn.execute(
            "SELECT * FROM packages WHERE agent_id=? ORDER BY name", (agent_id,)
        ).fetchall()
        jobs = conn.execute(
            "SELECT * FROM jobs WHERE agent_id=? ORDER BY id DESC LIMIT 50", (agent_id,)
        ).fetchall()
    payload = {
        "agent": _redact_agent_record(dict(agent)),
        "packages": [dict(p) for p in packages],
        "jobs": [dict(j) for j in jobs],
    }
    _cache_set(cache_key, payload, _CACHE_TTL_AGENT)
    return payload


@app.post("/api/agents/{agent_id}/jobs", dependencies=[Depends(require_role("admin","user"))])
async def create_job(agent_id: str, request: Request):
    data = await request.json()
    job_type = data.get("type")
    # C-3: Allowlist job types to prevent arbitrary command injection
    if job_type not in ALLOWED_JOB_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid job type. Allowed: {sorted(ALLOWED_JOB_TYPES)}")
    params = data.get("params", {})
    with get_db_ctx() as conn:
        agent = conn.execute("SELECT id, agent_type, capabilities FROM agents WHERE id=?", (agent_id,)).fetchone()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        capabilities = set(filter(None, str(agent["capabilities"] or "").split(",")))
        if job_type.startswith("ha_"):
            if agent["agent_type"] != "haos":
                raise HTTPException(status_code=422, detail="HA jobs are only available for Home Assistant OS agents")
            required = {
                "ha_backup": "ha_backup",
                "ha_core_update": "ha_core_update",
                "ha_supervisor_update": "ha_supervisor_update",
                "ha_os_update": "ha_os_update",
                "ha_addon_update": "ha_addon_update",
                "ha_addons_update": "ha_addons_update",
            }.get(job_type)
            if job_type == "ha_backup_update" and not {"ha_backup", "ha_core_update"}.issubset(capabilities):
                raise HTTPException(status_code=422, detail="Agent does not support ha_backup_update")
            if required and required not in capabilities:
                raise HTTPException(status_code=422, detail=f"Agent does not support {job_type}")
        conn.execute(
            "INSERT INTO jobs (agent_id, type, params, created) VALUES (?, ?, ?, datetime('now','localtime'))",
            (agent_id, job_type, json.dumps(params)),
        )
    # PERFORMANCE: Invalidate caches so the new job appears immediately in the UI.
    _cache_invalidate("dashboard", f"agent:{agent_id}")
    return {"status": "queued"}


@app.post("/api/agents/{agent_id}/config-review/ack", dependencies=[Depends(require_role("admin","user"))])
def api_ack_config_review(agent_id: str):
    with get_db_ctx() as conn:
        agent = conn.execute("SELECT id FROM agents WHERE id=?", (agent_id,)).fetchone()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        conn.execute(
            "UPDATE agents SET config_review_required=0, config_review_note='' WHERE id=?",
            (agent_id,),
        )
        conn.execute(
            "INSERT INTO jobs (agent_id, type, params, created) VALUES (?, ?, ?, datetime('now','localtime'))",
            (agent_id, "ack_config_review", "{}"),
        )
    _cache_invalidate("dashboard", f"agent:{agent_id}")
    return {"status": "queued"}


@app.delete("/api/agents/{agent_id}", dependencies=[Depends(require_role("admin"))])
def delete_agent(agent_id: str):
    with get_db_ctx() as conn:
        conn.execute("DELETE FROM agents WHERE id=?", (agent_id,))
    # L-2: Clear stale in-memory state so the ID can be cleanly re-registered
    _last_heartbeat.pop(agent_id, None)
    from scheduler import _offline_notified
    _offline_notified.discard(agent_id)
    _cache_invalidate("dashboard", f"agent:{agent_id}")
    return {"status": "deleted"}


@app.patch("/api/agents/{agent_id}/rename", dependencies=[Depends(require_role("admin"))])
async def rename_agent(agent_id: str, request: Request):
    """Rename an agent's ID. Updates all references (jobs, packages, schedules)."""
    data = await request.json()
    new_id = (data.get("new_id") or "").strip()
    _validate_agent_id(new_id)
    if new_id == agent_id:
        return {"status": "unchanged"}
    with get_db_ctx() as conn:
        # Check new ID doesn't already exist
        existing = conn.execute("SELECT id FROM agents WHERE id=?", (new_id,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail=f"Agent ID '{new_id}' already exists")
        # Check old ID exists
        old = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        if not old:
            raise HTTPException(status_code=404, detail="Agent not found")
        # Insert new agent row, migrate FK children, then delete old row.
        # This avoids PRAGMA foreign_keys=OFF (which has no effect inside transactions).
        cols = [k for k in dict(old).keys() if k != "id"]
        placeholders = ", ".join(f"{c}" for c in cols)
        qs = ", ".join("?" for _ in cols)
        vals = [dict(old)[c] for c in cols]
        conn.execute(f"INSERT INTO agents (id, {placeholders}) VALUES (?, {qs})", [new_id] + vals)
        conn.execute("UPDATE jobs SET agent_id=? WHERE agent_id=?", (new_id, agent_id))
        conn.execute("UPDATE packages SET agent_id=? WHERE agent_id=?", (new_id, agent_id))
        conn.execute("DELETE FROM agents WHERE id=?", (agent_id,))
        # Update schedule targets that reference this agent
        schedules = conn.execute("SELECT id, target FROM schedules").fetchall()
        for sched in schedules:
            targets = [t.strip() for t in sched["target"].split(",")]
            if agent_id in targets:
                new_targets = [new_id if t == agent_id else t for t in targets]
                conn.execute("UPDATE schedules SET target=? WHERE id=?",
                             (",".join(new_targets), sched["id"]))
    # Update in-memory state
    _last_heartbeat[new_id] = _last_heartbeat.pop(agent_id, 0)
    # Update existing alias chains: anything pointing to old_id now points to new_id
    with get_db_ctx() as conn2:
        conn2.execute("UPDATE rename_aliases SET new_id=? WHERE new_id=?", (new_id, agent_id))
    _store_alias(agent_id, new_id)  # persist so heartbeats from old ID get routed
    from scheduler import _offline_notified
    if agent_id in _offline_notified:
        _offline_notified.discard(agent_id)
        _offline_notified.add(new_id)
    _cache_invalidate("dashboard", f"agent:{agent_id}", f"agent:{new_id}")
    return {"status": "renamed", "old_id": agent_id, "new_id": new_id}


@app.patch("/api/agents/{agent_id}/tags", dependencies=[Depends(require_role("admin","user"))])
async def set_agent_tags(agent_id: str, request: Request):
    data = await request.json()
    # Accept a comma-separated string; strip whitespace around each tag.
    raw_tags = data.get("tags", "")
    # Normalise: split on commas, strip, drop empties, re-join.
    tags = ",".join(t.strip() for t in raw_tags.split(",") if t.strip())
    # MEDIUM-5: Validate individual tags and overall length
    for tag in tags.split(","):
        if tag and not _TAG_RE.match(tag):
            raise HTTPException(status_code=422, detail=f"Invalid tag: {tag!r}. Use a-z A-Z 0-9 . _ -")
    if len(tags) > 512:
        raise HTTPException(status_code=422, detail="Tags string exceeds 512 character limit")
    with get_db_ctx() as conn:
        row = conn.execute("SELECT id FROM agents WHERE id=?", (agent_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")
        conn.execute("UPDATE agents SET tags=? WHERE id=?", (tags, agent_id))
    _cache_invalidate("dashboard", f"agent:{agent_id}")
    return {"status": "ok", "tags": tags}


@app.get("/api/schedules", dependencies=[Depends(require_role("admin","user"))])
def api_schedules():
    with get_db_ctx() as conn:
        schedules = conn.execute("SELECT * FROM schedules ORDER BY id").fetchall()
        agents = conn.execute(
            "SELECT id, hostname FROM agents ORDER BY hostname"
        ).fetchall()
    schedule_list = []
    for s in schedules:
        row = dict(s)
        job = scheduler.get_job(str(row["id"]))
        if job and job.next_run_time:
            row["next_run"] = job.next_run_time.isoformat()
        schedule_list.append(row)
    return {
        "schedules": schedule_list,
        "agents": [dict(a) for a in agents],
    }


@app.post("/api/schedules", dependencies=[Depends(require_role("admin"))])
async def create_schedule(request: Request):
    data = await request.json()
    name   = str(data.get("name", ""))[:128]
    cron   = str(data.get("cron", ""))
    action = str(data.get("action", ""))
    target = str(data.get("target", ""))
    # M-7 / C-3: Validate all schedule fields before storing
    if not name:
        raise HTTPException(status_code=422, detail="Schedule name is required")
    if action not in ALLOWED_JOB_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid action. Allowed: {sorted(ALLOWED_JOB_TYPES)}")
    _validate_cron(cron)
    # target must be "all" or comma-separated valid agent IDs
    _validate_schedule_target(target)
    with get_db_ctx() as conn:
        conn.execute(
            "INSERT INTO schedules (name, cron, action, target) VALUES (?,?,?,?)",
            (name, cron, action, target),
        )
        row = conn.execute("SELECT last_insert_rowid() as id").fetchone()
        schedule_job(row["id"], name, cron, action, target)
    return {"status": "created"}


@app.patch("/api/schedules/{sid}", dependencies=[Depends(require_role("admin"))])
async def toggle_schedule(sid: int, request: Request):
    data = await request.json()
    enabled = 1 if data.get("enabled") else 0
    with get_db_ctx() as conn:
        row = conn.execute("SELECT id FROM schedules WHERE id=?", (sid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Schedule not found")
        conn.execute("UPDATE schedules SET enabled=? WHERE id=?", (enabled, sid))
    return {"status": "updated"}


@app.put("/api/schedules/{sid}", dependencies=[Depends(require_role("admin"))])
async def update_schedule(sid: int, request: Request):
    data = await request.json()
    name   = str(data.get("name", ""))[:128]
    cron   = str(data.get("cron", ""))
    action = str(data.get("action", ""))
    target = str(data.get("target", ""))
    if not name:
        raise HTTPException(status_code=422, detail="Schedule name is required")
    if action not in ALLOWED_JOB_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid action. Allowed: {sorted(ALLOWED_JOB_TYPES)}")
    _validate_cron(cron)
    _validate_schedule_target(target)
    with get_db_ctx() as conn:
        row = conn.execute("SELECT id FROM schedules WHERE id=?", (sid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Schedule not found")
        conn.execute(
            "UPDATE schedules SET name=?, cron=?, action=?, target=? WHERE id=?",
            (name, cron, action, target, sid),
        )
    # Re-register with updated cron
    schedule_job(sid, name, cron, action, target)
    return {"status": "updated"}


@app.post("/api/schedules/{sid}/run", dependencies=[Depends(require_role("admin","user"))])
def run_schedule_now(sid: int):
    """Immediately trigger a schedule's job, regardless of its cron time."""
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT action, target FROM schedules WHERE id=?", (sid,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    from scheduler import _run_scheduled_job
    _run_scheduled_job(sid, row["action"], row["target"])
    return {"status": "triggered"}


@app.delete("/api/schedules/{sid}", dependencies=[Depends(require_role("admin"))])
def delete_schedule(sid: int):
    with get_db_ctx() as conn:
        conn.execute("DELETE FROM schedules WHERE id=?", (sid,))
    try:
        scheduler.remove_job(str(sid))
    except Exception:
        pass
    return {"status": "deleted"}


# ===========================================================================
# SETTINGS API
# ===========================================================================

# Keys that contain sensitive data — masked in GET, encrypted in DB
_SENSITIVE_KEYS = {"smtp_password", "telegram_token"}

try:
    from crypto import encrypt as _encrypt_secret, decrypt as _decrypt_secret
except ImportError:
    # Fallback if cryptography not installed — plaintext
    _encrypt_secret = lambda v: v  # noqa: E731
    _decrypt_secret = lambda v: v  # noqa: E731

# LOW-4: Explicit allowlist — reject unknown keys to prevent mass assignment
_SETTINGS_ALLOWED_KEYS = {
    "telegram_token", "telegram_chat_id", "telegram_enabled",
    "telegram_notify_offline", "telegram_notify_patches", "telegram_notify_failures", "telegram_notify_success",
    "email_enabled",
    "smtp_host", "smtp_port", "smtp_security", "smtp_user", "smtp_password", "smtp_to",
    "notify_offline", "notify_offline_minutes", "notify_patches", "notify_failures",
    "server_port", "agent_port", "agent_ssl",
    "ui_audio_enabled", "ui_audio_volume", "ui_login_animation_enabled", "ui_login_background_animation_enabled", "ui_login_background_opacity",
}

_SSL_DIR = Path(os.environ.get("PATCHPILOT_SSL_DIR", str(Path(__file__).parent.parent / "ssl")))


def _get_internal_ip() -> str:
    """Best-effort detection of the server's LAN IP address."""
    try:
        # Connect to a public DNS — doesn't actually send packets, just reveals the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@app.get("/api/settings", dependencies=[Depends(require_role("admin","user","readonly"))])
def api_get_settings():
    """Return settings.  Sensitive values are replaced with '***'. Only saveable keys are returned."""
    with get_db_ctx() as conn:
        rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
    result = {}
    for row in rows:
        k, v = row["key"], row["value"]
        if k not in _SETTINGS_ALLOWED_KEYS:
            continue  # Don't expose internal keys (register_key, etc.)
        result[k] = "***" if (k in _SENSITIVE_KEYS and v) else v
    # Provide computed URLs for the Deploy page
    _scheme = "https" if os.environ.get("SSL_CERTFILE") else "http"
    _ip = _get_internal_ip()
    result["internal_url"] = f"{_scheme}://{_ip}:{_SERVER_PORT}"
    result["agent_url"] = f"{_AGENT_SCHEME}://{_ip}:{_AGENT_PORT}"
    result["ssl_enabled"] = bool(os.environ.get("SSL_CERTFILE"))
    return result


@app.post("/api/settings", dependencies=[Depends(require_role("admin"))])
async def api_save_settings(request: Request):
    """Persist settings.  Values equal to '***' are kept unchanged (masked)."""
    data = await request.json()
    # H-5: Validate security-sensitive fields before persisting
    # LOW-4: reject unknown keys
    unknown = set(data.keys()) - _SETTINGS_ALLOWED_KEYS
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown settings key(s): {', '.join(sorted(unknown))}")
    tg_token = data.get("telegram_token", "")
    if tg_token and tg_token != "***" and not _TG_TOKEN_RE.match(tg_token):
        raise HTTPException(status_code=422, detail="Invalid Telegram token format")
    smtp_host = data.get("smtp_host", "")
    if smtp_host and smtp_host != "***":
        _validate_smtp_host(smtp_host)
    # LOW-5: validate notify_offline_minutes as integer in [1, 10080]
    offline_min = data.get("notify_offline_minutes")
    if offline_min is not None and str(offline_min) != "***":
        try:
            val = int(offline_min)
            if not (1 <= val <= 10080):
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="notify_offline_minutes must be an integer between 1 and 10080")
    ui_audio_volume = data.get("ui_audio_volume")
    if ui_audio_volume is not None and str(ui_audio_volume) != "***":
        try:
            val = int(ui_audio_volume)
            if not (0 <= val <= 100):
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="ui_audio_volume must be an integer between 0 and 100")
    login_background_opacity = data.get("ui_login_background_opacity")
    if login_background_opacity is not None and str(login_background_opacity) != "***":
        try:
            val = int(login_background_opacity)
            if not (0 <= val <= 100):
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="ui_login_background_opacity must be an integer between 0 and 100")
    # Validate server_port as integer in [1, 65535]
    server_port_val = data.get("server_port")
    if server_port_val is not None and str(server_port_val) != "***":
        try:
            port_int = int(server_port_val)
            if not (1 <= port_int <= 65535):
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="server_port must be an integer between 1 and 65535")

    # Read current ports BEFORE saving so we can detect changes
    old_port: str | None = None
    old_agent_port: str | None = None
    old_agent_ssl: str | None = None
    new_port_str = str(server_port_val) if (server_port_val is not None and str(server_port_val) != "***") else None
    with get_db_ctx() as conn:
        if new_port_str:
            row = conn.execute("SELECT value FROM settings WHERE key='server_port'").fetchone()
            old_port = row["value"] if row else "8443"
        row_ap = conn.execute("SELECT value FROM settings WHERE key='agent_port'").fetchone()
        old_agent_port = row_ap["value"] if row_ap else "8050"
        row_as = conn.execute("SELECT value FROM settings WHERE key='agent_ssl'").fetchone()
        old_agent_ssl = row_as["value"] if row_as else "0"

    # Verify Telegram token validity BEFORE saving
    tg_valid = None
    if tg_token and tg_token != "***":
        try:
            import urllib.request as _urlreq
            import json as _json
            req = _urlreq.Request(
                f"https://api.telegram.org/bot{tg_token}/getMe",
                method="GET",
            )
            with _urlreq.urlopen(req, timeout=5) as resp:
                result = _json.loads(resp.read())
                tg_valid = result.get("ok", False)
        except Exception:
            tg_valid = False

    # Save all settings to DB (encrypt sensitive values)
    with get_db_ctx() as conn:
        for key, value in data.items():
            if value == "***":
                continue
            store_val = _encrypt_secret(str(value)) if key in _SENSITIVE_KEYS else str(value)
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, store_val),
            )
    notification_manager.reload()
    from telegram_bot import telegram_bot
    telegram_bot.reload_settings()

    # Port changed → update .env and restart service.
    restart_pending = False
    if new_port_str and old_port and new_port_str != old_port:
        _update_env_port(new_port_str, old_port)
        restart_pending = True

    # Agent port changed → update .env
    new_agent_port = data.get("agent_port")
    if new_agent_port and str(new_agent_port) != "***" and str(new_agent_port) != old_agent_port:
        _update_env_key("AGENT_PORT", str(new_agent_port))
        restart_pending = True

    # Agent SSL toggle
    new_agent_ssl = data.get("agent_ssl")
    if new_agent_ssl is not None and str(new_agent_ssl) != "***" and str(new_agent_ssl) != old_agent_ssl:
        _update_env_key("AGENT_SSL", "1" if str(new_agent_ssl) == "1" else "0")
        restart_pending = True

    if restart_pending:
        _schedule_restart(delay=1.5)

    return {"status": "saved", "restart_pending": restart_pending, "new_port": new_port_str, "telegram_valid": tg_valid}


@app.post("/api/settings/test/{channel}", dependencies=[Depends(require_role("admin"))])
async def api_test_notification(channel: str):
    """Send a test notification via the requested channel (telegram | email)."""
    notification_manager.reload()
    notification_manager._load()
    if channel == "telegram":
        notifier = notification_manager._telegram
        if not notifier:
            raise HTTPException(status_code=400, detail="Telegram not configured")
        ok = notifier.send("*PatchPilot Test*\nTelegram notifications are working correctly.")
    elif channel == "email":
        notifier = notification_manager._email
        if not notifier:
            raise HTTPException(status_code=400, detail="Email not configured")
        ok = notifier.send(
            "PatchPilot Test",
            "This email confirms that SMTP notifications are configured correctly.",
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid notification channel")
    if not ok:
        raise HTTPException(status_code=502, detail="Notification send failed — check server logs")
    return {"status": "sent"}


# ===========================================================================
# SSL MANAGEMENT
# ===========================================================================

def _update_env_ssl(certfile: str, keyfile: str) -> None:
    """Persist SSL_CERTFILE and SSL_KEYFILE in the systemd EnvironmentFile."""
    # SEC: Sanitize newlines to prevent env injection
    certfile = certfile.replace('\n', '').replace('\r', '')
    keyfile = keyfile.replace('\n', '').replace('\r', '')
    try:
        lines = _ENV_FILE.read_text().splitlines() if _ENV_FILE.exists() else []
        cert_ok = key_ok = False
        result = []
        for line in lines:
            if line.startswith("SSL_CERTFILE="):
                if certfile:
                    result.append(f"SSL_CERTFILE={certfile}")
                cert_ok = True
            elif line.startswith("SSL_KEYFILE="):
                if keyfile:
                    result.append(f"SSL_KEYFILE={keyfile}")
                key_ok = True
            else:
                result.append(line)
        if certfile and not cert_ok:
            result.append(f"SSL_CERTFILE={certfile}")
        if keyfile and not key_ok:
            result.append(f"SSL_KEYFILE={keyfile}")
        content = "\n".join(result) + "\n"
        tmp = _ENV_FILE.with_suffix(".env.tmp")
        tmp.write_text(content)
        os.replace(tmp, _ENV_FILE)
    except Exception as exc:
        import sys
        print(f"[patchpilot] Warning: could not update .env SSL: {exc}", file=sys.stderr)


def _get_cert_info(certfile: str) -> dict:
    """Read basic info from a PEM certificate file.  Path must be under _SSL_DIR."""
    try:
        if not Path(certfile).resolve().is_relative_to(_SSL_DIR.resolve()):
            return {"subject": "restricted", "expires": "n/a", "path": certfile}
        import ssl as _ssl
        cert = _ssl.PEM_cert_to_DER_cert(Path(certfile).read_text().split("-----END CERTIFICATE-----")[0] + "-----END CERTIFICATE-----\n")
        # Use subprocess to parse with openssl if available
        result = subprocess.run(
            ["openssl", "x509", "-noout", "-subject", "-enddate", "-inform", "DER"],
            input=cert, capture_output=True, timeout=5,
        )
        info = result.stdout.decode(errors="replace")
        subject = ""
        expires = ""
        for line in info.splitlines():
            if line.startswith("subject="):
                subject = line.split("=", 1)[1].strip()
            elif line.startswith("notAfter="):
                expires = line.split("=", 1)[1].strip()
        return {"subject": subject, "expires": expires, "path": certfile}
    except Exception:
        return {"subject": "unknown", "expires": "unknown", "path": certfile}


@app.post("/api/settings/generate-cert", dependencies=[Depends(require_role("admin"))])
async def api_generate_cert(request: Request):
    """Generate a self-signed SSL certificate and enable HTTPS."""
    try:
        data = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        years = max(1, min(10, int(data.get("years", 3))))
        days = years * 365

        # Use openssl CLI — available on all Debian/Ubuntu systems
        _SSL_DIR.mkdir(parents=True, exist_ok=True)
        cert_path = _SSL_DIR / "cert.pem"
        key_path = _SSL_DIR / "key.pem"
        hostname = socket.gethostname()
        ip = _get_internal_ip()

        result = subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key_path), "-out", str(cert_path),
            "-days", str(days), "-nodes",
            "-subj", f"/CN={hostname}",
            "-addext", f"subjectAltName=DNS:{hostname},IP:{ip}",
        ], capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"openssl failed: {result.stderr[:200]}")

        # Restrict permissions
        cert_path.chmod(0o644)
        key_path.chmod(0o600)

        # Persist cert paths in DB (but do NOT activate SSL or restart)
        with get_db_ctx() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ssl_certfile', ?)", (str(cert_path),))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ssl_keyfile', ?)", (str(key_path),))

        info = _get_cert_info(str(cert_path))
        return {
            "status": "generated",
            "certfile": str(cert_path),
            "keyfile": str(key_path),
            "info": info,
            "restart_pending": False,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/settings/ssl-enable", dependencies=[Depends(require_role("admin"))])
async def api_ssl_enable(request: Request):
    """Enable SSL with custom certificate paths."""
    data = await request.json()
    certfile = str(data.get("certfile", "")).strip()
    keyfile = str(data.get("keyfile", "")).strip()
    if not certfile or not keyfile:
        raise HTTPException(status_code=422, detail="Both certfile and keyfile paths are required")
    # SEC: Restrict cert/key paths to _SSL_DIR to prevent path traversal
    if not Path(certfile).resolve().is_relative_to(_SSL_DIR.resolve()):
        raise HTTPException(status_code=422, detail="Certificate path must be within the SSL directory")
    if not Path(keyfile).resolve().is_relative_to(_SSL_DIR.resolve()):
        raise HTTPException(status_code=422, detail="Key path must be within the SSL directory")
    # Validate files exist
    if not Path(certfile).is_file():
        raise HTTPException(status_code=422, detail=f"Certificate file not found: {certfile}")
    if not Path(keyfile).is_file():
        raise HTTPException(status_code=422, detail=f"Key file not found: {keyfile}")

    _update_env_ssl(certfile, keyfile)
    with get_db_ctx() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ssl_certfile', ?)", (str(certfile),))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ssl_keyfile', ?)", (str(keyfile),))

    _schedule_restart(delay=2.0)
    info = _get_cert_info(certfile)
    return {"status": "enabled", "info": info, "restart_pending": True}


@app.post("/api/settings/ssl-disable", dependencies=[Depends(require_role("admin"))])
def api_ssl_disable():
    """Disable SSL — remove cert/key from .env and restart on plain HTTP."""
    _update_env_ssl("", "")  # removes the lines from .env
    with get_db_ctx() as conn:
        conn.execute("UPDATE settings SET value='' WHERE key='ssl_certfile'")
        conn.execute("UPDATE settings SET value='' WHERE key='ssl_keyfile'")
    _schedule_restart(delay=2.0)
    return {"status": "disabled", "restart_pending": True}


@app.get("/api/settings/ssl-info", dependencies=[Depends(require_role("admin"))])
def api_ssl_info():
    """Return current SSL status and certificate info."""
    certfile = os.environ.get("SSL_CERTFILE", "")
    keyfile = os.environ.get("SSL_KEYFILE", "")
    enabled = bool(certfile and keyfile)
    info = _get_cert_info(certfile) if enabled else None
    # Also check DB for generated-but-not-yet-enabled certs
    if not info:
        with get_db_ctx() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='ssl_certfile'").fetchone()
            if row and row["value"]:
                db_certfile = row["value"]
                info = _get_cert_info(db_certfile)
                if not certfile:
                    certfile = db_certfile
                if not keyfile:
                    kr = conn.execute("SELECT value FROM settings WHERE key='ssl_keyfile'").fetchone()
                    keyfile = kr["value"] if kr else ""
    return {"enabled": enabled, "certfile": certfile, "keyfile": keyfile, "info": info}


# ===========================================================================
# MONITORING ENDPOINTS
# ===========================================================================

@app.get("/api/alerts", dependencies=[Depends(require_role("admin","user","readonly"))])
def api_alerts():
    """Return all VMs that have been offline for more than 5 minutes."""
    with get_db_ctx() as conn:
        rows = conn.execute(
            """SELECT hostname, ip,
               CAST((julianday('now','localtime') - julianday(last_seen)) * 86400 AS INTEGER) as offline_since_seconds
               FROM agents
               WHERE last_seen IS NOT NULL
                 AND (julianday('now','localtime') - julianday(last_seen)) * 86400 > 300
               ORDER BY offline_since_seconds DESC"""
        ).fetchall()
    return [
        {
            "hostname": r["hostname"],
            "ip": r["ip"],
            "offline_since_seconds": r["offline_since_seconds"],
        }
        for r in rows
    ]


@app.get("/api/status/badge", dependencies=[Depends(require_role("admin","user","readonly"))])
def api_status_badge():
    """Return a shields.io-style SVG badge showing X/Y online."""
    with get_db_ctx() as conn:
        agents = conn.execute(
            """SELECT
               COUNT(*) as total,
               SUM(CASE WHEN (julianday('now','localtime') - julianday(last_seen)) * 86400 < 120 THEN 1 ELSE 0 END) as online
               FROM agents"""
        ).fetchone()

    total = agents["total"] or 0
    online = agents["online"] or 0

    if total == 0 or online == 0:
        color = "#e05d44"  # red
    elif online < total:
        color = "#dfb317"  # yellow
    else:
        color = "#4c1"     # green

    label = "patchpilot"
    message = f"{online}/{total} online"
    label_width = 80
    message_width = max(len(message) * 7 + 10, 70)
    total_width = label_width + message_width
    label_x = label_width // 2
    message_x = label_width + message_width // 2

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{total_width}" height="20">
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{message_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="110">
    <text x="{label_x * 10}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{(label_width - 10) * 10}" lengthAdjust="spacing">{label}</text>
    <text x="{label_x * 10}" y="140" transform="scale(.1)" textLength="{(label_width - 10) * 10}" lengthAdjust="spacing">{label}</text>
    <text x="{message_x * 10}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{(message_width - 10) * 10}" lengthAdjust="spacing">{message}</text>
    <text x="{message_x * 10}" y="140" transform="scale(.1)" textLength="{(message_width - 10) * 10}" lengthAdjust="spacing">{message}</text>
  </g>
</svg>"""

    return Response(content=svg, media_type="image/svg+xml")


# ===========================================================================
# Agent download endpoint
# ===========================================================================
AGENT_DIR = Path(__file__).parent.parent / "agent"

@app.get("/agent/agent.py", include_in_schema=False)
def download_agent():
    f = AGENT_DIR / "agent.py"
    if not f.exists():
        raise HTTPException(status_code=404, detail="Agent not found")
    return FileResponse(f, media_type="text/x-python", filename="agent.py")

@app.get("/agent/agent.py.sha256", include_in_schema=False)
def download_agent_hash():
    """M-2: Serve SHA256 so install.sh can verify the download."""
    f = AGENT_DIR / "agent.py"
    if not f.exists():
        raise HTTPException(status_code=404, detail="Agent not found")
    sha256 = hashlib.sha256(f.read_bytes()).hexdigest()
    return Response(content=f"{sha256}  agent.py\n", media_type="text/plain")

@app.get("/agent/install.sh", include_in_schema=False)
def download_install_script():
    f = AGENT_DIR / "install.sh"
    if not f.exists():
        raise HTTPException(status_code=404, detail="Install script not found")
    return FileResponse(f, media_type="text/x-shellscript", filename="install.sh")


@app.get("/agent/ca.pem", include_in_schema=False)
def download_ca_cert():
    """Serve the SSL CA certificate for agent trust."""
    f = _SSL_DIR / "cert.pem"
    if not f.exists():
        raise HTTPException(status_code=404, detail="CA certificate not generated yet")
    return FileResponse(f, media_type="application/x-pem-file", filename="ca.pem")


@app.get("/agent/ca.pem.sha256", include_in_schema=False)
def download_ca_hash():
    f = _SSL_DIR / "cert.pem"
    if not f.exists():
        raise HTTPException(status_code=404, detail="CA certificate not generated yet")
    sha = hashlib.sha256(f.read_bytes()).hexdigest()
    return Response(content=f"{sha}  ca.pem\n", media_type="text/plain")


@app.post("/api/settings/deploy-ssl", dependencies=[Depends(require_role("admin"))])
async def api_deploy_ssl_to_agents(request: Request):
    """Create update_agent + deploy_ssl jobs for agents.

    If retry_batch is provided, only re-deploys to agents that failed in that batch.
    Otherwise deploys to all registered agents.
    Returns a batch_id so the frontend can track exactly this run.
    """
    cert = _SSL_DIR / "cert.pem"
    if not cert.exists():
        raise HTTPException(status_code=400, detail="No certificate generated yet — generate one first")
    import uuid as _uuid
    batch_id = _uuid.uuid4().hex[:12]

    data = {}
    try:
        data = await request.json()
    except Exception:
        pass
    retry_batch = re.sub(r'[^a-fA-F0-9]', '', data.get("retry_batch", ""))  # SEC: sanitize

    with get_db_ctx() as conn:
        if retry_batch:
            # Only retry agents that failed in the previous batch
            batch_filter = f'%"batch": "{retry_batch}"%'
            failed_agents = conn.execute("""
                SELECT DISTINCT j.agent_id, a.hostname FROM jobs j
                JOIN agents a ON a.id = j.agent_id
                WHERE j.status = 'failed' AND j.params LIKE ?
            """, (batch_filter,)).fetchall()
            agents = failed_agents
        else:
            agents = conn.execute("SELECT id AS agent_id, hostname FROM agents").fetchall()

        if not agents:
            raise HTTPException(status_code=422, detail="No agents to deploy to")
        count = 0
        for a in agents:
            aid = a["agent_id"] if "agent_id" in a.keys() else a["id"]
            params = json.dumps({"chain": "deploy_ssl", "batch": batch_id})
            conn.execute(
                'INSERT INTO jobs (agent_id, type, params, created) VALUES (?, \'update_agent\', ?, datetime(\'now\',\'localtime\'))',
                (aid, params),
            )
            count += 1
    _cache_invalidate("dashboard")
    return {"status": "deployed", "agent_count": count, "batch_id": batch_id}


@app.post("/api/agents/update-batch", dependencies=[Depends(require_role("admin"))])
async def api_update_agents_batch(request: Request):
    """Create update_agent jobs for all agents and return a trackable batch id."""
    import uuid as _uuid
    batch_id = _uuid.uuid4().hex[:12]

    data = {}
    try:
        data = await request.json()
    except Exception:
        pass
    retry_batch = re.sub(r'[^a-fA-F0-9]', '', data.get("retry_batch", ""))

    with get_db_ctx() as conn:
        if retry_batch:
            batch_filter = f'%"batch": "{retry_batch}"%'
            agents = conn.execute("""
                SELECT DISTINCT j.agent_id, a.hostname FROM jobs j
                JOIN agents a ON a.id = j.agent_id
                WHERE j.type = 'update_agent' AND j.status = 'failed' AND j.params LIKE ?
                  AND a.last_seen IS NOT NULL
                  AND (julianday('now','localtime') - julianday(a.last_seen)) * 86400 < 120
            """, (batch_filter,)).fetchall()
        else:
            agents = conn.execute("""
                SELECT id AS agent_id, hostname
                FROM agents
                WHERE last_seen IS NOT NULL
                  AND COALESCE(agent_type, 'linux') != 'haos'
                  AND (julianday('now','localtime') - julianday(last_seen)) * 86400 < 120
            """).fetchall()

        if not agents:
            raise HTTPException(status_code=422, detail="No agents to update")

        count = 0
        for a in agents:
            aid = a["agent_id"] if "agent_id" in a.keys() else a["id"]
            params = json.dumps({"batch": batch_id})
            conn.execute(
                "INSERT INTO jobs (agent_id, type, params, created) VALUES (?, 'update_agent', ?, datetime('now','localtime'))",
                (aid, params),
            )
            count += 1
    _cache_invalidate("dashboard")
    return {"status": "queued", "agent_count": count, "batch_id": batch_id}


@app.get("/api/settings/deploy-ssl/status", dependencies=[Depends(require_role("admin"))])
def api_deploy_ssl_status(batch: str = ""):
    """Return progress of SSL deployment for a specific batch.

    Shows the most advanced job per agent: deploy_ssl if it exists, otherwise
    the chained update_agent.  Phase: 'updating' while update_agent runs,
    'deploying' while deploy_ssl runs, status when done/failed.
    """
    batch = re.sub(r'[^a-fA-F0-9]', '', batch or '')  # SEC: sanitize
    if not batch:
        return {"agents": [], "total": 0, "completed": 0}

    batch_filter = f'%"batch": "{batch}"%'
    with get_db_ctx() as conn:
        # Get deploy_ssl jobs for this batch
        ssl_rows = conn.execute("""
            SELECT j.agent_id, a.hostname, j.status, j.output, j.finished
            FROM jobs j JOIN agents a ON a.id = j.agent_id
            WHERE j.type = 'deploy_ssl' AND j.params LIKE ?
        """, (batch_filter,)).fetchall()
        ssl_map = {r["agent_id"]: r for r in ssl_rows}

        # Get the chained update_agent jobs for this batch
        upd_rows = conn.execute("""
            SELECT j.agent_id, a.hostname, j.status, j.output, j.finished
            FROM jobs j JOIN agents a ON a.id = j.agent_id
            WHERE j.type = 'update_agent' AND j.params LIKE ?
        """, (batch_filter,)).fetchall()

        # Get online status for all agents (seen within last 2 min)
        online_rows = conn.execute("""
            SELECT id, (julianday('now','localtime') - julianday(last_seen)) * 86400 < 120 AS is_online
            FROM agents WHERE last_seen IS NOT NULL
        """).fetchall()
        online_map = {r["id"]: bool(r["is_online"]) for r in online_rows}

    agents = []
    for r in upd_rows:
        aid = r["agent_id"]
        is_online = online_map.get(aid, False)
        if aid in ssl_map:
            sr = ssl_map[aid]
            phase = "done" if sr["status"] == "done" else "failed" if sr["status"] == "failed" else "deploying"
            agents.append({
                "agent_id": aid, "hostname": sr["hostname"],
                "status": sr["status"], "phase": phase,
                "output": sr["output"] or "", "finished": sr["finished"],
                "online": is_online,
            })
        else:
            phase = "updating" if r["status"] in ("pending", "running") else (
                "failed" if r["status"] == "failed" else "waiting"
            )
            agents.append({
                "agent_id": aid, "hostname": r["hostname"],
                "status": r["status"] if r["status"] == "failed" else phase,
                "phase": phase,
                "output": r["output"] or "" if r["status"] == "failed" else "",
                "finished": r["finished"],
                "online": is_online,
            })
    # Sort: online first, then by hostname
    agents.sort(key=lambda a: (not a["online"], a["hostname"]))
    total_online = sum(1 for a in agents if a["online"])
    total = len(agents)
    done = sum(1 for a in agents if a["status"] in ("done", "failed"))
    # Consider deployment "complete" when all online agents are done
    # Offline agents will pick up jobs when they reconnect
    return {"agents": agents, "total": total, "total_online": total_online, "completed": done}


@app.get("/api/agents/update-batch/status", dependencies=[Depends(require_role("admin"))])
def api_update_agents_batch_status(batch: str = ""):
    """Return progress of an update_agent batch."""
    batch = re.sub(r'[^a-fA-F0-9]', '', batch or '')
    if not batch:
        return {"agents": [], "total": 0, "completed": 0}

    batch_filter = f'%"batch": "{batch}"%'
    with get_db_ctx() as conn:
        rows = conn.execute("""
            SELECT j.agent_id, a.hostname, j.status, j.output, j.finished
            FROM jobs j JOIN agents a ON a.id = j.agent_id
            WHERE j.type = 'update_agent' AND j.params LIKE ?
        """, (batch_filter,)).fetchall()

        online_rows = conn.execute("""
            SELECT id, (julianday('now','localtime') - julianday(last_seen)) * 86400 < 120 AS is_online
            FROM agents WHERE last_seen IS NOT NULL
        """).fetchall()
        online_map = {r["id"]: bool(r["is_online"]) for r in online_rows}

    agents = []
    for r in rows:
        phase = "updating" if r["status"] in ("pending", "running") else (
            "failed" if r["status"] == "failed" else "done"
        )
        agents.append({
            "agent_id": r["agent_id"],
            "hostname": r["hostname"],
            "status": r["status"],
            "phase": phase,
            "output": r["output"] or "",
            "finished": r["finished"],
            "online": online_map.get(r["agent_id"], False),
        })

    agents.sort(key=lambda a: (not a["online"], a["hostname"]))
    total_online = sum(1 for a in agents if a["online"])
    total = len(agents)
    done = sum(1 for a in agents if a["status"] in ("done", "failed"))
    return {"agents": agents, "total": total, "total_online": total_online, "completed": done}


# ===========================================================================
# ===========================================================================
# AUTH ENDPOINTS
# ===========================================================================

@app.post("/api/auth/login")
async def auth_login(request: Request):
    _check_rate_limit(request)
    data = await request.json()
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not username or not password:
        raise HTTPException(status_code=422, detail="Username and password required")
    if len(password) > 1024:
        raise HTTPException(status_code=422, detail="Password too long")
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username=?",
            (username,),
        ).fetchone()
    # Constant-time: always run verify_password even for non-existent users
    dummy_hash = hash_password("dummy")
    stored_hash = row["password_hash"] if row else dummy_hash
    valid = verify_password(password, stored_hash)
    if not row or not valid:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = secrets.token_hex(32)
    _sessions[token] = {
        "user_id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "created": time.monotonic(),
    }
    return {"token": token, "role": row["role"], "username": row["username"]}


@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    auth_val = request.headers.get("authorization", "")
    if auth_val.startswith("Bearer "):
        _sessions.pop(auth_val[7:], None)
    return {"status": "ok"}


@app.get("/api/auth/me", dependencies=[Depends(require_role("admin", "user", "readonly"))])
def auth_me(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401)
    return {"username": user["username"], "role": user["role"]}


# ===========================================================================
# USER MANAGEMENT (admin only)
# ===========================================================================

@app.get("/api/users", dependencies=[Depends(require_role("admin"))])
def list_users():
    with get_db_ctx() as conn:
        rows = conn.execute("SELECT id, username, role, created FROM users ORDER BY id").fetchall()
    return {"users": [dict(r) for r in rows]}


@app.post("/api/users", dependencies=[Depends(require_role("admin"))])
async def create_user(request: Request):
    data = await request.json()
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    role = str(data.get("role", "user"))
    if not username or not password:
        raise HTTPException(status_code=422, detail="Username and password required")
    if role not in ("admin", "user", "readonly"):
        raise HTTPException(status_code=422, detail="Invalid role")
    if len(username) > 64 or len(password) < 4 or len(password) > 1024:
        raise HTTPException(status_code=422, detail="Username max 64 chars, password 4-1024 chars")
    with get_db_ctx() as conn:
        existing = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Username already exists")
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, hash_password(password), role),
        )
    return {"status": "created"}


@app.patch("/api/users/{user_id}", dependencies=[Depends(require_role("admin"))])
async def update_user(user_id: int, request: Request):
    data = await request.json()
    with get_db_ctx() as conn:
        row = conn.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        if "role" in data:
            role = str(data["role"])
            if role not in ("admin", "user", "readonly"):
                raise HTTPException(status_code=422, detail="Invalid role")
            conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        if "password" in data:
            password = str(data["password"])
            if len(password) < 4:
                raise HTTPException(status_code=422, detail="Password min 4 chars")
            conn.execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                (hash_password(password), user_id),
            )
    # Invalidate active sessions for this user so role/password change takes effect immediately
    to_remove = [t for t, s in _sessions.items() if s.get("user_id") == user_id]
    for t in to_remove:
        _sessions.pop(t, None)
    return {"status": "updated"}


@app.delete("/api/users/{user_id}", dependencies=[Depends(require_role("admin"))])
def delete_user(user_id: int, request: Request):
    user = getattr(request.state, "user", {})
    # Legacy admin key has user_id=0; also prevent deleting yourself by session
    if user.get("user_id") == user_id and user_id != 0:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    # Count remaining admins — prevent deleting the last one
    with get_db_ctx() as conn:
        target = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        if target["role"] == "admin":
            admin_count = conn.execute("SELECT COUNT(*) as c FROM users WHERE role='admin'").fetchone()["c"]
            if admin_count <= 1:
                raise HTTPException(status_code=400, detail="Cannot delete the last admin user")
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    # Invalidate any sessions for this user
    to_remove = [t for t, s in _sessions.items() if s.get("user_id") == user_id]
    for t in to_remove:
        _sessions.pop(t, None)
    return {"status": "deleted"}


# Serve React frontend (if built)
# ===========================================================================
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        # LOW-3: resolve to prevent path traversal before serving
        file_path = (STATIC_DIR / full_path).resolve()
        static_root = STATIC_DIR.resolve()
        # LOW-3: Python < 3.9 fallback for is_relative_to()
        try:
            is_relative = file_path.is_relative_to(static_root)
        except AttributeError:
            is_relative = str(file_path).startswith(str(static_root))
        if file_path.is_file() and is_relative:
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")

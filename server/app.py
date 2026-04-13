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
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from apscheduler.triggers.cron import CronTrigger as _CronTrigger
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles

from db import init_db, db as get_db_ctx, hash_password, verify_password
from deps import (
    _ADMIN_KEY_ENV,
    _delete_session_from_db,
    _delete_sessions_for_user,
    _hash_token,
    _load_sessions_from_db,
    _persist_session,
    _sessions,
    require_admin,
    require_role,
    verify_agent,
)
from scheduler import (
    scheduler,
    schedule_job,
    register_system_jobs,
    get_scheduler_timezone,
    configure_timezone,
    agent_connectivity_state,
    ping_connectivity_state,
    is_effectively_online,
    trigger_ping_check_for_agent,
)
from notifications import notification_manager
from routes.agents import router as agents_router
from routes.auth import router as auth_router
from routes.dashboard import router as dashboard_router
from routes.deploy import router as deploy_router
from routes.settings import router as settings_router
import metrics as metrics_module


@asynccontextmanager
async def lifespan(app: FastAPI):
    _startup_app()
    try:
        yield
    finally:
        _shutdown_app()


app = FastAPI(title="PatchPilot API", lifespan=lifespan)

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


def _read_version_constant(path: Path, constant: str, fallback: str) -> str:
    try:
        content = path.read_text(encoding="utf-8")
        match = re.search(rf'^{constant}\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
        if match:
            return match.group(1).strip() or fallback
    except Exception:
        pass
    return fallback


_ROOT_DIR = Path(__file__).resolve().parent.parent
_AGENT_TARGET_VERSION = os.environ.get(
    "PATCHPILOT_AGENT_TARGET_VERSION",
    _read_version_constant(_ROOT_DIR / "agent" / "agent.py", "AGENT_VERSION", "1.0"),
)
_HA_AGENT_TARGET_VERSION = os.environ.get(
    "PATCHPILOT_HA_AGENT_TARGET_VERSION",
    _read_version_constant(
        _ROOT_DIR / "home-assistant-addons" / "patchpilot_haos" / "rootfs" / "opt" / "patchpilot-haos" / "agent.py",
        "AGENT_VERSION",
        _AGENT_TARGET_VERSION,
    ),
)


def _bootstrap_password_file() -> Path:
    raw = os.environ.get(
        "PATCHPILOT_BOOTSTRAP_PASSWORD_FILE",
        str(_ROOT_DIR / "bootstrap-admin.txt"),
    ).strip()
    return Path(raw)


def _remove_bootstrap_password_file() -> None:
    path = _bootstrap_password_file()
    try:
        if path.exists():
            path.unlink()
    except Exception as exc:
        print(f"[patchpilot] WARNING: failed to remove bootstrap password file {path}: {exc}")

# Prefixes that are agent-only (served on AGENT_PORT)
_AGENT_PREFIXES = ("/api/agents/", "/agent/")


def _is_agent_only_request(path: str, method: str) -> bool:
    """Return True only for agent-facing endpoints that must stay on AGENT_PORT."""
    if path == "/api/agents/register" or path.startswith("/agent/"):
        return True
    if not path.startswith("/api/agents/"):
        return False
    suffix = path[len("/api/agents/"):]
    if suffix.endswith("/heartbeat"):
        return True
    if method == "POST" and suffix.endswith("/ha-update-callback"):
        return True
    if method == "GET" and suffix.endswith("/jobs"):
        return True
    if method == "POST" and "/jobs/" in suffix and suffix.endswith("/result"):
        return True
    return False


@app.middleware("http")
async def _port_routing(request: Request, call_next):
    """Block requests that arrive on the wrong port."""
    if _UI_PORT != _AGENT_PORT:
        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        path = request.url.path
        is_shared = path in ("/api/ping", "/api/server-time")
        is_agent_only = _is_agent_only_request(path, request.method)

        if not is_shared:
            if port == _AGENT_PORT and not is_agent_only:
                return JSONResponse(status_code=404, content={"detail": "Not available on agent port"})
            if port == _UI_PORT and is_agent_only:
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

# Register monitoring router — must be after require_admin is defined
app.include_router(metrics_module.router, dependencies=[Depends(require_role("admin"))])
app.include_router(agents_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(deploy_router)
app.include_router(settings_router)

STATIC_DIR = Path(os.environ.get("PATCHPILOT_STATIC_DIR", str(Path(__file__).parent.parent / "frontend" / "dist")))

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
_AGENT_ID_RE = re.compile(r'^[a-zA-Z0-9._-]{1,64}$')
_TG_TOKEN_RE  = re.compile(r'^\d+:[A-Za-z0-9_-]{35,}$')
ALLOWED_JOB_TYPES = {"patch", "dist_upgrade", "force_patch", "refresh_updates", "reboot", "update_agent", "autoremove", "deploy_ssl", "ack_config_review", "ha_backup", "ha_core_update", "ha_backup_update", "ha_supervisor_update", "ha_os_update", "ha_addon_update", "ha_addons_update", "ha_entity_update", "ha_trigger_agent_update"}
_MANAGED_AGENT_TYPES = {"linux", "haos"}

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
    if agent_type in {"linux", "haos", "ping"}:
        return agent_type
    os_pretty = (fields.get("os_pretty") or "").lower()
    if "home assistant os" in os_pretty:
        return "haos"
    return "linux"


# HIGH-3: Capabilities allowed per agent type — agents cannot claim capabilities
# outside their type's allowlist, preventing privilege escalation via false claims.
_CAPABILITIES_BY_TYPE: dict[str, set[str]] = {
    "linux":  {"ssl", "ha_agent_auto_update"},
    "haos":   {
        "ha_backup", "ha_core_update", "ha_backup_update", "ha_supervisor_update",
        "ha_os_update", "ha_addon_update", "ha_addons_update", "ha_entity_update",
        "ha_agent_auto_update", "ssl",
    },
    "ping":   set(),
}


def _normalize_capabilities(fields: dict) -> str:
    raw = str(fields.get("capabilities") or "").strip()
    if not raw:
        return ""
    agent_type = str(fields.get("agent_type") or "linux").lower()
    allowed = _CAPABILITIES_BY_TYPE.get(agent_type, _CAPABILITIES_BY_TYPE["linux"])
    parts = []
    for item in raw.split(","):
        name = item.strip().lower()
        if name and re.fullmatch(r"[a-z0-9_.-]{1,64}", name) and name in allowed:
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
                     day_of_week=dow, timezone=get_scheduler_timezone())
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
    placeholders = ",".join("?" * len(parts))
    with get_db_ctx() as conn:
        rows = conn.execute(
            f"SELECT id, COALESCE(agent_type, 'linux') AS agent_type FROM agents WHERE id IN ({placeholders})",  # noqa: S608
            parts,
        ).fetchall()
    found = {row["id"]: str(row["agent_type"] or "linux") for row in rows}
    missing = [part for part in parts if part not in found]
    if missing:
        raise HTTPException(status_code=422, detail=f"Unknown agent ID in target: {missing[0]!r}")
    unsupported = [part for part, agent_type in found.items() if agent_type not in _MANAGED_AGENT_TYPES]
    if unsupported:
        raise HTTPException(status_code=422, detail=f"Monitor-only targets cannot be scheduled: {unsupported[0]!r}")

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


def _validate_webhook_url(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        raise HTTPException(status_code=422, detail="Webhook URL is required")
    if len(value) > 2048:
        raise HTTPException(status_code=422, detail="Webhook URL must be 2048 characters or less")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="Webhook URL must be a valid http(s) URL")
    return value.rstrip("/")


def _validate_ping_target_fields(hostname: str, address: str) -> tuple[str, str]:
    hostname = str(hostname or "").strip()
    address = str(address or "").strip()
    if not hostname:
        raise HTTPException(status_code=422, detail="Hostname is required")
    if not address:
        raise HTTPException(status_code=422, detail="Address is required")
    if len(hostname) > 64:
        raise HTTPException(status_code=422, detail="Hostname must be 64 characters or less")
    if len(address) > 255:
        raise HTTPException(status_code=422, detail="Address must be 255 characters or less")
    if any(ch in hostname for ch in "\r\n\t"):
        raise HTTPException(status_code=422, detail="Hostname contains unsupported control characters")
    if not re.search(r"[A-Za-z0-9]", hostname):
        raise HTTPException(status_code=422, detail="Hostname contains unsupported characters")
    return hostname, address


def _slugify_agent_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", str(value or "").strip().lower())
    slug = slug.strip(".-_")[:64]
    return slug or "ping-target"


def _allocate_agent_id(conn, desired: str) -> str:
    base = _slugify_agent_id(desired)
    candidate = base
    suffix = 2
    while conn.execute("SELECT 1 FROM agents WHERE id=?", (candidate,)).fetchone():
        tail = f"-{suffix}"
        candidate = f"{base[:max(1, 64 - len(tail))]}{tail}"
        suffix += 1
    return candidate

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

def _normalize_ip(raw: str) -> str:
    """Normalize an IP string to canonical form (handles IPv4-mapped IPv6 etc.)."""
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return raw


def _get_client_ip(request: Request) -> str:
    """MED-2: Extract real client IP.  Only honour X-Forwarded-For when the
    connection comes from the configured trusted proxy address.
    IPs are normalized via ipaddress so ::1 and 127.0.0.1 compare correctly."""
    direct_ip = _normalize_ip(request.client.host if request.client else "")
    if _TRUSTED_PROXY:
        try:
            trusted = str(ipaddress.ip_address(_TRUSTED_PROXY))
        except ValueError:
            trusted = _TRUSTED_PROXY
        if direct_ip == trusted:
            forwarded = request.headers.get("x-forwarded-for", "")
            candidate = forwarded.split(",")[0].strip()
            if candidate:
                return _normalize_ip(candidate)
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
# Note: update/reboot notification dedup is DB-based (agents.updates_notified /
# agents.reboot_notified) so it survives server restarts and works across processes.


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
        raise RuntimeError(f"could not update environment file for port change: {exc}") from exc


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
        raise RuntimeError(f"could not update environment file for {key}: {exc}") from exc


def _schedule_restart(delay: float = 1.5) -> None:
    """Restart PatchPilot after *delay* s.

    Default to a process exit so systemd `Restart=always` can bring the service
    back without relying on privilege escalation from the service user.
    """
    def _do() -> None:
        time.sleep(delay)
        mode = os.environ.get("PATCHPILOT_RESTART_MODE", "process")
        try:
            if mode == "systemd":
                if os.geteuid() == 0:
                    result = subprocess.run(["systemctl", "restart", "patchpilot"], check=False)
                else:
                    result = subprocess.run(["sudo", "-n", "systemctl", "restart", "patchpilot"], check=False)
                if result.returncode == 0:
                    return
                import sys
                print(
                    f"[patchpilot] Warning: systemd restart returned {result.returncode}, "
                    "falling back to process restart",
                    file=sys.stderr,
                )
        except Exception as exc:
            import sys
            print(f"[patchpilot] Warning: restart failed ({exc}), falling back to process restart", file=sys.stderr)
        os._exit(0)
    threading.Thread(target=_do, daemon=True).start()


def _startup_app():
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
        future_jobs = conn.execute(
            "UPDATE jobs SET created=datetime('now','localtime') "
            "WHERE created IS NOT NULL "
            "AND datetime(created) > datetime('now','localtime', '+5 minutes')"
        ).rowcount
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
        if future_jobs:
            print(f"[startup] Normalized {future_jobs} future-dated job timestamp(s)")
        if stale_running:
            print(f"[startup] Cleaned up {stale_running} stale running job(s)")
        if stale_pending:
            print(f"[startup] Cleaned up {stale_pending} stale pending job(s)")
    _load_sessions_from_db()
    configure_timezone(get_scheduler_timezone())
    scheduler.start()
    _load_schedules()
    register_system_jobs()
    # If the port was changed, forward the old port → new port so agents reconnect
    if _LEGACY_PORT and _LEGACY_PORT != _SERVER_PORT:
        _start_legacy_forwarder(_LEGACY_PORT, _SERVER_PORT)


def _shutdown_app():
    scheduler.shutdown(wait=False)


def _load_schedules():
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT id, name, cron, action, target FROM schedules WHERE enabled=1"
        ).fetchall()
    for row in rows:
        schedule_job(row["id"], row["name"], row["cron"], row["action"], row["target"])


def _redact_agent_record(row: dict) -> dict:
    """Remove sensitive fields before returning agent data to the UI."""
    row.pop("token", None)
    return row


def _ha_job_pending_target(job: dict) -> tuple[str | None, str | None]:
    params_raw = job.get("params")
    params: dict[str, object] = {}
    if isinstance(params_raw, str) and params_raw:
        try:
            decoded = json.loads(params_raw)
            if isinstance(decoded, dict):
                params = decoded
        except json.JSONDecodeError:
            params = {}
    elif isinstance(params_raw, dict):
        params = params_raw

    jtype = str(job.get("type") or "")
    if jtype in {"ha_core_update", "ha_backup_update"}:
        return "home-assistant-core", None
    if jtype == "ha_supervisor_update":
        return "home-assistant-supervisor", None
    if jtype == "ha_os_update":
        return "home-assistant-os", None
    if jtype == "ha_addon_update":
        slug = str(params.get("slug") or "").strip()
        if not slug:
            return None, None
        if slug.endswith("patchpilot_haos"):
            return "home-assistant-addon-patchpilot", None
        return f"addon:{slug}", None
    if jtype == "ha_entity_update":
        entity_id = str(params.get("entity_id") or "").strip()
        return None, entity_id or None
    return None, None


def _resolve_ha_job_display_status(job: dict, package_state: dict[str, set[str]], agent_last_seen: str | None) -> dict:
    if str(job.get("status") or "") != "running":
        return {"status": job.get("status"), "finished": job.get("finished")}

    name_target, source_target = _ha_job_pending_target(job)
    if not name_target and not source_target:
        return {"status": job.get("status"), "finished": job.get("finished")}

    started_raw = str(job.get("started") or "").strip()
    if not started_raw or not agent_last_seen:
        return {"status": job.get("status"), "finished": job.get("finished")}

    try:
        started_dt = datetime.strptime(started_raw, "%Y-%m-%d %H:%M:%S")
        last_seen_dt = datetime.strptime(agent_last_seen, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return {"status": job.get("status"), "finished": job.get("finished")}

    if last_seen_dt < started_dt:
        return {"status": job.get("status"), "finished": job.get("finished")}

    pending_names = package_state.get("names", set())
    pending_source_ids = package_state.get("source_ids", set())
    if name_target and name_target in pending_names:
        return {"status": job.get("status"), "finished": job.get("finished")}
    if source_target and source_target in pending_source_ids:
        return {"status": job.get("status"), "finished": job.get("finished")}

    return {"status": "done", "finished": agent_last_seen}


def _agent_online_status(row: dict, last_job: dict | None = None) -> dict:
    seconds_ago = row.get("seconds_ago")
    if str(row.get("agent_type") or "") == "ping":
        state = ping_connectivity_state(
            seconds_ago,
            row.get("ping_failures"),
            row.get("ping_last_checked"),
        )
    else:
        state = agent_connectivity_state(seconds_ago, last_job)
    row["effective_online"] = state != "offline"
    row["connectivity_state"] = state
    return row


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
# SETTINGS API
# ===========================================================================

# Keys that contain sensitive data — masked in GET, encrypted in DB
_SENSITIVE_KEYS = {"smtp_password", "telegram_token", "webhook_secret"}

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
    "webhook_url",
    "scheduler_timezone",
    "server_port", "agent_port", "agent_ssl",
    "ui_audio_enabled", "ui_audio_volume", "ui_login_animation_enabled", "ui_login_background_animation_enabled", "ui_login_background_opacity",
}

_SSL_DIR = Path(os.environ.get("PATCHPILOT_SSL_DIR", str(Path(__file__).parent.parent / "ssl")))
AGENT_DIR = Path(__file__).parent.parent / "agent"
_CA_ROLLOVER_PRIVATE_KEY = _SSL_DIR / "ca_rollover_private.pem"
_CA_ROLLOVER_PUBLIC_KEY = _SSL_DIR / "ca_rollover_public.pem"


def _ensure_ca_rollover_keypair() -> None:
    if _CA_ROLLOVER_PRIVATE_KEY.exists() and _CA_ROLLOVER_PUBLIC_KEY.exists():
        return
    _SSL_DIR.mkdir(parents=True, exist_ok=True)
    private_tmp = _CA_ROLLOVER_PRIVATE_KEY.with_suffix(".tmp")
    public_tmp = _CA_ROLLOVER_PUBLIC_KEY.with_suffix(".tmp")
    gen = subprocess.run(
        ["openssl", "genrsa", "-out", str(private_tmp), "3072"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if gen.returncode != 0:
        raise RuntimeError(f"openssl genrsa failed: {gen.stderr[:200]}")
    pub = subprocess.run(
        ["openssl", "rsa", "-in", str(private_tmp), "-pubout", "-out", str(public_tmp)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if pub.returncode != 0:
        try:
            private_tmp.unlink()
        except OSError:
            pass
        raise RuntimeError(f"openssl rsa -pubout failed: {pub.stderr[:200]}")
    os.replace(private_tmp, _CA_ROLLOVER_PRIVATE_KEY)
    os.replace(public_tmp, _CA_ROLLOVER_PUBLIC_KEY)
    _CA_ROLLOVER_PRIVATE_KEY.chmod(0o600)
    _CA_ROLLOVER_PUBLIC_KEY.chmod(0o644)


def _get_ca_rollover_public_pem() -> bytes:
    _ensure_ca_rollover_keypair()
    return _CA_ROLLOVER_PUBLIC_KEY.read_bytes()


def _sign_ca_rollover_payload(payload: bytes) -> bytes:
    _ensure_ca_rollover_keypair()
    payload_tmp = _SSL_DIR / "ca_rollover_payload.tmp"
    sig_tmp = _SSL_DIR / "ca_rollover_payload.sig.tmp"
    payload_tmp.write_bytes(payload)
    try:
        result = subprocess.run(
            [
                "openssl", "dgst", "-sha256",
                "-sign", str(_CA_ROLLOVER_PRIVATE_KEY),
                "-out", str(sig_tmp),
                str(payload_tmp),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise RuntimeError(f"openssl dgst -sign failed: {result.stderr[:200]}")
        return sig_tmp.read_bytes()
    finally:
        for path in (payload_tmp, sig_tmp):
            try:
                path.unlink()
            except OSError:
                pass


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
        raise RuntimeError(f"could not update environment file for SSL: {exc}") from exc


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


# ===========================================================================
# MONITORING ENDPOINTS
# ===========================================================================

_DISK_ALERT_THRESHOLD = 90  # percent used → alert



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

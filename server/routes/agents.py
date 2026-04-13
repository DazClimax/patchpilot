import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request

from deps import _get_db_ctx, _hash_token, verify_agent
from notifications import notification_manager

router = APIRouter()


@router.post("/api/agents/register")
async def register_agent(request: Request):
    from app import (
        _check_rate_limit,
        _infer_agent_type,
        _infer_package_manager,
        _normalize_capabilities,
        _sanitize_agent_fields,
        _validate_agent_id,
        _verify_register_key,
    )

    _check_rate_limit(request)
    data = await request.json()
    agent_id = data.get("id") or secrets.token_hex(8)
    _validate_agent_id(agent_id)
    fields = _sanitize_agent_fields(data)
    fields["package_manager"] = _infer_package_manager(fields)
    fields["agent_type"] = _infer_agent_type(fields)
    fields["capabilities"] = _normalize_capabilities(fields)
    token = secrets.token_hex(32)
    with _get_db_ctx() as conn:
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
                _verify_register_key(reg_key)
            else:
                raise HTTPException(status_code=403, detail="Re-registration requires current token or valid register key")
        else:
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
                _hash_token(token),
            ),
        )
    return {"agent_id": agent_id, "token": token}


@router.post("/api/agents/{agent_id}/heartbeat")
async def heartbeat(agent_id: str, request: Request, x_token: str = Header(...)):
    from app import (
        _AGENT_PORT,
        _AGENT_SCHEME,
        _HEARTBEAT_MIN_INTERVAL,
        _cache_invalidate,
        _check_agent_rate_limit,
        _clear_alias,
        _get_internal_ip,
        _infer_agent_type,
        _infer_package_manager,
        _last_heartbeat,
        _normalize_capabilities,
        _resolve_alias,
        _sanitize_agent_fields,
    )

    resolved_id = _resolve_alias(agent_id)
    if resolved_id != agent_id:
        verify_agent(resolved_id, x_token)
        agent_id = resolved_id
    else:
        verify_agent(agent_id, x_token)
        _clear_alias(new_id=agent_id)
    _check_agent_rate_limit(request)

    now_mono = time.monotonic()
    last = _last_heartbeat.get(agent_id, 0.0)
    if now_mono - last < _HEARTBEAT_MIN_INTERVAL:
        return {
            "status": "ok",
            "canonical_port": str(_AGENT_PORT),
            "canonical_url": f"{_AGENT_SCHEME}://{_get_internal_ip()}:{_AGENT_PORT}",
            "canonical_id": agent_id,
        }
    _last_heartbeat[agent_id] = now_mono
    _cache_invalidate("dashboard", f"agent:{agent_id}")

    data = await request.json()
    packages = data.get("packages", [])
    if len(packages) > 2000:
        packages = packages[:2000]
    fields = _sanitize_agent_fields(data)
    fields["package_manager"] = _infer_package_manager(fields)
    fields["agent_type"] = _infer_agent_type(fields)
    fields["capabilities"] = _normalize_capabilities(fields)

    raw_uptime = data.get("uptime_seconds")
    uptime_seconds = None
    if raw_uptime is not None:
        try:
            uptime_seconds = int(raw_uptime)
            if not (0 <= uptime_seconds <= 2147483647):
                uptime_seconds = None
        except (ValueError, TypeError):
            uptime_seconds = None

    disk_max = 256 * 1024**4

    def _parse_disk_bytes(value) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(value)
            return parsed if 0 <= parsed <= disk_max else None
        except (ValueError, TypeError):
            return None

    disk_total = _parse_disk_bytes(data.get("disk_total"))
    disk_used = _parse_disk_bytes(data.get("disk_used"))
    disk_free = _parse_disk_bytes(data.get("disk_free"))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config_review_required = 1 if data.get("config_review_required") else 0
    config_review_note = str(data.get("config_review_note", ""))[:4000] if config_review_required else ""
    protocol = "https" if request.url.scheme == "https" else "http"

    with _get_db_ctx() as conn:
        current = conn.execute(
            "SELECT hostname, pending_count, reboot_required FROM agents WHERE id=?",
            (agent_id,),
        ).fetchone()
        hostname = fields["hostname"] or (current["hostname"] if current else "unknown")
        conn.execute(
            """UPDATE agents SET
                hostname=?, ip=?, os_pretty=?, kernel=?, arch=?, package_manager=?, agent_version=?, agent_type=?, capabilities=?,
                reboot_required=?, pending_count=?, last_seen=?, uptime_seconds=?,
                protocol=?, config_review_required=?, config_review_note=?,
                disk_total=?, disk_used=?, disk_free=?
               WHERE id=?""",
            (
                hostname,
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
                disk_total,
                disk_used,
                disk_free,
                agent_id,
            ),
        )
        conn.execute("DELETE FROM packages WHERE agent_id=?", (agent_id,))
        conn.executemany(
            "INSERT OR REPLACE INTO packages (agent_id, name, current_ver, source_kind, source_id, new_ver) VALUES (?,?,?,?,?,?)",
            [
                (
                    agent_id,
                    str(pkg.get("name", ""))[:256],
                    str(pkg.get("current", ""))[:128] if pkg.get("current") else None,
                    str(pkg.get("source_kind", ""))[:64] if pkg.get("source_kind") else None,
                    str(pkg.get("source_id", ""))[:256] if pkg.get("source_id") else None,
                    str(pkg.get("new", ""))[:128] if pkg.get("new") else None,
                )
                for pkg in packages
            ],
        )

    new_pending = len(packages)
    new_reboot = 1 if data.get("reboot_required") else 0
    with _get_db_ctx() as conn:
        flags = conn.execute(
            "SELECT updates_notified, reboot_notified FROM agents WHERE id=?",
            (agent_id,),
        ).fetchone()
        already_updates = flags["updates_notified"] if flags else 0
        already_reboot = flags["reboot_notified"] if flags else 0

        if new_pending > 0:
            if not already_updates:
                notification_manager.notify_patch_available({"hostname": hostname, "id": agent_id}, new_pending)
                conn.execute("UPDATE agents SET updates_notified=1 WHERE id=?", (agent_id,))
        elif already_updates:
            conn.execute("UPDATE agents SET updates_notified=0 WHERE id=?", (agent_id,))

        if new_reboot:
            if not already_reboot:
                notification_manager.notify_reboot_required({"hostname": hostname, "id": agent_id})
                conn.execute("UPDATE agents SET reboot_notified=1 WHERE id=?", (agent_id,))
        elif already_reboot:
            conn.execute("UPDATE agents SET reboot_notified=0 WHERE id=?", (agent_id,))

    return {
        "status": "ok",
        "canonical_port": str(_AGENT_PORT),
        "canonical_url": f"{_AGENT_SCHEME}://{_get_internal_ip()}:{_AGENT_PORT}",
        "canonical_id": agent_id,
    }


@router.get("/api/agents/{agent_id}/jobs")
def get_jobs(agent_id: str, x_token: str = Header(...)):
    from app import _resolve_alias

    agent_id = _resolve_alias(agent_id)
    verify_agent(agent_id, x_token)
    with _get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT id, type, params FROM jobs WHERE agent_id=? AND status='pending' ORDER BY id",
            (agent_id,),
        ).fetchall()
        if rows:
            ids = [row["id"] for row in rows]
            placeholders = ",".join("?" * len(ids))
            safe_ids = [int(job_id) for job_id in ids]
            conn.execute(
                f"UPDATE jobs SET status='running', started=datetime('now','localtime') WHERE id IN ({placeholders})",
                safe_ids,
            )

    ssl_active = bool(os.environ.get("SSL_CERTFILE"))
    agent_py = Path(__file__).resolve().parents[2] / "agent" / "agent.py"

    result = []
    for row in rows:
        job = {"id": row["id"], "type": row["type"], "params": json.loads(row["params"] or "{}")}
        if row["type"] == "update_agent" and ssl_active and agent_py.exists():
            code = agent_py.read_bytes()
            job["params"]["inline_code"] = base64.b64encode(code).decode()
            job["params"]["inline_sha256"] = hashlib.sha256(code).hexdigest()
        result.append(job)
    return result


@router.post("/api/agents/{agent_id}/jobs/{job_id}/result")
async def job_result(agent_id: str, job_id: int, request: Request, x_token: str = Header(...)):
    from app import ALLOWED_JOB_TYPES, _resolve_alias

    agent_id = _resolve_alias(agent_id)
    verify_agent(agent_id, x_token)
    data = await request.json()
    output = (data.get("output") or "")[:65536]
    raw_status = data.get("status", "done")
    status = raw_status if raw_status in {"done", "failed"} else "done"
    with _get_db_ctx() as conn:
        conn.execute(
            "UPDATE jobs SET status=?, output=?, finished=datetime('now','localtime') WHERE id=? AND agent_id=?",
            (status, output, job_id, agent_id),
        )
        agent_row = conn.execute("SELECT hostname FROM agents WHERE id=?", (agent_id,)).fetchone()
        job_row = conn.execute("SELECT type, params FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job_row and job_row["type"] == "update_agent" and status == "done":
            try:
                params = json.loads(job_row["params"] or "{}")
                chain_type = params.get("chain")
                if chain_type and chain_type in ALLOWED_JOB_TYPES:
                    chain_params = dict(params.get("chain_params") or {})
                    if params.get("batch") and "batch" not in chain_params:
                        chain_params["batch"] = params["batch"]
                    conn.execute(
                        "INSERT INTO jobs (agent_id, type, params, created) VALUES (?, ?, ?, datetime('now','localtime'))",
                        (agent_id, chain_type, json.dumps(chain_params)),
                    )
            except (json.JSONDecodeError, AttributeError):
                pass
    if agent_row and job_row:
        hostname = agent_row["hostname"] or agent_id
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


@router.post("/api/agents/{agent_id}/ha-update-callback")
async def ha_update_callback(agent_id: str, request: Request, x_token: str = Header(...)):
    from app import _resolve_alias

    agent_id = _resolve_alias(agent_id)
    verify_agent(agent_id, x_token)
    data = await request.json()
    batch = re.sub(r"[^a-fA-F0-9]", "", str(data.get("batch", "") or ""))
    agent_version = str(data.get("agent_version", "") or "")
    if not batch:
        raise HTTPException(status_code=422, detail="batch is required")
    output = f"HA add-on restart callback received. Agent version: {agent_version or 'unknown'}"
    batch_filter = f'%\"batch\": \"{batch}\"%'
    with _get_db_ctx() as conn:
        row = conn.execute(
            """
            SELECT id FROM jobs
            WHERE agent_id=? AND type='ha_trigger_agent_update' AND params LIKE ?
            ORDER BY id DESC LIMIT 1
            """,
            (agent_id, batch_filter),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Matching HA update job not found")
        conn.execute(
            "UPDATE jobs SET output=? WHERE id=? AND agent_id=?",
            (output, row["id"], agent_id),
        )
    return {"status": "ok"}

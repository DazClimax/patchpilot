import base64
import json
import os
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from deps import _get_db_ctx, _hash_token, require_role
router = APIRouter()


@router.post("/api/agents/{agent_id}/jobs/{job_id}/cancel", dependencies=[Depends(require_role("admin", "user"))])
def cancel_job(agent_id: str, job_id: int):
    with _get_db_ctx() as conn:
        row = conn.execute(
            "SELECT status FROM jobs WHERE id=? AND agent_id=?",
            (job_id, agent_id),
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


@router.post("/api/agents/{agent_id}/jobs/cancel-pending", dependencies=[Depends(require_role("admin", "user"))])
def cancel_pending_jobs(agent_id: str):
    from app import _cache_invalidate

    with _get_db_ctx() as conn:
        result = conn.execute(
            "UPDATE jobs SET status='failed', output=COALESCE(output,'') || '\n[cancelled by user]', "
            "finished=datetime('now','localtime') WHERE agent_id=? AND status='pending'",
            (agent_id,),
        )
        count = result.rowcount
    _cache_invalidate("dashboard")
    return {"status": "ok", "cancelled": count}


@router.get("/api/dashboard", dependencies=[Depends(require_role("admin", "user", "readonly"))])
def api_dashboard():
    from app import (
        _AGENT_TARGET_VERSION,
        _CACHE_TTL_DASHBOARD,
        _HA_AGENT_TARGET_VERSION,
        _agent_online_status,
        _cache_get,
        _cache_set,
        _redact_agent_record,
        _resolve_ha_job_display_status,
    )

    cached = _cache_get("dashboard")
    if cached is not None:
        return cached

    with _get_db_ctx() as conn:
        agents = conn.execute(
            """SELECT agents.*,
               (SELECT COUNT(*) FROM packages p WHERE p.agent_id = agents.id) AS live_pending_count,
               (julianday('now','localtime') - julianday(last_seen)) * 86400 as seconds_ago
               FROM agents ORDER BY hostname"""
        ).fetchall()
        last_jobs = conn.execute(
            """SELECT j.agent_id, j.type, j.status, j.finished, j.started, j.params
               FROM jobs j
               INNER JOIN (
                   SELECT agent_id, MAX(id) as max_id
                   FROM jobs
                   GROUP BY agent_id
               ) latest ON j.id = latest.max_id"""
        ).fetchall()
        package_rows = conn.execute("SELECT agent_id, name, source_id FROM packages").fetchall()

    package_state_by_agent = {}
    for row in package_rows:
        state = package_state_by_agent.setdefault(row["agent_id"], {"names": set(), "source_ids": set()})
        if row["name"]:
            state["names"].add(str(row["name"]))
        if row["source_id"]:
            state["source_ids"].add(str(row["source_id"]))

    last_job_map = {row["agent_id"]: dict(row) for row in last_jobs}
    result = []
    for agent in agents:
        row = _redact_agent_record(dict(agent))
        row["pending_count"] = row.pop("live_pending_count", row.get("pending_count", 0))
        last_job = last_job_map.get(row["id"])
        if last_job:
            display = _resolve_ha_job_display_status(
                dict(last_job),
                package_state_by_agent.get(row["id"], {"names": set(), "source_ids": set()}),
                row.get("last_seen"),
            )
            row["last_job_type"] = last_job["type"]
            row["last_job_status"] = display["status"]
            row["last_job_finished"] = display["finished"]
            last_job = {**dict(last_job), **display}
        row = _agent_online_status(row, last_job)
        result.append(row)

    online = sum(1 for agent in result if agent.get("effective_online"))
    reboot_needed = sum(1 for agent in result if agent.get("reboot_required"))
    total_pending = sum(agent.get("pending_count") or 0 for agent in result)
    payload = {
        "agents": result,
        "agent_target_version": _AGENT_TARGET_VERSION,
        "ha_agent_target_version": _HA_AGENT_TARGET_VERSION,
        "stats": {
            "online": online,
            "total": len(result),
            "reboot_needed": reboot_needed,
            "total_pending": total_pending,
        },
    }
    _cache_set("dashboard", payload, _CACHE_TTL_DASHBOARD)
    return payload


@router.post("/api/register-key", dependencies=[Depends(require_role("admin"))])
def api_register_key_generate():
    from app import _generate_register_key

    key, remaining = _generate_register_key()
    return {"key": key, "expires_in": int(remaining)}


@router.get("/api/register-key", dependencies=[Depends(require_role("admin"))])
def api_register_key_status():
    from app import _get_active_register_key

    key, remaining = _get_active_register_key()
    if key is None:
        return {"active": False, "key": None, "expires_in": 0}
    return {"active": True, "key": None, "expires_in": int(remaining)}


@router.get("/api/deploy/bootstrap", dependencies=[Depends(require_role("admin"))])
def api_deploy_bootstrap():
    from app import _SSL_DIR, _get_ca_rollover_public_pem

    cert = _SSL_DIR / "cert.pem"
    ca_pem_b64 = ""
    if cert.exists():
        ca_pem_b64 = base64.b64encode(cert.read_bytes()).decode()
    ca_rollover_pub_pem_b64 = base64.b64encode(_get_ca_rollover_public_pem()).decode()
    return {
        "ca_pem_b64": ca_pem_b64,
        "ca_rollover_pub_pem_b64": ca_rollover_pub_pem_b64,
    }


@router.get("/api/ping")
def api_ping():
    return {"status": "ok", "utc": datetime.now(timezone.utc).isoformat()}


@router.get("/api/server-time")
def api_server_time():
    import zoneinfo
    from scheduler import get_scheduler_timezone

    tz = zoneinfo.ZoneInfo(get_scheduler_timezone())
    now = datetime.now(tz)
    return {
        "local": now.strftime("%Y-%m-%d %H:%M:%S"),
        "tz": now.strftime("%Z"),
        "iso": now.isoformat(),
    }


@router.get("/api/agents/{agent_id}", dependencies=[Depends(require_role("admin", "user", "readonly"))])
def api_agent(agent_id: str, days: int = 7, limit: int = 10, offset: int = 0):
    from app import (
        _AGENT_TARGET_VERSION,
        _CACHE_TTL_AGENT,
        _HA_AGENT_TARGET_VERSION,
        _agent_online_status,
        _cache_get,
        _cache_set,
        _redact_agent_record,
        _resolve_ha_job_display_status,
    )

    days = 0 if days <= 0 else min(days, 365)
    limit = 0 if limit <= 0 else min(limit, 500)
    offset = max(offset, 0)
    cache_key = f"agent:{agent_id}:days:{days}:limit:{limit}:offset:{offset}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    with _get_db_ctx() as conn:
        agent = conn.execute(
            """SELECT agents.*,
               (SELECT COUNT(*) FROM packages p WHERE p.agent_id = agents.id) AS live_pending_count,
               (julianday('now','localtime') - julianday(last_seen)) * 86400 as seconds_ago
               FROM agents WHERE id=?""",
            (agent_id,),
        ).fetchone()
        if not agent:
            raise HTTPException(status_code=404)
        packages = conn.execute("SELECT * FROM packages WHERE agent_id=? ORDER BY name", (agent_id,)).fetchall()
        jobs_where = " WHERE agent_id=?"
        jobs_params = [agent_id]
        if days > 0:
            jobs_where += " AND datetime(created) >= datetime('now','localtime', ?)"
            jobs_params.append(f"-{days} days")
        total_jobs = conn.execute(
            f"SELECT COUNT(*) AS count FROM jobs{jobs_where}",
            jobs_params,
        ).fetchone()["count"]
        jobs_query = f"SELECT * FROM jobs{jobs_where} ORDER BY id DESC"
        if limit > 0:
            jobs_query += " LIMIT ? OFFSET ?"
            jobs_params = [*jobs_params, limit, offset]
        jobs = conn.execute(jobs_query, jobs_params).fetchall()

    now_local = datetime.now()
    agent_dict = _redact_agent_record(dict(agent))
    agent_dict["pending_count"] = agent_dict.pop("live_pending_count", agent_dict.get("pending_count", 0))
    agent_last_seen_raw = agent_dict.get("last_seen")
    agent_last_seen_dt = None
    if agent_last_seen_raw:
        try:
            agent_last_seen_dt = datetime.strptime(agent_last_seen_raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            agent_last_seen_dt = None
    health_job_types = {
        "patch",
        "dist_upgrade",
        "force_patch",
        "refresh_updates",
        "reboot",
        "update_agent",
        "ha_trigger_agent_update",
        "ha_core_update",
        "ha_backup_update",
        "ha_supervisor_update",
        "ha_os_update",
        "ha_addon_update",
        "ha_addons_update",
        "ha_entity_update",
    }
    package_state = {
        "names": {str(pkg["name"]) for pkg in packages if pkg["name"]},
        "source_ids": {str(pkg["source_id"]) for pkg in packages if pkg["source_id"]},
    }
    latest_job_for_connectivity = None
    jobs_payload = []
    for job_row in jobs:
        job = dict(job_row)
        job.update(_resolve_ha_job_display_status(job, package_state, agent_dict.get("last_seen")))
        if latest_job_for_connectivity is None:
            latest_job_for_connectivity = dict(job)
        health_status = None
        if job.get("status") == "done" and job.get("type") in health_job_types:
            finished_raw = job.get("finished")
            finished_dt = None
            if finished_raw:
                try:
                    finished_dt = datetime.strptime(finished_raw, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    finished_dt = None
            if finished_dt:
                if agent_last_seen_dt and agent_last_seen_dt >= finished_dt:
                    health_status = "ok"
                elif (now_local - finished_dt).total_seconds() <= 600:
                    health_status = "pending"
                else:
                    health_status = "stale"
        job["health_status"] = health_status
        jobs_payload.append(job)

    agent_dict = _agent_online_status(agent_dict, latest_job_for_connectivity)
    payload = {
        "agent": agent_dict,
        "agent_target_version": _AGENT_TARGET_VERSION,
        "ha_agent_target_version": _HA_AGENT_TARGET_VERSION,
        "packages": [dict(pkg) for pkg in packages],
        "jobs": jobs_payload,
        "jobs_total": total_jobs,
        "jobs_has_more": False if limit == 0 else (offset + len(jobs_payload) < total_jobs),
    }
    _cache_set(cache_key, payload, _CACHE_TTL_AGENT)
    return payload


@router.post("/api/agents/ping-targets", dependencies=[Depends(require_role("admin"))])
async def api_create_ping_target(request: Request):
    from app import (
        _agent_online_status,
        _allocate_agent_id,
        _cache_invalidate,
        _redact_agent_record,
        _validate_agent_id,
        _validate_ping_target_fields,
        trigger_ping_check_for_agent,
    )

    data = await request.json()
    hostname, address = _validate_ping_target_fields(
        data.get("hostname"),
        data.get("address") or data.get("ip"),
    )
    requested_id = str(data.get("id") or "").strip()
    if requested_id:
        _validate_agent_id(requested_id)
    with _get_db_ctx() as conn:
        agent_id = requested_id or _allocate_agent_id(conn, hostname)
        if requested_id and conn.execute("SELECT 1 FROM agents WHERE id=?", (agent_id,)).fetchone():
            raise HTTPException(status_code=409, detail=f"Agent ID '{agent_id}' already exists")
        conn.execute(
            """
            INSERT INTO agents (
                id, hostname, ip, os_pretty, package_manager, agent_version,
                agent_type, capabilities, protocol, token
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                hostname,
                address,
                "Ping monitor",
                None,
                "",
                "ping",
                "",
                "icmp",
                _hash_token(secrets.token_hex(32)),
            ),
        )
    reachable = trigger_ping_check_for_agent(agent_id)
    _cache_invalidate("dashboard", f"agent:{agent_id}")
    with _get_db_ctx() as conn:
        row = conn.execute(
            """
            SELECT agents.*,
                   0 AS live_pending_count,
                   (julianday('now','localtime') - julianday(last_seen)) * 86400 as seconds_ago
            FROM agents WHERE id=?
            """,
            (agent_id,),
        ).fetchone()
    agent_payload = _agent_online_status(_redact_agent_record(dict(row)))
    agent_payload["pending_count"] = agent_payload.pop("live_pending_count", 0)
    return {"status": "created", "reachable": reachable, "agent": agent_payload}


@router.post("/api/agents/{agent_id}/ping-check", dependencies=[Depends(require_role("admin", "user"))])
def api_ping_check(agent_id: str):
    from app import _cache_invalidate, trigger_ping_check_for_agent

    with _get_db_ctx() as conn:
        row = conn.execute("SELECT agent_type FROM agents WHERE id=?", (agent_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")
        if str(row["agent_type"] or "") != "ping":
            raise HTTPException(status_code=422, detail="Ping checks are only available for ping-only targets")
    reachable = trigger_ping_check_for_agent(agent_id)
    _cache_invalidate("dashboard", f"agent:{agent_id}")
    return {"status": "ok", "reachable": reachable}


@router.post("/api/agents/{agent_id}/jobs", dependencies=[Depends(require_role("admin", "user"))])
async def create_job(agent_id: str, request: Request):
    from app import ALLOWED_JOB_TYPES, _MANAGED_AGENT_TYPES, _cache_invalidate

    data = await request.json()
    job_type = data.get("type")
    if job_type not in ALLOWED_JOB_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid job type. Allowed: {sorted(ALLOWED_JOB_TYPES)}")
    params = data.get("params", {})
    with _get_db_ctx() as conn:
        agent = conn.execute("SELECT id, agent_type, capabilities FROM agents WHERE id=?", (agent_id,)).fetchone()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        if str(agent["agent_type"] or "linux") not in _MANAGED_AGENT_TYPES:
            raise HTTPException(status_code=422, detail="This target is monitor-only and does not support jobs")
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
                "ha_entity_update": "ha_entity_update",
            }.get(job_type)
            if job_type == "ha_backup_update" and not {"ha_backup", "ha_core_update"}.issubset(capabilities):
                raise HTTPException(status_code=422, detail="Agent does not support ha_backup_update")
            if job_type == "ha_trigger_agent_update" and "ha_agent_auto_update" not in capabilities:
                raise HTTPException(status_code=422, detail="Agent does not support ha_trigger_agent_update")
            if required and required not in capabilities:
                raise HTTPException(status_code=422, detail=f"Agent does not support {job_type}")
        conn.execute(
            "INSERT INTO jobs (agent_id, type, params, created) VALUES (?, ?, ?, datetime('now','localtime'))",
            (agent_id, job_type, json.dumps(params)),
        )
    _cache_invalidate("dashboard", f"agent:{agent_id}")
    return {"status": "queued"}


@router.post("/api/agents/{agent_id}/config-review/ack", dependencies=[Depends(require_role("admin", "user"))])
def api_ack_config_review(agent_id: str):
    from app import _cache_invalidate

    with _get_db_ctx() as conn:
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


@router.delete("/api/agents/{agent_id}", dependencies=[Depends(require_role("admin"))])
def delete_agent(agent_id: str):
    from app import _cache_invalidate, _last_heartbeat
    from scheduler import _offline_notified

    with _get_db_ctx() as conn:
        conn.execute("DELETE FROM agents WHERE id=?", (agent_id,))
    _last_heartbeat.pop(agent_id, None)
    _offline_notified.discard(agent_id)
    _cache_invalidate("dashboard", f"agent:{agent_id}")
    return {"status": "deleted"}


@router.patch("/api/agents/{agent_id}/rename", dependencies=[Depends(require_role("admin"))])
async def rename_agent(agent_id: str, request: Request):
    from app import _cache_invalidate, _clear_alias, _last_heartbeat, _store_alias, _validate_agent_id
    from scheduler import _offline_notified

    data = await request.json()
    new_id = (data.get("new_id") or "").strip()
    _validate_agent_id(new_id)
    if new_id == agent_id:
        return {"status": "unchanged"}
    with _get_db_ctx() as conn:
        existing = conn.execute("SELECT id FROM agents WHERE id=?", (new_id,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail=f"Agent ID '{new_id}' already exists")
        old = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        if not old:
            raise HTTPException(status_code=404, detail="Agent not found")
        cols = [key for key in dict(old).keys() if key != "id"]
        placeholders = ", ".join(f"{col}" for col in cols)
        qs = ", ".join("?" for _ in cols)
        values = [dict(old)[col] for col in cols]
        conn.execute(f"INSERT INTO agents (id, {placeholders}) VALUES (?, {qs})", [new_id] + values)
        conn.execute("UPDATE jobs SET agent_id=? WHERE agent_id=?", (new_id, agent_id))
        conn.execute("UPDATE packages SET agent_id=? WHERE agent_id=?", (new_id, agent_id))
        conn.execute("DELETE FROM agents WHERE id=?", (agent_id,))
        schedules = conn.execute("SELECT id, target FROM schedules").fetchall()
        for sched in schedules:
            targets = [target.strip() for target in sched["target"].split(",")]
            if agent_id in targets:
                new_targets = [new_id if target == agent_id else target for target in targets]
                conn.execute(
                    "UPDATE schedules SET target=? WHERE id=?",
                    (",".join(new_targets), sched["id"]),
                )
    _last_heartbeat[new_id] = _last_heartbeat.pop(agent_id, 0)
    with _get_db_ctx() as conn2:
        conn2.execute("UPDATE rename_aliases SET new_id=? WHERE new_id=?", (new_id, agent_id))
    _store_alias(agent_id, new_id)
    if agent_id in _offline_notified:
        _offline_notified.discard(agent_id)
        _offline_notified.add(new_id)
    _cache_invalidate("dashboard", f"agent:{agent_id}", f"agent:{new_id}")
    return {"status": "renamed", "old_id": agent_id, "new_id": new_id}


@router.patch("/api/agents/{agent_id}/tags", dependencies=[Depends(require_role("admin", "user"))])
async def set_agent_tags(agent_id: str, request: Request):
    from app import _TAG_RE, _cache_invalidate

    data = await request.json()
    raw_tags = data.get("tags", "")
    tags = ",".join(tag.strip() for tag in raw_tags.split(",") if tag.strip())
    for tag in tags.split(","):
        if tag and not _TAG_RE.match(tag):
            raise HTTPException(status_code=422, detail=f"Invalid tag: {tag!r}. Use a-z A-Z 0-9 . _ -")
    if len(tags) > 512:
        raise HTTPException(status_code=422, detail="Tags string exceeds 512 character limit")
    with _get_db_ctx() as conn:
        row = conn.execute("SELECT id FROM agents WHERE id=?", (agent_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")
        conn.execute("UPDATE agents SET tags=? WHERE id=?", (tags, agent_id))
    _cache_invalidate("dashboard", f"agent:{agent_id}")
    return {"status": "ok", "tags": tags}


@router.get("/api/schedules", dependencies=[Depends(require_role("admin", "user"))])
def api_schedules():
    from app import scheduler

    with _get_db_ctx() as conn:
        schedules = conn.execute("SELECT * FROM schedules ORDER BY id").fetchall()
        agents = conn.execute(
            "SELECT id, hostname FROM agents WHERE COALESCE(agent_type, 'linux') IN ('linux', 'haos') ORDER BY hostname"
        ).fetchall()
    schedule_list = []
    for schedule in schedules:
        row = dict(schedule)
        job = scheduler.get_job(str(row["id"]))
        if job and job.next_run_time:
            row["next_run"] = job.next_run_time.isoformat()
        schedule_list.append(row)
    return {"schedules": schedule_list, "agents": [dict(agent) for agent in agents]}


@router.post("/api/schedules", dependencies=[Depends(require_role("admin"))])
async def create_schedule(request: Request):
    from app import ALLOWED_JOB_TYPES, _validate_cron, _validate_schedule_target
    from scheduler import schedule_job

    data = await request.json()
    name = str(data.get("name", ""))[:128]
    cron = str(data.get("cron", ""))
    action = str(data.get("action", ""))
    target = str(data.get("target", ""))
    if not name:
        raise HTTPException(status_code=422, detail="Schedule name is required")
    if action not in ALLOWED_JOB_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid action. Allowed: {sorted(ALLOWED_JOB_TYPES)}")
    _validate_cron(cron)
    _validate_schedule_target(target)
    with _get_db_ctx() as conn:
        conn.execute(
            "INSERT INTO schedules (name, cron, action, target) VALUES (?,?,?,?)",
            (name, cron, action, target),
        )
        row = conn.execute("SELECT last_insert_rowid() as id").fetchone()
        schedule_job(row["id"], name, cron, action, target)
    return {"status": "created"}


@router.patch("/api/schedules/{sid}", dependencies=[Depends(require_role("admin"))])
async def toggle_schedule(sid: int, request: Request):
    from app import scheduler
    from scheduler import schedule_job

    data = await request.json()
    enabled = 1 if data.get("enabled") else 0
    with _get_db_ctx() as conn:
        row = conn.execute(
            "SELECT id, name, cron, action, target FROM schedules WHERE id=?",
            (sid,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Schedule not found")
        conn.execute("UPDATE schedules SET enabled=? WHERE id=?", (enabled, sid))
    if enabled:
        schedule_job(sid, row["name"], row["cron"], row["action"], row["target"])
    else:
        try:
            scheduler.remove_job(str(sid))
        except Exception:
            pass
    return {"status": "updated"}


@router.put("/api/schedules/{sid}", dependencies=[Depends(require_role("admin"))])
async def update_schedule(sid: int, request: Request):
    from app import scheduler
    from app import ALLOWED_JOB_TYPES, _validate_cron, _validate_schedule_target
    from scheduler import schedule_job

    data = await request.json()
    name = str(data.get("name", ""))[:128]
    cron = str(data.get("cron", ""))
    action = str(data.get("action", ""))
    target = str(data.get("target", ""))
    if not name:
        raise HTTPException(status_code=422, detail="Schedule name is required")
    if action not in ALLOWED_JOB_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid action. Allowed: {sorted(ALLOWED_JOB_TYPES)}")
    _validate_cron(cron)
    _validate_schedule_target(target)
    with _get_db_ctx() as conn:
        row = conn.execute("SELECT id, enabled FROM schedules WHERE id=?", (sid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Schedule not found")
        conn.execute(
            "UPDATE schedules SET name=?, cron=?, action=?, target=? WHERE id=?",
            (name, cron, action, target, sid),
        )
    if row["enabled"]:
        schedule_job(sid, name, cron, action, target)
    else:
        try:
            scheduler.remove_job(str(sid))
        except Exception:
            pass
    return {"status": "updated"}


@router.post("/api/schedules/{sid}/run", dependencies=[Depends(require_role("admin", "user"))])
def run_schedule_now(sid: int):
    with _get_db_ctx() as conn:
        row = conn.execute("SELECT action, target FROM schedules WHERE id=?", (sid,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    from scheduler import _run_scheduled_job

    _run_scheduled_job(sid, row["action"], row["target"])
    return {"status": "triggered"}


@router.delete("/api/schedules/{sid}", dependencies=[Depends(require_role("admin"))])
def delete_schedule(sid: int):
    from app import scheduler

    with _get_db_ctx() as conn:
        conn.execute("DELETE FROM schedules WHERE id=?", (sid,))
    try:
        scheduler.remove_job(str(sid))
    except Exception:
        pass
    return {"status": "deleted"}


@router.get("/api/alerts", dependencies=[Depends(require_role("admin", "user", "readonly"))])
def api_alerts():
    from app import _DISK_ALERT_THRESHOLD, _agent_online_status

    with _get_db_ctx() as conn:
        rows = conn.execute(
            """SELECT id, hostname, ip, agent_type, ping_failures, ping_last_checked,
               disk_total, disk_used,
               CAST((julianday('now','localtime') - julianday(last_seen)) * 86400 AS INTEGER) as seconds_ago
               FROM agents
               WHERE last_seen IS NOT NULL"""
        ).fetchall()
        last_jobs = conn.execute(
            """SELECT j.agent_id, j.type, j.status, j.created, j.started
               FROM jobs j
               INNER JOIN (
                   SELECT agent_id, MAX(id) as max_id
                   FROM jobs
                   GROUP BY agent_id
               ) latest ON j.id = latest.max_id"""
        ).fetchall()
    last_job_map = {row["agent_id"]: dict(row) for row in last_jobs}
    result = []
    for row in rows:
        row_dict = _agent_online_status(dict(row), last_job_map.get(row["id"]))
        if not row_dict.get("effective_online"):
            result.append(
                {
                    "hostname": row_dict["hostname"],
                    "ip": row_dict["ip"],
                    "offline_since_seconds": row_dict.get("seconds_ago") or 0,
                    "kind": "offline",
                }
            )
        elif (
            row_dict.get("disk_total")
            and row_dict.get("disk_used") is not None
            and row_dict["disk_total"] > 0
            and round(row_dict["disk_used"] / row_dict["disk_total"] * 100) >= _DISK_ALERT_THRESHOLD
        ):
            pct = round(row_dict["disk_used"] / row_dict["disk_total"] * 100)
            result.append(
                {
                    "hostname": row_dict["hostname"],
                    "ip": row_dict["ip"],
                    "offline_since_seconds": 0,
                    "kind": "disk",
                    "disk_percent": pct,
                }
            )
    result.sort(key=lambda item: item["offline_since_seconds"], reverse=True)
    return result


@router.get("/api/status/badge", dependencies=[Depends(require_role("admin", "user", "readonly"))])
def api_status_badge():
    from app import _agent_online_status

    with _get_db_ctx() as conn:
        agents = conn.execute(
            """SELECT
               id,
               agent_type,
               ping_failures,
               ping_last_checked,
               CAST((julianday('now','localtime') - julianday(last_seen)) * 86400 AS INTEGER) as seconds_ago
               FROM agents"""
        ).fetchall()
        last_jobs = conn.execute(
            """SELECT j.agent_id, j.type, j.status, j.created, j.started
               FROM jobs j
               INNER JOIN (
                   SELECT agent_id, MAX(id) as max_id
                   FROM jobs
                   GROUP BY agent_id
               ) latest ON j.id = latest.max_id"""
        ).fetchall()
    last_job_map = {row["agent_id"]: dict(row) for row in last_jobs}
    total = len(agents)
    online = sum(
        1
        for row in agents
        if _agent_online_status(dict(row), last_job_map.get(row["id"])).get("effective_online")
    )

    if total == 0 or online == 0:
        color = "#e05d44"
    elif online < total:
        color = "#dfb317"
    else:
        color = "#4c1"

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

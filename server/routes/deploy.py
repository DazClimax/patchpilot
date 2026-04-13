import base64
import hashlib
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse

from deps import _get_db_ctx, require_role
from scheduler import is_effectively_online

router = APIRouter()


@router.get("/agent/agent.py", include_in_schema=False)
def download_agent():
    from app import AGENT_DIR

    file_path = AGENT_DIR / "agent.py"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Agent not found")
    return FileResponse(file_path, media_type="text/x-python", filename="agent.py")


@router.get("/agent/agent.py.sha256", include_in_schema=False)
def download_agent_hash():
    from app import AGENT_DIR

    file_path = AGENT_DIR / "agent.py"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Agent not found")
    sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
    return Response(content=f"{sha256}  agent.py\n", media_type="text/plain")


@router.get("/agent/agent.py.sig", include_in_schema=False)
def download_agent_signature():
    from app import AGENT_DIR, _sign_ca_rollover_payload

    file_path = AGENT_DIR / "agent.py"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        sig_bytes = _sign_ca_rollover_payload(file_path.read_bytes())
        sig_b64 = base64.b64encode(sig_bytes).decode()
        return Response(content=f"{sig_b64}\n", media_type="text/plain")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Signing unavailable: {exc}")


@router.get("/agent/install.sh", include_in_schema=False)
def download_install_script():
    from app import AGENT_DIR

    file_path = AGENT_DIR / "install.sh"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Install script not found")
    return FileResponse(file_path, media_type="text/x-shellscript", filename="install.sh")


@router.get("/agent/ca.pem", include_in_schema=False)
def download_ca_cert():
    from app import _SSL_DIR

    file_path = _SSL_DIR / "cert.pem"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="CA certificate not generated yet")
    return FileResponse(file_path, media_type="application/x-pem-file", filename="ca.pem")


@router.get("/agent/ca.pem.sha256", include_in_schema=False)
def download_ca_hash():
    from app import _SSL_DIR

    file_path = _SSL_DIR / "cert.pem"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="CA certificate not generated yet")
    sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
    return Response(content=f"{sha}  ca.pem\n", media_type="text/plain")


@router.get("/agent/ca.pem.sig", include_in_schema=False)
def download_ca_signature():
    from app import _SSL_DIR, _sign_ca_rollover_payload

    file_path = _SSL_DIR / "cert.pem"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="CA certificate not generated yet")
    sig_b64 = base64.b64encode(_sign_ca_rollover_payload(file_path.read_bytes())).decode()
    return Response(content=f"{sig_b64}\n", media_type="text/plain")


@router.get("/agent/ca-rollover.pub", include_in_schema=False)
def download_ca_rollover_public_key():
    from app import _get_ca_rollover_public_pem

    return Response(content=_get_ca_rollover_public_pem(), media_type="application/x-pem-file")


@router.post("/api/settings/deploy-ssl", dependencies=[Depends(require_role("admin"))])
async def api_deploy_ssl_to_agents(request):
    from app import _SSL_DIR, _cache_invalidate, _get_ca_rollover_public_pem, _sign_ca_rollover_payload
    cert = _SSL_DIR / "cert.pem"
    if not cert.exists():
        raise HTTPException(status_code=400, detail="No certificate generated yet — generate one first")
    import uuid as _uuid

    batch_id = _uuid.uuid4().hex[:12]
    cert_bytes = cert.read_bytes()
    ca_pem_b64 = base64.b64encode(cert_bytes).decode()
    ca_sig_b64 = base64.b64encode(_sign_ca_rollover_payload(cert_bytes)).decode()
    rollover_pubkey_pem = _get_ca_rollover_public_pem().decode("utf-8")
    ca_sha256 = hashlib.sha256(cert_bytes).hexdigest()

    data = {}
    try:
        data = await request.json()
    except Exception:
        pass
    retry_batch = re.sub(r"[^a-fA-F0-9]", "", data.get("retry_batch", ""))

    with _get_db_ctx() as conn:
        if retry_batch:
            batch_filter = f'%\"batch\": \"{retry_batch}\"%'
            agents = conn.execute(
                """
                SELECT DISTINCT j.agent_id, a.hostname FROM jobs j
                JOIN agents a ON a.id = j.agent_id
                WHERE j.status = 'failed' AND j.params LIKE ?
                """,
                (batch_filter,),
            ).fetchall()
        else:
            agents = conn.execute(
                "SELECT id AS agent_id, hostname, COALESCE(agent_type, 'linux') AS agent_type "
                "FROM agents WHERE COALESCE(agent_type, 'linux') IN ('linux', 'haos')"
            ).fetchall()

        if not agents:
            raise HTTPException(status_code=422, detail="No agents to deploy to")
        count = 0
        for agent in agents:
            agent_id = agent["agent_id"] if "agent_id" in agent.keys() else agent["id"]
            agent_type = agent["agent_type"] if "agent_type" in agent.keys() else "linux"
            signed_ca_params = {
                "batch": batch_id,
                "ca_pem_b64": ca_pem_b64,
                "ca_sig_b64": ca_sig_b64,
                "ca_sha256": ca_sha256,
                "rollover_pubkey_pem": rollover_pubkey_pem,
            }
            if agent_type == "haos":
                params = json.dumps(signed_ca_params)
                job_type = "deploy_ssl"
            else:
                params = json.dumps(
                    {
                        "chain": "deploy_ssl",
                        "batch": batch_id,
                        "chain_params": signed_ca_params,
                    }
                )
                job_type = "update_agent"
            conn.execute(
                "INSERT INTO jobs (agent_id, type, params, created) VALUES (?, ?, ?, datetime('now','localtime'))",
                (agent_id, job_type, params),
            )
            count += 1
    _cache_invalidate("dashboard")
    return {"status": "deployed", "agent_count": count, "batch_id": batch_id}


@router.post("/api/agents/update-batch", dependencies=[Depends(require_role("admin"))])
async def api_update_agents_batch(request):
    from app import _cache_invalidate
    import uuid as _uuid

    batch_id = _uuid.uuid4().hex[:12]
    data = {}
    try:
        data = await request.json()
    except Exception:
        pass
    retry_batch = re.sub(r"[^a-fA-F0-9]", "", data.get("retry_batch", ""))
    requested_agent_ids = [
        re.sub(r"[^a-zA-Z0-9._:-]", "", str(agent_id))
        for agent_id in (data.get("agent_ids") or [])
        if str(agent_id).strip()
    ]
    requested_agent_ids = [agent_id for agent_id in requested_agent_ids if agent_id]

    with _get_db_ctx() as conn:
        if retry_batch:
            batch_filter = f'%\"batch\": \"{retry_batch}\"%'
            agents = conn.execute(
                """
                SELECT DISTINCT j.agent_id, a.hostname FROM jobs j
                JOIN agents a ON a.id = j.agent_id
                WHERE j.type IN ('update_agent', 'ha_trigger_agent_update') AND j.status = 'failed' AND j.params LIKE ?
                  AND a.last_seen IS NOT NULL
                  AND (julianday('now','localtime') - julianday(a.last_seen)) * 86400 < 120
                """,
                (batch_filter,),
            ).fetchall()
        else:
            if requested_agent_ids:
                placeholders = ",".join("?" for _ in requested_agent_ids)
                agents = conn.execute(
                    f"""
                    SELECT id AS agent_id, hostname, COALESCE(agent_type, 'linux') AS agent_type, COALESCE(capabilities, '') AS capabilities
                    FROM agents
                    WHERE id IN ({placeholders})
                      AND COALESCE(agent_type, 'linux') IN ('linux', 'haos')
                      AND last_seen IS NOT NULL
                      AND (julianday('now','localtime') - julianday(last_seen)) * 86400 < 120
                    """,
                    requested_agent_ids,
                ).fetchall()
            else:
                agents = conn.execute(
                    """
                    SELECT id AS agent_id, hostname, COALESCE(agent_type, 'linux') AS agent_type, COALESCE(capabilities, '') AS capabilities
                    FROM agents
                    WHERE COALESCE(agent_type, 'linux') IN ('linux', 'haos')
                      AND last_seen IS NOT NULL
                      AND (julianday('now','localtime') - julianday(last_seen)) * 86400 < 120
                    """
                ).fetchall()

        if not agents:
            raise HTTPException(status_code=422, detail="No agents to update")

        count = 0
        for agent in agents:
            agent_id = agent["agent_id"] if "agent_id" in agent.keys() else agent["id"]
            agent_type = agent["agent_type"] if "agent_type" in agent.keys() else "linux"
            capabilities = set(filter(None, str(agent["capabilities"] or "").split(",")))
            if agent_type == "haos":
                if "ha_agent_auto_update" not in capabilities:
                    continue
                job_type = "ha_trigger_agent_update"
            else:
                job_type = "update_agent"
            params = json.dumps({"batch": batch_id})
            conn.execute(
                "INSERT INTO jobs (agent_id, type, params, created) VALUES (?, ?, ?, datetime('now','localtime'))",
                (agent_id, job_type, params),
            )
            count += 1
        if count == 0:
            raise HTTPException(status_code=422, detail="No agents to update")
    _cache_invalidate("dashboard")
    return {"status": "queued", "agent_count": count, "batch_id": batch_id}


@router.get("/api/settings/deploy-ssl/status", dependencies=[Depends(require_role("admin"))])
def api_deploy_ssl_status(batch: str = ""):
    batch = re.sub(r"[^a-fA-F0-9]", "", batch or "")
    if not batch:
        return {"agents": [], "total": 0, "completed": 0}

    batch_filter = f'%\"batch\": \"{batch}\"%'
    with _get_db_ctx() as conn:
        ssl_rows = conn.execute(
            """
            SELECT j.agent_id, a.hostname, j.type, j.status, j.output, j.finished, j.created, j.started,
                   CAST((julianday('now','localtime') - julianday(a.last_seen)) * 86400 AS INTEGER) AS seconds_ago
            FROM jobs j JOIN agents a ON a.id = j.agent_id
            WHERE j.type = 'deploy_ssl' AND j.params LIKE ?
            """,
            (batch_filter,),
        ).fetchall()
        ssl_map = {row["agent_id"]: row for row in ssl_rows}
        upd_rows = conn.execute(
            """
            SELECT j.agent_id, a.hostname, j.type, j.status, j.output, j.finished, j.created, j.started,
                   CAST((julianday('now','localtime') - julianday(a.last_seen)) * 86400 AS INTEGER) AS seconds_ago
            FROM jobs j JOIN agents a ON a.id = j.agent_id
            WHERE j.type IN ('update_agent', 'ha_trigger_agent_update') AND j.params LIKE ?
            """,
            (batch_filter,),
        ).fetchall()

    agents = []
    seen_agent_ids = set()
    for row in upd_rows:
        agent_id = row["agent_id"]
        seen_agent_ids.add(agent_id)
        is_online = is_effectively_online(row["seconds_ago"], dict(row))
        if agent_id in ssl_map:
            ssl_row = ssl_map[agent_id]
            phase = "done" if ssl_row["status"] == "done" else "failed" if ssl_row["status"] == "failed" else "deploying"
            agents.append(
                {
                    "agent_id": agent_id,
                    "hostname": ssl_row["hostname"],
                    "status": ssl_row["status"],
                    "phase": phase,
                    "output": ssl_row["output"] or "",
                    "finished": ssl_row["finished"],
                    "online": is_effectively_online(ssl_row["seconds_ago"], dict(ssl_row)),
                }
            )
        else:
            phase = "updating" if row["status"] in ("pending", "running") else ("failed" if row["status"] == "failed" else "waiting")
            agents.append(
                {
                    "agent_id": agent_id,
                    "hostname": row["hostname"],
                    "status": row["status"] if row["status"] == "failed" else phase,
                    "phase": phase,
                    "output": row["output"] or "" if row["status"] == "failed" else "",
                    "finished": row["finished"],
                    "online": is_online,
                }
            )
    for agent_id, ssl_row in ssl_map.items():
        if agent_id in seen_agent_ids:
            continue
        phase = "done" if ssl_row["status"] == "done" else "failed" if ssl_row["status"] == "failed" else "deploying"
        agents.append(
            {
                "agent_id": agent_id,
                "hostname": ssl_row["hostname"],
                "status": ssl_row["status"],
                "phase": phase,
                "output": ssl_row["output"] or "",
                "finished": ssl_row["finished"],
                "online": is_effectively_online(ssl_row["seconds_ago"], dict(ssl_row)),
            }
        )
    agents.sort(key=lambda item: (not item["online"], item["hostname"]))
    total_online = sum(1 for item in agents if item["online"])
    total = len(agents)
    done = sum(1 for item in agents if item["online"] and item["status"] in ("done", "failed"))
    return {"agents": agents, "total": total, "total_online": total_online, "completed": done}


@router.get("/api/agents/update-batch/status", dependencies=[Depends(require_role("admin"))])
def api_update_agents_batch_status(batch: str = ""):
    from app import _AGENT_TARGET_VERSION, _HA_AGENT_TARGET_VERSION

    batch = re.sub(r"[^a-fA-F0-9]", "", batch or "")
    if not batch:
        return {"agents": [], "total": 0, "completed": 0}

    batch_filter = f'%\"batch\": \"{batch}\"%'
    with _get_db_ctx() as conn:
        rows = conn.execute(
            """
            SELECT j.agent_id, a.hostname, a.agent_version, j.type, j.status, j.output, j.finished, j.created, j.started,
                   CAST((julianday('now','localtime') - julianday(a.last_seen)) * 86400 AS INTEGER) AS seconds_ago
            FROM jobs j JOIN agents a ON a.id = j.agent_id
            WHERE j.type IN ('update_agent', 'ha_trigger_agent_update') AND j.params LIKE ?
            """,
            (batch_filter,),
        ).fetchall()

    agents = []
    for row in rows:
        if row["type"] == "ha_trigger_agent_update":
            if row["status"] == "failed":
                phase = "failed"
                status = "failed"
            elif row["status"] in ("pending", "running"):
                phase = "triggering"
                status = row["status"]
            elif (row["agent_version"] or "").strip() == _HA_AGENT_TARGET_VERSION:
                phase = "done"
                status = "done"
            else:
                phase = "waiting"
                status = "running"
        else:
            if row["status"] == "failed":
                phase = "failed"
                status = "failed"
            elif (row["agent_version"] or "").strip() == _AGENT_TARGET_VERSION:
                phase = "done"
                status = "done"
            elif row["status"] in ("pending", "running"):
                phase = "updating"
                status = row["status"]
            else:
                phase = "waiting"
                status = "running"
        agents.append(
            {
                "agent_id": row["agent_id"],
                "hostname": row["hostname"],
                "job_type": row["type"],
                "status": status,
                "phase": phase,
                "output": row["output"] or "",
                "finished": row["finished"],
                "online": is_effectively_online(row["seconds_ago"], dict(row)),
            }
        )

    agents.sort(key=lambda item: (not item["online"], item["hostname"]))
    total_online = sum(1 for item in agents if item["online"])
    total = len(agents)
    done = sum(1 for item in agents if item["online"] and item["status"] in ("done", "failed"))
    return {"agents": agents, "total": total, "total_online": total_online, "completed": done}

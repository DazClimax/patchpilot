#!/usr/bin/env python3
import hashlib
import json
import os
import platform
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request as urlreq
from pathlib import Path

OPTIONS_FILE = Path("/data/options.json")
STATE_FILE = Path("/data/patchpilot_state.json")
CA_FILE = Path("/data/patchpilot_ca.pem")
SUPERVISOR_URL = "http://supervisor"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")


def load_options() -> dict:
    if not OPTIONS_FILE.exists():
      raise RuntimeError("Missing /data/options.json")
    return json.loads(OPTIONS_FILE.read_text())


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))
    STATE_FILE.chmod(0o600)


def make_ssl_context(ca_pem: str) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if ca_pem.strip():
        CA_FILE.write_text(ca_pem.strip() + "\n")
        CA_FILE.chmod(0o600)
        ctx.load_verify_locations(cafile=str(CA_FILE))
    return ctx


def request_json(method: str, url: str, *, data=None, headers=None, ssl_ctx=None):
    headers = headers or {}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urlreq.Request(url, method=method, data=body, headers=headers)
    with urlreq.urlopen(req, timeout=60, context=ssl_ctx) as resp:
        raw = resp.read()
    return json.loads(raw or b"{}")


def request_text(method: str, url: str, *, data=None, headers=None, ssl_ctx=None) -> str:
    headers = headers or {}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urlreq.Request(url, method=method, data=body, headers=headers)
    with urlreq.urlopen(req, timeout=60, context=ssl_ctx) as resp:
        return resp.read().decode()


def supervisor_json(method: str, path: str, data=None):
    if not SUPERVISOR_TOKEN:
        raise RuntimeError("SUPERVISOR_TOKEN not available")
    return request_json(
        method,
        f"{SUPERVISOR_URL}{path}",
        data=data,
        headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
    )


def get_core_info() -> dict:
    return supervisor_json("GET", "/core/info").get("data", {})


def get_host_info() -> dict:
    return supervisor_json("GET", "/host/info").get("data", {})


def get_pending_updates() -> list[dict]:
    core = get_core_info()
    if not core.get("update_available"):
        return []
    return [{
        "name": "home-assistant-core",
        "current": core.get("version"),
        "new": core.get("version_latest"),
    }]


def register(server: str, register_key: str, agent_id: str, ssl_ctx):
    payload = {
        "id": agent_id or socket.gethostname(),
        "hostname": socket.gethostname(),
        "ip": "homeassistant.local",
        "os_pretty": "Home Assistant OS",
        "kernel": platform.release(),
        "arch": platform.machine(),
        "package_manager": "haos",
        "agent_type": "haos",
        "capabilities": "ha_backup,ha_core_update",
        "register_key": register_key,
    }
    data = request_json("POST", f"{server}/api/agents/register", data=payload, ssl_ctx=ssl_ctx)
    return data["agent_id"], data["token"]


def heartbeat(server: str, agent_id: str, token: str, ssl_ctx):
    core = get_core_info()
    host = get_host_info()
    payload = {
        "hostname": host.get("hostname") or socket.gethostname(),
        "ip": host.get("hostname") or "homeassistant.local",
        "os_pretty": "Home Assistant OS",
        "kernel": host.get("kernel") or platform.release(),
        "arch": platform.machine(),
        "package_manager": "haos",
        "agent_type": "haos",
        "capabilities": "ha_backup,ha_core_update",
        "packages": get_pending_updates(),
        "reboot_required": 0,
        "uptime_seconds": None,
    }
    return request_json(
        "POST",
        f"{server}/api/agents/{agent_id}/heartbeat",
        data=payload,
        headers={"x-token": token},
        ssl_ctx=ssl_ctx,
    )


def poll_jobs(server: str, agent_id: str, token: str, ssl_ctx):
    return request_json(
        "GET",
        f"{server}/api/agents/{agent_id}/jobs",
        headers={"x-token": token},
        ssl_ctx=ssl_ctx,
    ) or []


def report_result(server: str, agent_id: str, token: str, job_id: int, status: str, output: str, ssl_ctx):
    request_json(
        "POST",
        f"{server}/api/agents/{agent_id}/jobs/{job_id}/result",
        data={"status": status, "output": output},
        headers={"x-token": token},
        ssl_ctx=ssl_ctx,
    )


def run_job(job: dict) -> tuple[str, str]:
    jtype = job["type"]
    params = job.get("params") or {}
    if jtype == "ha_backup":
        result = supervisor_json("POST", "/backups/new/full", {
            "name": f"PatchPilot backup {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "background": False,
        })
        data = result.get("data", {})
        return "done", f"Backup created: {data.get('slug', 'unknown')}"
    if jtype == "ha_core_update":
        version = params.get("version")
        payload = {"backup": False}
        if version:
            payload["version"] = version
        result = supervisor_json("POST", "/core/update", payload)
        data = result.get("data", {})
        return "done", f"Home Assistant Core update started{f' -> {version}' if version else ''}. Response: {json.dumps(data)}"
    if jtype == "ha_backup_update":
        version = params.get("version")
        payload = {"backup": True}
        if version:
            payload["version"] = version
        result = supervisor_json("POST", "/core/update", payload)
        data = result.get("data", {})
        return "done", f"Home Assistant Core backup+update started{f' -> {version}' if version else ''}. Response: {json.dumps(data)}"
    return "failed", f"Unknown job type: {jtype}"


def main():
    opts = load_options()
    server = opts.get("patchpilot_server", "").rstrip("/")
    register_key = opts.get("register_key", "")
    agent_id = opts.get("agent_id", "").strip()
    poll_interval = int(opts.get("poll_interval", 30) or 30)
    ca_pem = opts.get("ca_pem", "").strip()
    if not server:
        raise RuntimeError("patchpilot_server is required")
    if not register_key:
        raise RuntimeError("register_key is required")

    ssl_ctx = make_ssl_context(ca_pem)
    state = load_state()
    agent_id = state.get("agent_id") or agent_id or socket.gethostname()
    token = state.get("token", "")
    if not token:
        agent_id, token = register(server, register_key, agent_id, ssl_ctx)
        state.update({"agent_id": agent_id, "token": token})
        save_state(state)

    last_heartbeat = 0
    while True:
        try:
            if last_heartbeat <= 0:
                heartbeat(server, agent_id, token, ssl_ctx)
                last_heartbeat = poll_interval
            jobs = poll_jobs(server, agent_id, token, ssl_ctx)
            for job in jobs:
                status, output = run_job(job)
                report_result(server, agent_id, token, job["id"], status, output, ssl_ctx)
                heartbeat(server, agent_id, token, ssl_ctx)
        except urllib.error.HTTPError as err:
            print(f"[patchpilot-haos] HTTP {err.code}: {err.read().decode(errors='ignore')}", file=sys.stderr)
        except Exception as err:
            print(f"[patchpilot-haos] {err}", file=sys.stderr)
        time.sleep(10)
        last_heartbeat -= 10


if __name__ == "__main__":
    main()

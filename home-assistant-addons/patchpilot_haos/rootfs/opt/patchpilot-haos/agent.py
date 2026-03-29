#!/usr/bin/env python3
import hashlib
import ipaddress
import json
import os
import platform
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request as urlreq
from datetime import datetime
from urllib.parse import urlparse
from pathlib import Path

OPTIONS_FILE = Path("/data/options.json")
STATE_FILE = Path("/data/patchpilot_state.json")
CA_FILE = Path("/data/patchpilot_ca.pem")
SUPERVISOR_URL = "http://supervisor"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
SELF_ADDON_HINT = "patchpilot_haos"
AGENT_VERSION = "1.1"
AUTO_UPDATE_CAPABILITY = "ha_agent_auto_update"
BASE_CAPABILITIES = (
    "ha_backup",
    "ha_core_update",
    "ha_supervisor_update",
    "ha_os_update",
    "ha_addon_update",
    "ha_addons_update",
)


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


def homeassistant_request(method: str, path: str, data=None):
    if not SUPERVISOR_TOKEN:
        raise RuntimeError("SUPERVISOR_TOKEN not available")
    url = f"{SUPERVISOR_URL}/core/api{path}"
    headers = {"Authorization": f"Bearer {SUPERVISOR_TOKEN}"}
    try:
        return request_json(method, url, data=data, headers=headers)
    except json.JSONDecodeError:
        return {"result": "ok"}


def get_core_info() -> dict:
    return supervisor_json("GET", "/core/info").get("data", {})


def get_supervisor_info() -> dict:
    return supervisor_json("GET", "/supervisor/info").get("data", {})


def get_os_info() -> dict:
    return supervisor_json("GET", "/os/info").get("data", {})


def get_host_info() -> dict:
    return supervisor_json("GET", "/host/info").get("data", {})


def get_network_info() -> dict:
    return supervisor_json("GET", "/network/info").get("data", {})


def get_addons_info() -> list[dict]:
    return supervisor_json("GET", "/addons").get("data", {}).get("addons", [])


def is_self_addon(slug: str) -> bool:
    normalized = (slug or "").strip().lower()
    return normalized.endswith(SELF_ADDON_HINT)


def build_capabilities(opts: dict) -> str:
    values = list(BASE_CAPABILITIES)
    if str(opts.get("agent_update_webhook_id") or "").strip():
        values.append(AUTO_UPDATE_CAPABILITY)
    return ",".join(values)


def _normalize_ip(value: str) -> str | None:
    ip = (value or "").split("/")[0].strip()
    if not ip or ip in {"127.0.0.1", "0.0.0.0"}:
        return None
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if parsed.version != 4:
        return None
    return str(parsed)


def _score_ip(ip: str) -> int:
    parsed = ipaddress.ip_address(ip)
    if parsed.is_loopback or parsed.is_link_local:
        return -1
    if parsed in ipaddress.ip_network("192.168.0.0/16"):
        return 400
    if parsed in ipaddress.ip_network("10.0.0.0/8"):
        return 300
    if parsed in ipaddress.ip_network("172.16.0.0/12"):
        return 200
    if parsed.is_private:
        return 100
    return 0


def _iter_interface_values(interfaces) -> list[dict]:
    if isinstance(interfaces, list):
        return [iface for iface in interfaces if isinstance(iface, dict)]
    if isinstance(interfaces, dict):
        values: list[dict] = []
        for name, iface in interfaces.items():
            if isinstance(iface, dict):
                entry = dict(iface)
                entry.setdefault("name", name)
                values.append(entry)
        return values
    return []


def _is_virtual_interface(iface: dict) -> bool:
    name = str(iface.get("name") or "").lower()
    iface_id = str(iface.get("id") or "").lower()
    iface_type = str(iface.get("type") or "").lower()
    text = " ".join(filter(None, [name, iface_id, iface_type]))
    virtual_markers = (
        "docker",
        "hassio",
        "veth",
        "virbr",
        "br-",
        "cni",
        "podman",
        "loopback",
    )
    if name == "lo":
        return True
    return any(marker in text for marker in virtual_markers)


def _add_interface_candidates(iface: dict, add_candidate) -> None:
    for key in ("ipv4", "ipv4_addresses"):
        values = iface.get(key)
        if isinstance(values, list):
            for value in values:
                add_candidate(value)
        elif isinstance(values, dict):
            for nested_key in ("ip_address", "address"):
                nested_value = values.get(nested_key)
                if isinstance(nested_value, str):
                    add_candidate(nested_value)
                elif isinstance(nested_value, list):
                    for item in nested_value:
                        add_candidate(item)
    for key in ("ipv4_address", "ip_address", "address"):
        value = iface.get(key)
        if isinstance(value, str):
            add_candidate(value)
        elif isinstance(value, list):
            for item in value:
                add_candidate(item)


def detect_local_ip(server: str, host_info: dict | None = None, advertise_ip: str = "") -> str | None:
    override = _normalize_ip(advertise_ip)
    if override:
        return override

    host_info = host_info or {}
    candidates: list[str] = []
    primary_candidates: list[str] = []

    def add_candidate(value: str, *, primary: bool = False):
        ip = _normalize_ip(value)
        if ip and ip not in candidates:
            candidates.append(ip)
        if primary and ip and ip not in primary_candidates:
            primary_candidates.append(ip)

    interfaces = host_info.get("interfaces")
    for iface in _iter_interface_values(interfaces):
        _add_interface_candidates(iface, add_candidate)

    try:
        network_info = get_network_info()
        network_ifaces = _iter_interface_values(network_info.get("interfaces"))
        primary_ifaces = [iface for iface in network_ifaces if iface.get("primary") is True and not _is_virtual_interface(iface)]
        for iface in primary_ifaces:
            _add_interface_candidates(iface, lambda value: add_candidate(value, primary=True))
        if primary_candidates:
            return max(primary_candidates, key=_score_ip)
        for iface in network_ifaces:
            if iface not in primary_ifaces and not _is_virtual_interface(iface):
                _add_interface_candidates(iface, add_candidate)
    except Exception:
        pass

    try:
        parsed = urlparse(server)
        target_host = parsed.hostname
        target_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if target_host:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((target_host, target_port))
                add_candidate(sock.getsockname()[0])
    except Exception:
        pass

    try:
        interfaces = host_info.get("interfaces")
        for iface in _iter_interface_values(interfaces):
            if not _is_virtual_interface(iface):
                _add_interface_candidates(iface, add_candidate)
    except Exception:
        pass

    if primary_candidates:
        return max(primary_candidates, key=_score_ip)
    if not candidates:
        return None
    return max(candidates, key=_score_ip)


def _boot_timestamp_to_seconds(value) -> float | None:
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    if ts > 1e17:   # nanoseconds
        return ts / 1_000_000_000
    if ts > 1e14:   # microseconds
        return ts / 1_000_000
    if ts > 1e11:   # milliseconds
        return ts / 1_000
    return ts       # seconds


def get_uptime_seconds(host_info: dict | None = None) -> int | None:
    host_info = host_info or {}
    boot_timestamp = _boot_timestamp_to_seconds(host_info.get("boot_timestamp"))
    try:
        if boot_timestamp is not None:
            now_utc = host_info.get("dt_utc")
            now_seconds = time.time()
            if isinstance(now_utc, str) and now_utc:
                now_seconds = datetime.fromisoformat(now_utc).timestamp()
            uptime = int(now_seconds - boot_timestamp)
            if uptime >= 0:
                return uptime
    except (TypeError, ValueError):
        pass

    for key in ("uptime", "uptime_seconds"):
        value = host_info.get(key)
        try:
            if value is not None:
                uptime = int(float(value))
                if uptime >= 0:
                    return uptime
        except (TypeError, ValueError):
            pass

    try:
        raw = Path("/proc/uptime").read_text().split()[0]
        uptime = int(float(raw))
        if uptime >= 0:
            return uptime
    except Exception:
        pass

    return None


def get_pending_updates() -> list[dict]:
    updates: list[dict] = []

    core = get_core_info()
    if core.get("update_available"):
        updates.append({
            "name": "home-assistant-core",
            "current": core.get("version"),
            "new": core.get("version_latest"),
        })

    supervisor = get_supervisor_info()
    if supervisor.get("update_available"):
        updates.append({
            "name": "home-assistant-supervisor",
            "current": supervisor.get("version"),
            "new": supervisor.get("version_latest"),
        })

    os_info = get_os_info()
    if os_info.get("update_available"):
        updates.append({
            "name": "home-assistant-os",
            "current": os_info.get("version"),
            "new": os_info.get("version_latest"),
        })

    for addon in get_addons_info():
        if addon.get("update_available"):
            slug = addon.get("slug") or addon.get("name") or "unknown-addon"
            if is_self_addon(slug):
                updates.append({
                    "name": "home-assistant-addon-patchpilot",
                    "current": addon.get("version"),
                    "new": addon.get("version_latest"),
                })
                continue
            updates.append({
                "name": f"addon:{slug}",
                "current": addon.get("version"),
                "new": addon.get("version_latest"),
            })

    return updates


def register(server: str, register_key: str, agent_id: str, advertise_ip: str, ssl_ctx):
    host = get_host_info()
    opts = load_options()
    payload = {
        "id": agent_id or socket.gethostname(),
        "hostname": host.get("hostname") or socket.gethostname(),
        "ip": detect_local_ip(server, host, advertise_ip),
        "os_pretty": "Home Assistant OS",
        "kernel": host.get("kernel") or platform.release(),
        "arch": platform.machine(),
        "package_manager": "haos",
        "agent_version": AGENT_VERSION,
        "agent_type": "haos",
        "capabilities": build_capabilities(opts),
        "register_key": register_key,
    }
    data = request_json("POST", f"{server}/api/agents/register", data=payload, ssl_ctx=ssl_ctx)
    return data["agent_id"], data["token"]


def heartbeat(server: str, agent_id: str, token: str, advertise_ip: str, ssl_ctx):
    core = get_core_info()
    host = get_host_info()
    opts = load_options()
    payload = {
        "hostname": host.get("hostname") or socket.gethostname(),
        "ip": detect_local_ip(server, host, advertise_ip),
        "os_pretty": "Home Assistant OS",
        "kernel": host.get("kernel") or platform.release(),
        "arch": platform.machine(),
        "package_manager": "haos",
        "agent_version": AGENT_VERSION,
        "agent_type": "haos",
        "capabilities": build_capabilities(opts),
        "packages": get_pending_updates(),
        "reboot_required": 0,
        "uptime_seconds": get_uptime_seconds(host),
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
    opts = load_options()
    if jtype == "refresh_updates":
        return "done", "Home Assistant update status refreshed."
    if jtype == "update_agent":
        return "failed", "PatchPilot HAOS Agent updates are installed through the Home Assistant Add-on Store."
    if jtype == "ha_trigger_agent_update":
        webhook_id = str(opts.get("agent_update_webhook_id") or "").strip()
        if not webhook_id:
            return "failed", "Home Assistant auto-update is not configured. Add a webhook ID in the PatchPilot HAOS add-on options."
        homeassistant_request("POST", f"/webhook/{webhook_id}")
        return "done", "Triggered Home Assistant automation webhook for PatchPilot HAOS Agent update."
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
    if jtype == "ha_supervisor_update":
        result = supervisor_json("POST", "/supervisor/update", {})
        data = result.get("data", {})
        return "done", f"Home Assistant Supervisor update started. Response: {json.dumps(data)}"
    if jtype == "ha_os_update":
        version = params.get("version")
        payload = {}
        if version:
            payload["version"] = version
        result = supervisor_json("POST", "/os/update", payload)
        data = result.get("data", {})
        return "done", f"Home Assistant OS update started{f' -> {version}' if version else ''}. Response: {json.dumps(data)}"
    if jtype == "ha_addon_update":
        slug = str(params.get("slug") or "").strip()
        if not slug:
            return "failed", "Missing add-on slug for ha_addon_update"
        if is_self_addon(slug):
            return "done", "Skipped self-update for PatchPilot HAOS Agent. Update the add-on from Home Assistant instead."
        result = supervisor_json("POST", f"/addons/{slug}/update", {})
        data = result.get("data", {})
        return "done", f"Home Assistant add-on update started for {slug}. Response: {json.dumps(data)}"
    if jtype == "ha_addons_update":
        updated: list[str] = []
        skipped: list[str] = []
        for addon in get_addons_info():
            slug = addon.get("slug")
            if not slug:
                continue
            if is_self_addon(slug):
                skipped.append(slug)
                continue
            if not addon.get("update_available"):
                skipped.append(slug)
                continue
            supervisor_json("POST", f"/addons/{slug}/update", {})
            updated.append(slug)
        return "done", json.dumps({
            "updated_addons": updated,
            "skipped_addons": skipped,
        })
    return "failed", f"Unknown job type: {jtype}"


def main():
    opts = load_options()
    server = opts.get("patchpilot_server", "").rstrip("/")
    register_key = opts.get("register_key", "")
    agent_id = opts.get("agent_id", "").strip()
    advertise_ip = opts.get("advertise_ip", "").strip()
    poll_interval = int(opts.get("poll_interval", 30) or 30)
    ca_pem = opts.get("ca_pem", "").strip()
    if not server:
        raise RuntimeError("patchpilot_server is required")

    ssl_ctx = make_ssl_context(ca_pem)
    state = load_state()
    agent_id = state.get("agent_id") or agent_id or socket.gethostname()
    token = state.get("token", "")
    if not token:
        if not register_key:
            raise RuntimeError("register_key is required for first registration")
        agent_id, token = register(server, register_key, agent_id, advertise_ip, ssl_ctx)
        state.update({"agent_id": agent_id, "token": token})
        save_state(state)

    last_heartbeat = 0
    while True:
        try:
            if last_heartbeat <= 0:
                heartbeat(server, agent_id, token, advertise_ip, ssl_ctx)
                last_heartbeat = poll_interval
            jobs = poll_jobs(server, agent_id, token, ssl_ctx)
            for job in jobs:
                status, output = run_job(job)
                report_result(server, agent_id, token, job["id"], status, output, ssl_ctx)
                heartbeat(server, agent_id, token, advertise_ip, ssl_ctx)
        except urllib.error.HTTPError as err:
            print(f"[patchpilot-haos] HTTP {err.code}: {err.read().decode(errors='ignore')}", file=sys.stderr)
        except Exception as err:
            print(f"[patchpilot-haos] {err}", file=sys.stderr)
        time.sleep(10)
        last_heartbeat -= 10


if __name__ == "__main__":
    main()

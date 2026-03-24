#!/usr/bin/env python3
"""
PatchPilot Agent — runs on each Debian VM.
Configure via /etc/patchpilot/agent.conf or environment variables.

ENV vars:
  PATCHPILOT_SERVER   e.g. http://192.168.1.10:8000
  PATCHPILOT_AGENT_ID (optional, auto-generated on first run)
  PATCHPILOT_TOKEN    (set automatically after registration)
  PATCHPILOT_INTERVAL poll interval in seconds (default: 60)
"""

import json
import os
import platform
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

try:
    import ssl
    import urllib.request as urlreq
    import urllib.error
except ImportError:
    print("[agent] FATAL: ssl/urllib not available — cannot communicate with server", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# TLS context
# ---------------------------------------------------------------------------
def _make_ssl_context() -> "ssl.SSLContext":
    """Return a strict SSL context that verifies server certificates.

    If the environment variable PATCHPILOT_SERVER starts with 'http://'
    (plain HTTP, typical in private home networks), TLS is not used and
    this context is irrelevant.  For HTTPS deployments the context
    enforces certificate verification to prevent MITM attacks.

    Set PATCHPILOT_CA_BUNDLE to a custom CA certificate file if you use
    a self-signed certificate on the server.
    """
    ctx = ssl.create_default_context()
    ca_bundle = os.environ.get("PATCHPILOT_CA_BUNDLE", "")
    if ca_bundle:
        ctx.load_verify_locations(cafile=ca_bundle)
    return ctx

_SSL_CTX = _make_ssl_context()


def _reload_ssl_context():
    """Rebuild the global SSL context (e.g. after installing a new CA cert)."""
    global _SSL_CTX
    _SSL_CTX = _make_ssl_context()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CONFIG_DIR = Path("/etc/patchpilot")
CONFIG_FILE = CONFIG_DIR / "agent.conf"
STATE_FILE = CONFIG_DIR / "state.json"

DEFAULT_INTERVAL = 60


def load_config():
    cfg = {}
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    # ENV overrides
    for key in ("PATCHPILOT_SERVER", "PATCHPILOT_AGENT_ID", "PATCHPILOT_TOKEN", "PATCHPILOT_INTERVAL"):
        if val := os.environ.get(key):
            cfg[key] = val
    return cfg


def save_state(state: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # SECURITY: Write via file descriptor with restricted permissions so the
    # token is never world-readable, even briefly.
    fd = os.open(str(STATE_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps(state, indent=2).encode())
    finally:
        os.close(fd)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception as e:
            print(f"[agent] WARNING: corrupt state file, starting fresh: {e}", file=sys.stderr)
    return {}


# ---------------------------------------------------------------------------
# System info helpers
# ---------------------------------------------------------------------------
def get_hostname() -> str:
    return socket.gethostname()


def get_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return "unknown"


def get_os_pretty() -> str:
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip('"')
    except Exception:
        pass
    return platform.system()


def get_kernel() -> str:
    return platform.release()


def get_arch() -> str:
    return platform.machine()


def reboot_required() -> bool:
    return Path("/var/run/reboot-required").exists()


def get_uptime_seconds() -> int | None:
    """Read system uptime from /proc/uptime (Linux only)."""
    try:
        return int(float(Path("/proc/uptime").read_text().split()[0]))
    except Exception:
        return None


def get_pending_updates() -> list:
    """Return list of {name, current, new} for upgradeable packages."""
    try:
        # Update package lists quietly
        subprocess.run(
            ["apt-get", "update", "-qq"],
            capture_output=True,
            timeout=120,
        )
        out = subprocess.run(
            ["apt-get", "--just-print", "upgrade"],
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout
    except Exception as e:
        print(f"[agent] apt-get error: {e}", file=sys.stderr)
        return []

    packages = []
    # Lines like: Inst <name> [<current>] (<new> ...)
    for line in out.splitlines():
        m = re.match(r"Inst (\S+) \[(\S+)\] \((\S+)", line)
        if m:
            packages.append({"name": m.group(1), "current": m.group(2), "new": m.group(3)})
        elif line.startswith("Inst "):
            parts = line.split()
            if len(parts) >= 2:
                packages.append({"name": parts[1], "current": None, "new": None})
    return packages


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only)
# ---------------------------------------------------------------------------
def _request(method: str, url: str, data=None, headers=None):
    headers = headers or {}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urlreq.Request(url, data=body, headers=headers, method=method)
    # SECURITY: Pass the SSL context so that server certificates are verified
    # for HTTPS connections.  For plain HTTP (http://) the context is ignored
    # by urlopen, so existing home-network setups continue to work unchanged.
    try:
        with urlreq.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # L-5: cap error body to 200 bytes to avoid flooding logs with large responses
        body_snippet = e.read(200)
        print(f"[agent] HTTP {e.code} {url}: {body_snippet!r}", file=sys.stderr)
        if e.code == 401:
            raise _TokenInvalid()
        return None
    except _TokenInvalid:
        raise
    except Exception as e:
        print(f"[agent] Request failed {url}: {e}", file=sys.stderr)
        return None


class _TokenInvalid(Exception):
    """Raised when the server returns 401 — signals the main loop to re-register."""


# ---------------------------------------------------------------------------
# Agent logic
# ---------------------------------------------------------------------------
def register(server: str, agent_id: str, token: str) -> tuple:
    cfg = load_config()
    hdrs = {}
    # For re-registration, send existing token; for new, send register key
    if token:
        hdrs["x-token"] = token
    else:
        reg_key = cfg.get("PATCHPILOT_REGISTER_KEY", "")
        if reg_key:
            hdrs["x-register-key"] = reg_key
    resp = _request(
        "POST",
        f"{server}/api/agents/register",
        data={
            "id": agent_id,
            # LOW-6: do not send client-proposed token — server always generates it
            "hostname": get_hostname(),
            "ip": get_ip(),
            "os_pretty": get_os_pretty(),
            "kernel": get_kernel(),
            "arch": get_arch(),
        },
        headers=hdrs,
    )
    if resp and "agent_id" in resp and "token" in resp:
        return resp["agent_id"], resp["token"]
    if resp:
        print(f"[agent] WARNING: unexpected registration response: {list(resp.keys())}", file=sys.stderr)
    return agent_id, token


def send_heartbeat(server: str, agent_id: str, token: str, packages: list) -> dict:
    resp = _request(
        "POST",
        f"{server}/api/agents/{agent_id}/heartbeat",
        data={
            "hostname": get_hostname(),
            "ip": get_ip(),
            "os_pretty": get_os_pretty(),
            "kernel": get_kernel(),
            "arch": get_arch(),
            "reboot_required": reboot_required(),
            "uptime_seconds": get_uptime_seconds(),
            "packages": packages,
        },
        headers={"x-token": token},
    )
    return resp or {}


def poll_jobs(server: str, agent_id: str, token: str) -> list:
    resp = _request(
        "GET",
        f"{server}/api/agents/{agent_id}/jobs",
        headers={"x-token": token},
    )
    return resp or []


def report_result(server: str, agent_id: str, token: str, job_id: int, status: str, output: str):
    _request(
        "POST",
        f"{server}/api/agents/{agent_id}/jobs/{job_id}/result",
        data={"status": status, "output": output},
        headers={"x-token": token},
    )


_SAFE_PKG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.+\-]{0,127}$")


def _validate_package_names(pkg_list: list) -> list:
    """Return only package names that match the Debian package-name grammar.

    Debian policy (section 5.6.1) allows [a-z0-9][a-z0-9.+-]+.
    We also permit uppercase for robustness.  Any name that does not match
    is dropped and logged so a compromised server cannot inject shell
    metacharacters into the apt-get invocation.
    """
    safe = []
    for name in pkg_list:
        if isinstance(name, str) and _SAFE_PKG_RE.match(name):
            safe.append(name)
        else:
            print(
                f"[agent] WARNING: rejected invalid package name {name!r}",
                file=sys.stderr,
            )
    return safe


def execute_job(job: dict) -> tuple:
    if "type" not in job or "id" not in job:
        return "failed", f"Malformed job dict: missing 'type' or 'id' key"
    jtype = job["type"]
    params = job.get("params", {})

    if jtype == "patch":
        raw_pkg_list = params.get("packages", [])
        # SECURITY: Validate every package name before passing it to
        # apt-get.  This prevents a compromised server (or MITM) from
        # injecting shell metacharacters.  subprocess is called with a
        # list (not shell=True) so shell injection is already structurally
        # blocked, but name validation adds defence-in-depth.
        pkg_list = _validate_package_names(raw_pkg_list) if raw_pkg_list else []
        apt_env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
        dpkg_opts = ["-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold"]
        if pkg_list:
            cmd = ["apt-get", "install", "-y"] + dpkg_opts + ["--only-upgrade"] + pkg_list
        else:
            cmd = ["apt-get", "upgrade", "-y"] + dpkg_opts
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                env=apt_env,
            )
            output = result.stdout + result.stderr
            status = "done" if result.returncode == 0 else "failed"
            # Detect kept config files and warn the user
            confold_markers = ["force-confold", "Konfigurationsdatei", "configuration file",
                               "keeping old config", "installing new version"]
            kept_configs = [l.strip() for l in output.splitlines()
                           if any(m.lower() in l.lower() for m in confold_markers)
                           and ("==>" in l or "conf" in l.lower())]
            if kept_configs:
                output += "\n\n⚠️  CONFIG NOTICE: Some packages had modified config files. " \
                          "The existing config was kept. Review manually if the new version " \
                          "requires config changes:\n" + "\n".join(f"  • {c}" for c in kept_configs)
            # Auto-run autoremove after successful patch to clean up
            if status == "done":
                try:
                    ar = subprocess.run(
                        ["apt-get", "autoremove", "-y"],
                        capture_output=True, text=True, timeout=300,
                        env=apt_env,
                    )
                    if ar.stdout.strip():
                        output += "\n--- autoremove ---\n" + ar.stdout
                except Exception:
                    pass  # best-effort, don't fail the patch job
        except subprocess.TimeoutExpired:
            output = "Timeout after 600s"
            status = "failed"
        except Exception as e:
            output = str(e)
            status = "failed"
        return status, output

    elif jtype == "reboot":
        try:
            subprocess.Popen(["shutdown", "-r", "+1", "PatchPilot scheduled reboot"])
            return "done", "Reboot scheduled in 1 minute"
        except Exception as e:
            return "failed", str(e)

    elif jtype == "autoremove":
        try:
            result = subprocess.run(
                ["apt-get", "autoremove", "-y"],
                capture_output=True,
                text=True,
                timeout=300,
                env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
            )
            output = result.stdout + result.stderr
            status = "done" if result.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            output = "Timeout after 300s"
            status = "failed"
        except Exception as e:
            output = str(e)
            status = "failed"
        return status, output

    elif jtype == "update_agent":
        # Self-update: download new agent.py from server, verify SHA-256, replace self.
        return _update_self(params)

    elif jtype == "deploy_ssl":
        # Download CA certificate from server and install it locally.
        return _deploy_ssl_cert()

    else:
        return "failed", f"Unknown job type: {jtype}"


def _deploy_ssl_cert() -> tuple:
    """Download the server's CA certificate and install it so the agent trusts
    HTTPS connections.  Updates agent.conf with PATCHPILOT_CA_BUNDLE path."""
    import hashlib as _hashlib
    import tempfile as _tempfile

    cfg = load_config()
    server_url = cfg.get("PATCHPILOT_SERVER", "").rstrip("/")
    if not server_url:
        return "failed", "PATCHPILOT_SERVER not set — cannot download certificate"

    cert_url = f"{server_url}/agent/ca.pem"
    hash_url = f"{server_url}/agent/ca.pem.sha256"
    ca_path = CONFIG_DIR / "ca.pem"

    try:
        # Download SHA-256 checksum
        req_hash = urlreq.Request(hash_url, method="GET")
        with urlreq.urlopen(req_hash, timeout=30, context=_SSL_CTX) as r:
            expected_hash = r.read().decode().split()[0].strip()

        # Download certificate
        req_cert = urlreq.Request(cert_url, method="GET")
        with urlreq.urlopen(req_cert, timeout=30, context=_SSL_CTX) as r:
            cert_data = r.read()

        # Verify integrity
        actual_hash = _hashlib.sha256(cert_data).hexdigest()
        if actual_hash != expected_hash:
            return "failed", f"SHA-256 mismatch: expected {expected_hash[:16]}… got {actual_hash[:16]}…"

        # SEC: Validate PEM format before writing
        if not cert_data.strip().startswith(b"-----BEGIN CERTIFICATE-----"):
            return "failed", "Downloaded data is not a valid PEM certificate"

        # Write cert atomically
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp_name = None
        tmp = _tempfile.NamedTemporaryFile(
            dir=str(CONFIG_DIR), suffix=".tmp", delete=False
        )
        try:
            tmp_name = tmp.name
            tmp.write(cert_data)
            tmp.flush()
            tmp_path = Path(tmp.name)
        finally:
            tmp.close()
        try:
            tmp_path.chmod(0o644)
            tmp_path.replace(ca_path)
        except Exception:
            if tmp_name:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
            raise

        # Update agent.conf: set PATCHPILOT_CA_BUNDLE
        _update_config_key("PATCHPILOT_CA_BUNDLE", str(ca_path))

        # Update env and reload the global SSL context in-process
        os.environ["PATCHPILOT_CA_BUNDLE"] = str(ca_path)
        _reload_ssl_context()

        return "done", f"CA cert installed at {ca_path}"

    except Exception as e:
        return "failed", f"SSL cert deploy failed: {e}"


def _update_config_key(key: str, value: str):
    """Set a key=value in agent.conf, adding it if not present."""
    # SEC: Sanitize newlines to prevent config injection
    key = key.replace('\n', '').replace('\r', '')
    value = value.replace('\n', '').replace('\r', '')
    cfg_path = CONFIG_FILE
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if cfg_path.exists():
        lines = cfg_path.read_text().splitlines()
        found = False
        new_lines = []
        for ln in lines:
            if ln.strip().startswith(f"{key}="):
                new_lines.append(f"{key}={value}")
                found = True
            else:
                new_lines.append(ln)
        if not found:
            new_lines.append(f"{key}={value}")
        cfg_path.write_text("\n".join(new_lines) + "\n")
    else:
        cfg_path.write_text(f"{key}={value}\n")


def _update_self(params: dict) -> tuple:
    """Download the latest agent.py from the server, verify its SHA-256, and replace
    the running script.  The agent restarts automatically via systemd (Restart=always).
    """
    import hashlib as _hashlib
    import tempfile as _tempfile

    # Always download from configured server — never accept external URLs (SEC M-6)
    cfg = load_config()
    server_url = cfg.get("PATCHPILOT_SERVER", "").rstrip("/")
    if not server_url:
        return "failed", "PATCHPILOT_SERVER not set — cannot download update"

    agent_url = f"{server_url}/agent/agent.py"
    hash_url  = f"{server_url}/agent/agent.py.sha256"
    self_path = Path(__file__).resolve()

    try:
        # Download SHA-256 checksum first (SEC M-2: use SSL context)
        req_hash = urlreq.Request(hash_url, method="GET")
        with urlreq.urlopen(req_hash, timeout=30, context=_SSL_CTX) as r:
            expected_hash = r.read().decode().split()[0].strip()

        # Download new agent binary
        req_agent = urlreq.Request(agent_url, method="GET")
        with urlreq.urlopen(req_agent, timeout=60, context=_SSL_CTX) as r:
            new_code = r.read()

        # Verify integrity
        actual_hash = _hashlib.sha256(new_code).hexdigest()
        if actual_hash != expected_hash:
            return "failed", f"SHA-256 mismatch: expected {expected_hash[:16]}… got {actual_hash[:16]}…"

        # Write to temp file in same directory, then atomically replace
        tmp = _tempfile.NamedTemporaryFile(
            dir=self_path.parent, suffix=".tmp", delete=False
        )
        try:
            tmp.write(new_code)
            tmp.flush()
            tmp_path = Path(tmp.name)
        finally:
            tmp.close()

        # Preserve permissions
        try:
            tmp_path.chmod(self_path.stat().st_mode)
        except OSError:
            pass

        tmp_path.replace(self_path)

        # Fork a child that sleeps 4s then kills the parent, so systemd
        # (Restart=always) relaunches with new code.  The delay gives
        # report_result time to POST the job result.  os.fork + os._exit
        # need no extra imports — important for bootstrapping old agents.
        pid = os.getpid()
        child = os.fork()
        if child == 0:
            # Child process: wait then kill parent
            time.sleep(4)
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            os._exit(0)

        return "done", f"Agent updated to {actual_hash[:16]}… — restarting in 4s"

    except Exception as e:
        return "failed", f"Update failed: {e}"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    cfg = load_config()
    server = cfg.get("PATCHPILOT_SERVER", "").rstrip("/")
    if not server:
        print("[agent] ERROR: PATCHPILOT_SERVER not set", file=sys.stderr)
        sys.exit(1)

    try:
        interval = int(cfg.get("PATCHPILOT_INTERVAL", DEFAULT_INTERVAL))
        if interval < 10:
            interval = DEFAULT_INTERVAL
    except (ValueError, TypeError):
        print(f"[agent] WARNING: invalid PATCHPILOT_INTERVAL, using default {DEFAULT_INTERVAL}s", file=sys.stderr)
        interval = DEFAULT_INTERVAL
    state = load_state()

    agent_id = cfg.get("PATCHPILOT_AGENT_ID") or state.get("agent_id") or get_hostname()
    token = cfg.get("PATCHPILOT_TOKEN") or state.get("token") or ""

    # Restore migrated server URL from persistent state so port changes survive restarts.
    # Only apply if the host matches (same server, different port).
    state_server = state.get("server", "").rstrip("/")
    if state_server and state_server != server:
        cfg_host = server.split(":")[1].lstrip("/") if "://" in server else server
        st_host  = state_server.split(":")[1].lstrip("/") if "://" in state_server else state_server
        if cfg_host == st_host:
            print(f"[agent] Restored migrated server URL from state: {state_server}")
            server = state_server

    # MED-7: Warn when using plain HTTP — tokens are sent in cleartext
    if server.startswith("http://"):
        print(
            "[agent] WARNING: connecting over plain HTTP — agent token is sent "
            "unencrypted. Use HTTPS for production deployments.",
            file=sys.stderr,
        )

    # Graceful shutdown on SIGTERM (systemd sends this on stop/restart)
    _shutdown = False
    def _handle_sigterm(signum, frame):
        nonlocal _shutdown
        _shutdown = True
        print("[agent] Received SIGTERM, shutting down gracefully")
    signal.signal(signal.SIGTERM, _handle_sigterm)

    print(f"[agent] Starting — server={server} id={agent_id or '(new)'}")

    # Register / re-register
    agent_id, token = register(server, agent_id, token)
    state.update({"agent_id": agent_id, "token": token})
    save_state(state)
    print(f"[agent] Registered as {agent_id}")

    last_heartbeat = 0  # seconds since last heartbeat (force immediate first run)
    while not _shutdown:
        try:
            # Collect updates every full interval, jobs every 10s
            if last_heartbeat >= interval or last_heartbeat == 0:
                print("[agent] Collecting pending updates …")
                packages = get_pending_updates()
                print(f"[agent] {len(packages)} pending update(s)")
                hb = send_heartbeat(server, agent_id, token, packages)
                # If the server signals a different canonical URL (protocol, host,
                # or port change), migrate to it automatically.
                canonical_url = hb.get("canonical_url", "")
                if canonical_url and canonical_url != server:
                    # Validate: must be http(s)://host:port format
                    if canonical_url.startswith(("http://", "https://")) and ":" in canonical_url.split("://", 1)[1]:
                        print(f"[agent] Server URL changed → migrating to {canonical_url}")
                        server = canonical_url
                        state["server"] = server
                        save_state(state)
                elif not canonical_url:
                    # Fallback: legacy canonical_port for older servers
                    canonical_port = hb.get("canonical_port")
                    if canonical_port:
                        try:
                            port_int = int(canonical_port)
                            if not (1 <= port_int <= 65535):
                                canonical_port = None
                        except (ValueError, TypeError):
                            canonical_port = None
                    if canonical_port:
                        base, _, _ = server.rpartition(":")
                        canonical = f"{base}:{canonical_port}"
                        if canonical != server:
                            print(f"[agent] Server port changed → migrating to {canonical}")
                            server = canonical
                            state["server"] = server
                            save_state(state)

                # If the server renamed our ID, update config + state
                canonical_id = hb.get("canonical_id")
                if canonical_id and canonical_id != agent_id:
                    print(f"[agent] Server renamed us: {agent_id} → {canonical_id}")
                    agent_id = canonical_id
                    state["agent_id"] = agent_id
                    save_state(state)
                    # Also update the config file so it survives restarts
                    cfg = load_config()
                    cfg_path = CONFIG_FILE
                    if cfg_path.exists():
                        try:
                            lines = cfg_path.read_text().splitlines()
                            new_lines = []
                            for ln in lines:
                                if ln.startswith("PATCHPILOT_AGENT_ID="):
                                    new_lines.append(f"PATCHPILOT_AGENT_ID={agent_id}")
                                else:
                                    new_lines.append(ln)
                            cfg_path.write_text("\n".join(new_lines) + "\n")
                        except OSError as e:
                            print(f"[agent] Warning: could not update agent.conf: {e}", file=sys.stderr)

                last_heartbeat = 0

            # Poll for jobs
            jobs = poll_jobs(server, agent_id, token)
            for job in jobs:
                print(f"[agent] Executing job #{job['id']} type={job['type']}")
                status, output = execute_job(job)
                report_result(server, agent_id, token, job["id"], status, output)
                print(f"[agent] Job #{job['id']} finished: {status}")

                # Refresh heartbeat after patching
                if job["type"] == "patch":
                    packages = get_pending_updates()
                    send_heartbeat(server, agent_id, token, packages)

        except KeyboardInterrupt:
            print("[agent] Shutting down (keyboard interrupt)")
            break
        except _TokenInvalid:
            # Token rejected by server — clear it and re-register on next tick
            print("[agent] Token invalid, re-registering…", file=sys.stderr)
            token = ""
            state.pop("token", None)
            save_state(state)
            time.sleep(5)
            agent_id, token = register(server, agent_id, token)
            state.update({"agent_id": agent_id, "token": token})
            save_state(state)
            print(f"[agent] Re-registered as {agent_id}")
            continue
        except Exception as e:
            print(f"[agent] Unexpected error: {e}", file=sys.stderr)

        time.sleep(10)
        last_heartbeat += 10


if __name__ == "__main__":
    main()

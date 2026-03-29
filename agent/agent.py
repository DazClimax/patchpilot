#!/usr/bin/env python3
"""
PatchPilot Agent — runs on Linux VMs.
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
import shutil
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
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2  # SEC: enforce minimum TLS 1.2
    ca_bundle = os.environ.get("PATCHPILOT_CA_BUNDLE", "")
    # Also check agent.conf directly — env var may not be set at import time
    if not ca_bundle:
        conf = Path("/etc/patchpilot/agent.conf")
        if conf.exists():
            for line in conf.read_text().splitlines():
                line = line.strip()
                if line.startswith("PATCHPILOT_CA_BUNDLE="):
                    ca_bundle = line.split("=", 1)[1].strip()
                    break
    if ca_bundle and Path(ca_bundle).is_file():
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
AGENT_VERSION = "1.0"


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


def _set_config_review(required: bool, note: str = ""):
    state = load_state()
    state["config_review_required"] = bool(required)
    state["config_review_note"] = note[:4000] if required else ""
    save_state(state)


def _get_config_review() -> tuple[bool, str]:
    state = load_state()
    return bool(state.get("config_review_required")), str(state.get("config_review_note", ""))


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


def get_package_manager() -> str:
    try:
        return _pkg_backend()["name"]
    except Exception:
        return "unknown"


def reboot_required() -> bool:
    if Path("/var/run/reboot-required").exists():
        return True
    try:
        backend = _pkg_backend()
        if backend["name"] in {"dnf", "yum"}:
            return _rpm_reboot_required(backend)
        cmd = backend.get("reboot_check")
        if cmd:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.returncode == 1
    except Exception:
        pass
    return False


def get_uptime_seconds() -> int | None:
    """Read system uptime from /proc/uptime (Linux only)."""
    try:
        return int(float(Path("/proc/uptime").read_text().split()[0]))
    except Exception:
        return None


def _is_container() -> bool:
    if Path("/run/.containerenv").exists() or Path("/.dockerenv").exists():
        return True
    if os.environ.get("container"):
        return True
    try:
        result = subprocess.run(
            ["systemd-detect-virt", "--quiet", "--container"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _rpm_reboot_required(backend: dict) -> bool:
    # Container guests share the host kernel. Kernel/package based reboot hints
    # are therefore noisy and often permanently wrong there.
    if _is_container():
        return False

    kernel_reboot_needed = _rpm_kernel_reboot_required()
    cmd = backend.get("reboot_check")
    if not cmd:
        return kernel_reboot_needed

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return kernel_reboot_needed
    except Exception:
        return kernel_reboot_needed

    if result.returncode == 0:
        return False
    if result.returncode == 1 and kernel_reboot_needed:
        return True

    combined = f"{result.stdout}\n{result.stderr}".lower()
    reboot_markers = (
        "reboot is required",
        "reboot should be performed",
        "system restart is required",
        "kernel update",
    )
    if any(marker in combined for marker in reboot_markers):
        return True
    return kernel_reboot_needed


def _rpm_kernel_reboot_required() -> bool:
    try:
        result = subprocess.run(
            ["rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}.%{ARCH}\t%{INSTALLTIME}\n"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        return False

    if result.returncode != 0:
        return False

    newest_release = ""
    newest_installtime = -1
    kernel_names = {"kernel", "kernel-core", "kernel-rt", "kernel-rt-core"}
    for raw in result.stdout.splitlines():
        parts = raw.strip().split("\t")
        if len(parts) != 3:
            continue
        name, release, installtime_raw = parts
        if name not in kernel_names:
            continue
        try:
            installtime = int(installtime_raw)
        except ValueError:
            continue
        if installtime > newest_installtime:
            newest_installtime = installtime
            newest_release = release

    if not newest_release:
        return False

    running_kernel = platform.release().strip()
    return newest_release != running_kernel


def _extract_config_review_note(output: str, backend_name: str) -> str:
    lines = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        lower = line.lower()
        if backend_name == "apt":
            markers = ("force-confold", "configuration file", "konfigurationsdatei", "keeping old config", "installing new version")
            if any(marker in lower for marker in markers) and ("==>" in line or "conf" in lower):
                lines.append(line)
        else:
            if ".rpmnew" in lower or ".rpmsave" in lower or "saved as" in lower:
                lines.append(line)
    unique = []
    for line in lines:
        if line not in unique:
            unique.append(line)
    return "\n".join(unique[:8])


def get_pending_updates() -> list:
    """Return list of {name, current, new} for upgradeable packages."""
    backend = _pkg_backend()
    try:
        refresh_cmd = backend.get("refresh")
        if refresh_cmd:
            subprocess.run(refresh_cmd, capture_output=True, timeout=180)
        out = subprocess.run(
            backend["list_updates"],
            capture_output=True,
            text=True,
            timeout=120,
        ).stdout
    except Exception as e:
        print(f"[agent] package manager error: {e}", file=sys.stderr)
        return []

    packages = []
    if backend["name"] == "apt":
        # Lines like: Inst <name> [<current>] (<new> ...)
        for line in out.splitlines():
            m = re.match(r"Inst (\S+) \[(\S+)\] \((\S+)", line)
            if m:
                packages.append({"name": m.group(1), "current": m.group(2), "new": m.group(3)})
            elif line.startswith("Inst "):
                parts = line.split()
                if len(parts) >= 2:
                    packages.append({"name": parts[1], "current": None, "new": None})
    else:
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith(("Last metadata expiration", "Obsoleting", "Security:", "Available Upgrades")):
                continue
            parts = line.split()
            if len(parts) >= 3 and "." in parts[0]:
                packages.append({"name": parts[0].rsplit(".", 1)[0], "current": None, "new": parts[1]})
    return packages


def _pkg_backend() -> dict:
    if shutil.which("apt-get"):
        return {
            "name": "apt",
            "refresh": ["apt-get", "update", "-qq"],
            "list_updates": ["apt-get", "--just-print", "upgrade"],
            "patch_all": ["apt-get", "upgrade", "-y", "-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold"],
            "dist_upgrade_all": ["apt-get", "dist-upgrade", "-y", "-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold"],
            "patch_selected_prefix": ["apt-get", "install", "-y", "-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold", "--only-upgrade"],
            "autoremove": ["apt-get", "autoremove", "-y"],
            "env": {**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
            "reboot_check": None,
        }
    if shutil.which("dnf"):
        return {
            "name": "dnf",
            "refresh": ["dnf", "-q", "makecache"],
            "list_updates": ["dnf", "-q", "check-update"],
            "patch_all": ["dnf", "-y", "upgrade", "--refresh"],
            "dist_upgrade_all": ["dnf", "-y", "distro-sync", "--refresh"],
            "patch_selected_prefix": ["dnf", "-y", "upgrade", "--refresh"],
            "autoremove": ["dnf", "-y", "autoremove"],
            "env": dict(os.environ),
            "reboot_check": ["dnf", "needs-restarting", "-r"],
        }
    if shutil.which("yum"):
        return {
            "name": "yum",
            "refresh": ["yum", "-q", "makecache"],
            "list_updates": ["yum", "-q", "check-update"],
            "patch_all": ["yum", "-y", "update"],
            "dist_upgrade_all": ["yum", "-y", "update"],
            "patch_selected_prefix": ["yum", "-y", "update"],
            "autoremove": None,
            "env": dict(os.environ),
            "reboot_check": None,
        }
    raise RuntimeError("No supported package manager found (requires apt, dnf, or yum)")


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
        # Protocol fallback: if HTTP fails, try HTTPS and vice versa.
        # This handles the transition when the server switches protocol
        # (e.g. SSL enabled/disabled) and the agent hasn't migrated yet.
        alt_url = _protocol_fallback(url)
        if alt_url:
            try:
                alt_req = urlreq.Request(alt_url, data=body, headers=headers, method=method)
                with urlreq.urlopen(alt_req, timeout=30, context=_SSL_CTX) as resp:
                    print(f"[agent] Fallback succeeded: {url} → {alt_url}")
                    return json.loads(resp.read())
            except Exception:
                pass  # fallback also failed, report original error
        print(f"[agent] Request failed {url}: {e}", file=sys.stderr)
        return None


def _protocol_fallback(url: str) -> str | None:
    """Return the URL with swapped protocol (http↔https), or None."""
    if url.startswith("http://"):
        return "https://" + url[7:]
    elif url.startswith("https://"):
        return "http://" + url[8:]
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
            "package_manager": get_package_manager(),
            "agent_version": AGENT_VERSION,
        },
        headers=hdrs,
    )
    if resp and "agent_id" in resp and "token" in resp:
        return resp["agent_id"], resp["token"]
    if resp:
        print(f"[agent] WARNING: unexpected registration response: {list(resp.keys())}", file=sys.stderr)
    return agent_id, token


def send_heartbeat(server: str, agent_id: str, token: str, packages: list) -> dict:
    config_review_required, config_review_note = _get_config_review()
    resp = _request(
        "POST",
        f"{server}/api/agents/{agent_id}/heartbeat",
        data={
            "hostname": get_hostname(),
            "ip": get_ip(),
            "os_pretty": get_os_pretty(),
            "kernel": get_kernel(),
            "arch": get_arch(),
            "package_manager": get_package_manager(),
            "agent_version": AGENT_VERSION,
            "reboot_required": reboot_required(),
            "uptime_seconds": get_uptime_seconds(),
            "config_review_required": config_review_required,
            "config_review_note": config_review_note,
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


_SAFE_PKG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.+:_\-]{0,127}$")


def _validate_package_names(pkg_list: list) -> list:
    """Return only package names that look safe for apt/dnf/yum invocations."""
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


def _run_package_command(cmd: list[str], env: dict, timeout: int) -> tuple[str, str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return ("done" if result.returncode == 0 else "failed"), (result.stdout + result.stderr)
    except subprocess.TimeoutExpired:
        return "failed", f"Timeout after {timeout}s"
    except Exception as e:
        return "failed", str(e)


def _run_force_patch(backend: dict, pkg_list: list[str]) -> tuple[str, str]:
    if backend["name"] not in {"dnf", "yum"}:
        cmd = backend["patch_selected_prefix"] + pkg_list if pkg_list else backend["patch_all"]
        return _run_package_command(cmd, backend["env"], 900)

    if not shutil.which("systemd-run"):
        return "failed", "Force update requires systemd-run on RPM systems"

    base_cmd = backend["patch_selected_prefix"] + pkg_list if pkg_list else backend["patch_all"]
    unit_name = f"patchpilot-force-update-{int(time.time())}"
    cmd = [
        "systemd-run",
        "--wait",
        "--collect",
        "--quiet",
        f"--unit={unit_name}",
        "--service-type=exec",
        "--property=StandardOutput=journal",
        "--property=StandardError=journal",
        *base_cmd,
    ]
    status, output = _run_package_command(cmd, backend["env"], 1200)
    if shutil.which("journalctl"):
        journal_status, journal_output = _run_package_command(
            ["journalctl", "--no-pager", "-o", "cat", "-u", unit_name],
            backend["env"],
            60,
        )
        if journal_output.strip():
            output = journal_output
        elif journal_status == "failed" and output.strip():
            output += "\n\n[journalctl]\n" + journal_output
    if status == "done":
        output = (output.rstrip() + "\n\n" if output.strip() else "") + "Force update executed via transient systemd service."
    return status, output


def execute_job(job: dict) -> tuple:
    if "type" not in job or "id" not in job:
        return "failed", f"Malformed job dict: missing 'type' or 'id' key"
    jtype = job["type"]
    params = job.get("params", {})

    if jtype in {"patch", "dist_upgrade", "force_patch"}:
        raw_pkg_list = params.get("packages", [])
        # SECURITY: Validate every package name before passing it to
        # the package manager.  This prevents a compromised server (or MITM) from
        # injecting shell metacharacters.  subprocess is called with a
        # list (not shell=True) so shell injection is already structurally
        # blocked, but name validation adds defence-in-depth.
        pkg_list = _validate_package_names(raw_pkg_list) if raw_pkg_list else []
        backend = _pkg_backend()
        if jtype == "dist_upgrade":
            cmd = backend.get("dist_upgrade_all") or backend["patch_all"]
        elif jtype == "force_patch":
            status, output = _run_force_patch(backend, pkg_list)
            review_note = _extract_config_review_note(output, backend["name"])
            if review_note:
                _set_config_review(True, review_note)
                output += "\n\nCONFIG REVIEW REQUIRED:\n" + review_note + "\n\nReview the changed config files and acknowledge the warning in PatchPilot once everything looks good."
            elif status == "done":
                _set_config_review(False)
            return status, output
        elif pkg_list:
            cmd = backend["patch_selected_prefix"] + pkg_list
        else:
            cmd = backend["patch_all"]
        try:
            status, output = _run_package_command(cmd, backend["env"], 600)
            review_note = _extract_config_review_note(output, backend["name"])
            if review_note:
                _set_config_review(True, review_note)
                output += "\n\nCONFIG REVIEW REQUIRED:\n" + review_note + "\n\nReview the changed config files and acknowledge the warning in PatchPilot once everything looks good."
            elif status == "done":
                _set_config_review(False)
            # Auto-run autoremove after successful patch to clean up
            if status == "done" and backend.get("autoremove"):
                try:
                    ar = subprocess.run(
                        backend["autoremove"],
                        capture_output=True, text=True, timeout=300,
                        env=backend["env"],
                    )
                    if ar.stdout.strip():
                        output += "\n--- autoremove ---\n" + ar.stdout
                except Exception:
                    pass  # best-effort, don't fail the patch job
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

    elif jtype == "refresh_updates":
        backend = _pkg_backend()
        try:
            result = subprocess.run(
                backend["refresh"],
                capture_output=True,
                text=True,
                timeout=300,
                env=backend["env"],
            )
            output = result.stdout + result.stderr
            status = "done" if result.returncode == 0 else "failed"
            if status == "done":
                packages = get_pending_updates()
                output = (output.rstrip() + "\n\n" if output.strip() else "") + f"Package metadata refreshed. Pending updates: {len(packages)}"
        except subprocess.TimeoutExpired:
            output = "Timeout after 300s"
            status = "failed"
        except Exception as e:
            output = str(e)
            status = "failed"
        return status, output

    elif jtype == "autoremove":
        backend = _pkg_backend()
        if not backend.get("autoremove"):
            return "failed", f"Autoremove is not supported on {backend['name']}"
        try:
            result = subprocess.run(
                backend["autoremove"],
                capture_output=True,
                text=True,
                timeout=300,
                env=backend["env"],
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

    elif jtype == "ack_config_review":
        _set_config_review(False)
        return "done", "Configuration review status acknowledged"

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


def _bootstrap_ca_cert(server_url: str):
    """Re-download CA cert from server with SHA-256 integrity verification.

    Uses an unverified TLS connection (bootstrap trust) which is inherent to
    the chicken-and-egg problem of deploying a new CA cert.  The SHA-256 hash
    is downloaded separately and must match — this doesn't prevent a full MITM
    but does catch partial corruption and ensures both endpoints agree.
    """
    import hashlib as _hl
    ca_url = f"{server_url}/agent/ca.pem"
    hash_url = f"{server_url}/agent/ca.pem.sha256"
    ca_path = CONFIG_DIR / "ca.pem"
    try:
        nossl = ssl.create_default_context()
        nossl.check_hostname = False
        nossl.verify_mode = ssl.CERT_NONE

        # Download cert + hash in quick succession
        req_cert = urlreq.Request(ca_url, method="GET")
        with urlreq.urlopen(req_cert, timeout=15, context=nossl) as r:
            cert_data = r.read()

        req_hash = urlreq.Request(hash_url, method="GET")
        with urlreq.urlopen(req_hash, timeout=15, context=nossl) as r:
            expected_hash = r.read().decode().split()[0].strip()

        # PEM format check
        if not cert_data.startswith(b"-----BEGIN CERTIFICATE-----"):
            print("[agent] WARNING: downloaded CA cert is not valid PEM, skipping", file=sys.stderr)
            return

        # SHA-256 integrity check
        actual_hash = _hl.sha256(cert_data).hexdigest()
        if actual_hash != expected_hash:
            print(f"[agent] WARNING: CA cert hash mismatch ({actual_hash[:16]} vs {expected_hash[:16]}), skipping", file=sys.stderr)
            return

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        ca_path.write_bytes(cert_data)
        os.chmod(str(ca_path), 0o644)
        _update_config_key("PATCHPILOT_CA_BUNDLE", str(ca_path))
        os.environ["PATCHPILOT_CA_BUNDLE"] = str(ca_path)
        _reload_ssl_context()
        print(f"[agent] CA cert re-bootstrapped at {ca_path} (sha256:{actual_hash[:16]})")
    except Exception as e:
        print(f"[agent] WARNING: CA cert bootstrap failed: {e}", file=sys.stderr)


def _update_self(params: dict) -> tuple:
    """Download the latest agent.py from the server, verify its SHA-256, and replace
    the running script.  The agent restarts automatically via systemd (Restart=always).
    """
    import hashlib as _hashlib
    import tempfile as _tempfile

    self_path = Path(__file__).resolve()

    # If the server inlined the code in the job params (SSL bootstrap), use it directly
    inline_code = params.get("inline_code")
    inline_sha = params.get("inline_sha256")
    if inline_code and inline_sha:
        import base64 as _b64
        try:
            new_code = _b64.b64decode(inline_code)
            actual_hash = _hashlib.sha256(new_code).hexdigest()
            if actual_hash != inline_sha:
                return "failed", f"Inline code SHA-256 mismatch: {actual_hash[:16]}… vs {inline_sha[:16]}…"
            print("[agent] Using inline agent code from job payload (SSL bootstrap)")
        except Exception as e:
            return "failed", f"Failed to decode inline agent code: {e}"
    else:
        # Download from server
        cfg = load_config()
        server_url = cfg.get("PATCHPILOT_SERVER", "").rstrip("/")
        if not server_url:
            return "failed", "PATCHPILOT_SERVER not set — cannot download update"

        agent_url = f"{server_url}/agent/agent.py"
        hash_url  = f"{server_url}/agent/agent.py.sha256"

        try:
            # Download SHA-256 checksum (with SSL bootstrap fallback)
            try:
                req_hash = urlreq.Request(hash_url, method="GET")
                with urlreq.urlopen(req_hash, timeout=30, context=_SSL_CTX) as r:
                    expected_hash = r.read().decode().split()[0].strip()
            except urllib.error.URLError as ssl_err:
                if "SSL" in str(ssl_err) or "CERTIFICATE" in str(ssl_err).upper():
                    print("[agent] SSL error — server cert may have changed, re-fetching CA cert...")
                    _bootstrap_ca_cert(server_url)
                    req_hash = urlreq.Request(hash_url, method="GET")
                    with urlreq.urlopen(req_hash, timeout=30, context=_SSL_CTX) as r:
                        expected_hash = r.read().decode().split()[0].strip()
                else:
                    raise

            # Download new agent binary
            req_agent = urlreq.Request(agent_url, method="GET")
            with urlreq.urlopen(req_agent, timeout=60, context=_SSL_CTX) as r:
                new_code = r.read()

            # Verify integrity
            actual_hash = _hashlib.sha256(new_code).hexdigest()
            if actual_hash != expected_hash:
                return "failed", f"SHA-256 mismatch: expected {expected_hash[:16]}… got {actual_hash[:16]}…"
        except Exception as e:
            return "failed", f"Update failed: {e}"

    # Common path: write new code to disk and restart
    try:
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
        # (Restart=always) relaunches with new code.
        pid = os.getpid()
        child = os.fork()
        if child == 0:
            time.sleep(4)
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            os._exit(0)

        return "done", f"Agent updated to {_hashlib.sha256(new_code).hexdigest()[:16]}… — restarting in 4s"
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

                # Refresh heartbeat after package metadata or upgrade jobs
                if job["type"] in {"patch", "dist_upgrade", "refresh_updates", "force_patch"}:
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

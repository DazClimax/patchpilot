import os
import secrets
import socket
import subprocess
from json import JSONDecodeError
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from deps import _get_db_ctx, require_role
from notifications import notification_manager
from scheduler import configure_timezone, get_scheduler_timezone

router = APIRouter()


@router.get("/api/push-config", dependencies=[Depends(require_role("admin"))])
def api_get_push_config():
    from app import _decrypt_secret

    with _get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key IN ('webhook_url', 'webhook_secret')"
        ).fetchall()
    values = {row["key"]: row["value"] for row in rows}
    secret = values.get("webhook_secret", "")
    if not secret:
        return {"webhookUrl": values.get("webhook_url", ""), "webhookSecret": None, "active": False}
    try:
        return {
            "webhookUrl": values.get("webhook_url", ""),
            "webhookSecret": _decrypt_secret(secret),
            "active": True,
        }
    except Exception:
        return {"webhookUrl": values.get("webhook_url", ""), "webhookSecret": None, "active": False}


@router.post("/api/settings/push-mobile/activate", dependencies=[Depends(require_role("admin"))])
async def api_activate_push_mobile(request: Request):
    from app import _decrypt_secret, _encrypt_secret, _validate_webhook_url

    with _get_db_ctx() as conn:
        try:
            data = await request.json()
            if not isinstance(data, dict):
                data = {}
        except JSONDecodeError:
            data = {}
        row_url = conn.execute("SELECT value FROM settings WHERE key='webhook_url'").fetchone()
        saved_webhook_url = row_url["value"] if row_url else ""
        webhook_url = _validate_webhook_url(data.get("webhook_url") or saved_webhook_url)
        row = conn.execute("SELECT value FROM settings WHERE key='webhook_secret'").fetchone()
        encrypted_secret = row["value"] if row else ""
        if encrypted_secret:
            webhook_secret = _decrypt_secret(encrypted_secret)
        else:
            webhook_secret = secrets.token_hex(32)
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('webhook_secret', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (_encrypt_secret(webhook_secret),),
            )
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('webhook_url', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (webhook_url,),
        )
    notification_manager.reload()
    return {"status": "activated", "webhookUrl": webhook_url, "webhookSecret": webhook_secret, "active": True}


@router.post("/api/settings/push-mobile/deactivate", dependencies=[Depends(require_role("admin"))])
def api_deactivate_push_mobile():
    with _get_db_ctx() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('webhook_secret', '') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        row = conn.execute("SELECT value FROM settings WHERE key='webhook_url'").fetchone()
    notification_manager.reload()
    webhook_url = row["value"] if row else ""
    return {"status": "deactivated", "webhookUrl": webhook_url, "webhookSecret": None, "active": False}


@router.get("/api/settings", dependencies=[Depends(require_role("admin"))])
def api_get_settings():
    from app import (
        _AGENT_PORT,
        _AGENT_SCHEME,
        _SERVER_PORT,
        _SETTINGS_ALLOWED_KEYS,
        _SENSITIVE_KEYS,
        _get_internal_ip,
    )

    with _get_db_ctx() as conn:
        rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
    result = {}
    for row in rows:
        key, value = row["key"], row["value"]
        if key not in _SETTINGS_ALLOWED_KEYS:
            continue
        result[key] = "***" if (key in _SENSITIVE_KEYS and value) else value
    scheme = "https" if os.environ.get("SSL_CERTFILE") else "http"
    ip = _get_internal_ip()
    result["internal_url"] = f"{scheme}://{ip}:{_SERVER_PORT}"
    result["agent_url"] = f"{_AGENT_SCHEME}://{ip}:{_AGENT_PORT}"
    result["ssl_enabled"] = bool(os.environ.get("SSL_CERTFILE"))
    return result


@router.post("/api/settings", dependencies=[Depends(require_role("admin"))])
@router.put("/api/settings", dependencies=[Depends(require_role("admin"))])
async def api_save_settings(request: Request):
    from app import (
        _SETTINGS_ALLOWED_KEYS,
        _SENSITIVE_KEYS,
        _TG_TOKEN_RE,
        _encrypt_secret,
        _schedule_restart,
        _update_env_key,
        _update_env_port,
        _validate_smtp_host,
        _validate_webhook_url,
    )

    data = await request.json()
    unknown = set(data.keys()) - _SETTINGS_ALLOWED_KEYS
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown settings key(s): {', '.join(sorted(unknown))}")
    tg_token = data.get("telegram_token", "")
    if tg_token and tg_token != "***" and not _TG_TOKEN_RE.match(tg_token):
        raise HTTPException(status_code=422, detail="Invalid Telegram token format")
    smtp_host = data.get("smtp_host", "")
    if smtp_host and smtp_host != "***":
        _validate_smtp_host(smtp_host)
    webhook_url = data.get("webhook_url")
    if webhook_url is not None and str(webhook_url) != "***":
        _validate_webhook_url(str(webhook_url))
    offline_min = data.get("notify_offline_minutes")
    if offline_min is not None and str(offline_min) != "***":
        try:
            val = int(offline_min)
            if not (1 <= val <= 10080):
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="notify_offline_minutes must be an integer between 1 and 10080")
    tz_val = data.get("scheduler_timezone")
    if tz_val is not None and str(tz_val) != "***":
        try:
            import zoneinfo
            zoneinfo.ZoneInfo(str(tz_val))
        except Exception:
            raise HTTPException(status_code=422, detail=f"Invalid timezone: {tz_val!r}")
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
    server_port_val = data.get("server_port")
    if server_port_val is not None and str(server_port_val) != "***":
        try:
            port_int = int(server_port_val)
            if not (1 <= port_int <= 65535):
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="server_port must be an integer between 1 and 65535")

    old_port = None
    old_agent_port = None
    old_agent_ssl = None
    old_timezone = None
    new_port_str = str(server_port_val) if (server_port_val is not None and str(server_port_val) != "***") else None
    with _get_db_ctx() as conn:
        if new_port_str:
            row = conn.execute("SELECT value FROM settings WHERE key='server_port'").fetchone()
            old_port = row["value"] if row else "8443"
        row_ap = conn.execute("SELECT value FROM settings WHERE key='agent_port'").fetchone()
        old_agent_port = row_ap["value"] if row_ap else "8050"
        row_as = conn.execute("SELECT value FROM settings WHERE key='agent_ssl'").fetchone()
        old_agent_ssl = row_as["value"] if row_as else "0"
        row_tz = conn.execute("SELECT value FROM settings WHERE key='scheduler_timezone'").fetchone()
        old_timezone = row_tz["value"] if row_tz and row_tz["value"] else get_scheduler_timezone()

    tg_valid = None
    if tg_token and tg_token != "***":
        try:
            import json as _json
            import urllib.request as _urlreq

            req = _urlreq.Request(
                f"https://api.telegram.org/bot{tg_token}/getMe",
                method="GET",
            )
            with _urlreq.urlopen(req, timeout=5) as resp:
                result = _json.loads(resp.read())
                tg_valid = result.get("ok", False)
        except Exception:
            tg_valid = False

    with _get_db_ctx() as conn:
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

    if tz_val and str(tz_val) != "***" and str(tz_val) != str(old_timezone or ""):
        configure_timezone(str(tz_val))
        from scheduler import load_schedules_from_db

        load_schedules_from_db()

    restart_pending = False
    if new_port_str and old_port and new_port_str != old_port:
        _update_env_port(new_port_str, old_port)
        restart_pending = True

    new_agent_port = data.get("agent_port")
    if new_agent_port and str(new_agent_port) != "***" and str(new_agent_port) != old_agent_port:
        _update_env_key("AGENT_PORT", str(new_agent_port))
        restart_pending = True

    new_agent_ssl = data.get("agent_ssl")
    if new_agent_ssl is not None and str(new_agent_ssl) != "***" and str(new_agent_ssl) != old_agent_ssl:
        _update_env_key("AGENT_SSL", "1" if str(new_agent_ssl) == "1" else "0")
        restart_pending = True

    if restart_pending:
        _schedule_restart(delay=1.5)

    return {"status": "saved", "restart_pending": restart_pending, "new_port": new_port_str, "telegram_valid": tg_valid}


@router.post("/api/settings/test/{channel}", dependencies=[Depends(require_role("admin"))])
async def api_test_notification(channel: str):
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
    elif channel == "push":
        notifier = notification_manager._webhook
        if not notifier or not getattr(notifier, "_url", "") or not getattr(notifier, "_secret", ""):
            raise HTTPException(status_code=400, detail="Mobile push not configured")
        ok = notifier.send_test()
    else:
        raise HTTPException(status_code=400, detail="Invalid notification channel")
    if not ok:
        raise HTTPException(status_code=502, detail="Notification send failed — check server logs")
    return {"status": "sent"}


@router.post("/api/settings/generate-cert", dependencies=[Depends(require_role("admin"))])
async def api_generate_cert(request: Request):
    from app import _SSL_DIR, _get_cert_info, _get_internal_ip

    try:
        data = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        years = max(1, min(10, int(data.get("years", 3))))
        days = years * 365

        _SSL_DIR.mkdir(parents=True, exist_ok=True)
        cert_path = _SSL_DIR / "cert.pem"
        key_path = _SSL_DIR / "key.pem"
        hostname = socket.gethostname()
        ip = _get_internal_ip()

        result = subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(key_path),
                "-out",
                str(cert_path),
                "-days",
                str(days),
                "-nodes",
                "-subj",
                f"/CN={hostname}",
                "-addext",
                f"subjectAltName=DNS:{hostname},IP:{ip}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"openssl failed: {result.stderr[:200]}")

        cert_path.chmod(0o644)
        key_path.chmod(0o600)

        with _get_db_ctx() as conn:
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


@router.post("/api/settings/ssl-enable", dependencies=[Depends(require_role("admin"))])
async def api_ssl_enable(request: Request):
    from app import _SSL_DIR, _get_cert_info, _schedule_restart, _update_env_key, _update_env_ssl

    data = await request.json()
    certfile = str(data.get("certfile", "")).strip()
    keyfile = str(data.get("keyfile", "")).strip()
    if not certfile or not keyfile:
        raise HTTPException(status_code=422, detail="Both certfile and keyfile paths are required")
    if not Path(certfile).resolve().is_relative_to(_SSL_DIR.resolve()):
        raise HTTPException(status_code=422, detail="Certificate path must be within the SSL directory")
    if not Path(keyfile).resolve().is_relative_to(_SSL_DIR.resolve()):
        raise HTTPException(status_code=422, detail="Key path must be within the SSL directory")
    if not Path(certfile).is_file():
        raise HTTPException(status_code=422, detail=f"Certificate file not found: {certfile}")
    if not Path(keyfile).is_file():
        raise HTTPException(status_code=422, detail=f"Key file not found: {keyfile}")

    try:
        _update_env_ssl(certfile, keyfile)
        _update_env_key("AGENT_SSL", "1")
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    with _get_db_ctx() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ssl_certfile', ?)", (str(certfile),))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ssl_keyfile', ?)", (str(keyfile),))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('agent_ssl', '1')")

    _schedule_restart(delay=2.0)
    info = _get_cert_info(certfile)
    return {"status": "enabled", "info": info, "restart_pending": True}


@router.post("/api/settings/ssl-disable", dependencies=[Depends(require_role("admin"))])
def api_ssl_disable():
    from app import _schedule_restart, _update_env_ssl

    try:
        _update_env_ssl("", "")
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    with _get_db_ctx() as conn:
        conn.execute("UPDATE settings SET value='' WHERE key='ssl_certfile'")
        conn.execute("UPDATE settings SET value='' WHERE key='ssl_keyfile'")
    _schedule_restart(delay=2.0)
    return {"status": "disabled", "restart_pending": True}


@router.get("/api/settings/ssl-info", dependencies=[Depends(require_role("admin"))])
def api_ssl_info():
    from app import _get_cert_info

    certfile = os.environ.get("SSL_CERTFILE", "")
    keyfile = os.environ.get("SSL_KEYFILE", "")
    enabled = bool(certfile and keyfile)
    info = _get_cert_info(certfile) if enabled else None
    if not info:
        with _get_db_ctx() as conn:
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

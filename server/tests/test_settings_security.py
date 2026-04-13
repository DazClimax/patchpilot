"""
test_settings_security.py — authorization tests for settings endpoints.
"""

import os

import app as app_module
import db as db_module
import notifications as notifications_module
import telegram_bot as telegram_bot_module

DEFAULT_PUSH_URL = "https://push.patch-pilot.app"


def _create_user(db_conn, username: str, role: str, password: str = "secret123") -> None:
    db_conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, app_module.hash_password(password), role),
    )
    db_conn.commit()


def _login(client, username: str, password: str) -> str:
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"x-admin-key": ""},
    )
    assert resp.status_code == 200
    return resp.json()["token"]


class TestSettingsAuthorization:
    def test_fresh_init_disables_notification_defaults(self, monkeypatch, tmp_path):
        db_path = tmp_path / "patchpilot.db"
        monkeypatch.setattr(db_module, "DB_PATH", db_path)
        monkeypatch.setenv("PATCHPILOT_ADMIN_PASSWORD", "Test123!secure")

        db_module.init_db()

        conn = db_module.get_db()
        try:
            rows = conn.execute(
                "SELECT key, value FROM settings WHERE key IN ("
                "'email_enabled', 'telegram_enabled', "
                "'telegram_notify_offline', 'telegram_notify_patches', "
                "'telegram_notify_failures', 'telegram_notify_success', "
                "'notify_offline', 'notify_patches', 'notify_failures', "
                "'agent_ssl'"
                ") ORDER BY key"
            ).fetchall()
        finally:
            conn.close()

        values = {row["key"]: row["value"] for row in rows}
        assert values["email_enabled"] == "0"
        assert values["telegram_enabled"] == "0"
        assert values["telegram_notify_offline"] == "0"
        assert values["telegram_notify_patches"] == "0"
        assert values["telegram_notify_failures"] == "0"
        assert values["telegram_notify_success"] == "0"
        assert values["notify_offline"] == "0"
        assert values["notify_patches"] == "0"
        assert values["notify_failures"] == "0"
        assert values["agent_ssl"] == "1"

    def test_readonly_user_cannot_get_settings(self, client, db_conn):
        _create_user(db_conn, "viewer", "readonly")
        token = _login(client, "viewer", "secret123")

        resp = client.get(
            "/api/settings",
            headers={"Authorization": f"Bearer {token}", "x-admin-key": ""},
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Insufficient permissions"

    def test_admin_bootstrap_includes_rollover_public_key(self, client):
        resp = client.get("/api/deploy/bootstrap")

        assert resp.status_code == 200
        data = resp.json()
        assert "ca_pem_b64" in data
        assert "ca_rollover_pub_pem_b64" in data
        assert data["ca_rollover_pub_pem_b64"]

    def test_user_cannot_get_settings(self, client, db_conn):
        _create_user(db_conn, "operator", "user")
        token = _login(client, "operator", "secret123")

        resp = client.get(
            "/api/settings",
            headers={"Authorization": f"Bearer {token}", "x-admin-key": ""},
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Insufficient permissions"

    def test_readonly_user_cannot_get_push_config(self, client, db_conn):
        _create_user(db_conn, "viewer", "readonly")
        token = _login(client, "viewer", "secret123")

        resp = client.get(
            "/api/push-config",
            headers={"Authorization": f"Bearer {token}", "x-admin-key": ""},
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Insufficient permissions"

    def test_user_cannot_activate_mobile_push(self, client, db_conn):
        _create_user(db_conn, "operator", "user")
        token = _login(client, "operator", "secret123")

        resp = client.post(
            "/api/settings/push-mobile/activate",
            json={"webhook_url": DEFAULT_PUSH_URL},
            headers={"Authorization": f"Bearer {token}", "x-admin-key": ""},
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Insufficient permissions"

    def test_user_cannot_deactivate_mobile_push(self, client, db_conn):
        _create_user(db_conn, "operator2", "user")
        token = _login(client, "operator2", "secret123")

        resp = client.post(
            "/api/settings/push-mobile/deactivate",
            headers={"Authorization": f"Bearer {token}", "x-admin-key": ""},
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Insufficient permissions"

    def test_admin_settings_get_does_not_auto_generate_push_secret(self, client, db_conn):
        resp = client.get("/api/settings")

        assert resp.status_code == 200
        row = db_conn.execute("SELECT value FROM settings WHERE key='webhook_secret'").fetchone()
        assert row is None

    def test_admin_can_activate_mobile_push(self, client, db_conn):
        resp = client.post(
            "/api/settings/push-mobile/activate",
            json={"webhook_url": DEFAULT_PUSH_URL},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "activated"
        assert data["active"] is True
        assert data["webhookUrl"] == DEFAULT_PUSH_URL
        assert len(data["webhookSecret"]) == 64

        row = db_conn.execute("SELECT value FROM settings WHERE key='webhook_secret'").fetchone()
        assert row is not None
        assert row["value"]

    def test_admin_can_save_settings_via_put_alias(self, client, db_conn):
        resp = client.put(
            "/api/settings",
            json={"webhook_url": DEFAULT_PUSH_URL},
        )

        assert resp.status_code == 200
        row = db_conn.execute("SELECT value FROM settings WHERE key='webhook_url'").fetchone()
        assert row is not None
        assert row["value"] == DEFAULT_PUSH_URL

    def test_admin_can_disable_telegram_without_reconfiguring_unchanged_timezone(self, client, db_conn, monkeypatch):
        db_conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("scheduler_timezone", "Europe/Berlin"),
        )
        db_conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("telegram_enabled", "1"),
        )
        db_conn.commit()

        called = {"configure": 0, "reload": 0}

        def fake_configure_timezone(_tz: str):
            called["configure"] += 1

        def fake_load_schedules_from_db():
            called["reload"] += 1

        monkeypatch.setattr(app_module, "configure_timezone", fake_configure_timezone)
        monkeypatch.setattr(telegram_bot_module.telegram_bot, "reload_settings", lambda: None)
        monkeypatch.setattr(app_module.notification_manager, "reload", lambda: None)
        monkeypatch.setattr("scheduler.load_schedules_from_db", fake_load_schedules_from_db)

        resp = client.post(
            "/api/settings",
            json={
                "telegram_enabled": "0",
                "scheduler_timezone": "Europe/Berlin",
            },
        )

        assert resp.status_code == 200
        assert called == {"configure": 0, "reload": 0}
        row = db_conn.execute("SELECT value FROM settings WHERE key='telegram_enabled'").fetchone()
        assert row is not None
        assert row["value"] == "0"

    def test_admin_can_read_existing_push_config(self, client):
        activate = client.post(
            "/api/settings/push-mobile/activate",
            json={"webhook_url": DEFAULT_PUSH_URL},
        )
        assert activate.status_code == 200

        resp = client.get("/api/push-config")

        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is True
        assert data["webhookUrl"] == DEFAULT_PUSH_URL
        assert len(data["webhookSecret"]) == 64

    def test_admin_can_deactivate_mobile_push(self, client, db_conn):
        activate = client.post(
            "/api/settings/push-mobile/activate",
            json={"webhook_url": DEFAULT_PUSH_URL},
        )
        assert activate.status_code == 200

        resp = client.post("/api/settings/push-mobile/deactivate")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deactivated"
        assert data["active"] is False
        assert data["webhookSecret"] is None
        assert data["webhookUrl"] == DEFAULT_PUSH_URL

        row = db_conn.execute("SELECT value FROM settings WHERE key='webhook_secret'").fetchone()
        assert row is not None
        assert row["value"] == ""

    def test_admin_can_send_mobile_push_test(self, client, monkeypatch):
        webhook = app_module.notification_manager._webhook
        monkeypatch.setattr(app_module.notification_manager, "reload", lambda: None)
        monkeypatch.setattr(app_module.notification_manager, "_load", lambda: None)
        monkeypatch.setattr(webhook, "_url", DEFAULT_PUSH_URL)
        monkeypatch.setattr(webhook, "_secret", "test-secret")
        monkeypatch.setattr(webhook, "send_test", lambda: True)

        resp = client.post("/api/settings/test/push")

        assert resp.status_code == 200
        assert resp.json()["status"] == "sent"

    def test_webhook_send_test_uses_updates_available_payload(self):
        webhook = notifications_module.WebhookNotifier()
        webhook._url = DEFAULT_PUSH_URL
        webhook._secret = "test-secret"

        calls: list[tuple[str, str, str]] = []

        def fake_post(event: str, hostname: str, details: str = "") -> bool:
            calls.append((event, hostname, details))
            return True

        webhook._post = fake_post  # type: ignore[method-assign]

        ok = webhook.send_test()

        assert ok is True
        assert calls == [("updates_available", "Test1", "12")]

    def test_activate_mobile_push_rejects_invalid_url(self, client):
        resp = client.post(
            "/api/settings/push-mobile/activate",
            json={"webhook_url": "file:///tmp/push"},
        )

        assert resp.status_code == 422
        assert resp.json()["detail"] == "Webhook URL must be a valid http(s) URL"


class TestSslSettings:
    def test_ssl_enable_forces_agent_ssl(self, client, db_conn, monkeypatch, tmp_path):
        ssl_dir = tmp_path / "ssl"
        ssl_dir.mkdir()
        certfile = ssl_dir / "cert.pem"
        keyfile = ssl_dir / "key.pem"
        certfile.write_text("-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----\n")
        keyfile.write_text("-----BEGIN PRIVATE KEY-----\nTEST\n-----END PRIVATE KEY-----\n")

        monkeypatch.setattr(app_module, "_SSL_DIR", ssl_dir)
        monkeypatch.setattr(app_module, "_schedule_restart", lambda delay=0: None)
        monkeypatch.setattr(app_module, "_get_cert_info", lambda path: {"subject": "test", "expires": "never", "path": path})

        updates: list[tuple[str, str]] = []
        original_env = os.environ.copy()

        def fake_update_env_ssl(cert: str, key: str):
            updates.append(("ssl", f"{cert}|{key}"))

        def fake_update_env_key(key: str, value: str):
            updates.append((key, value))

        monkeypatch.setattr(app_module, "_update_env_ssl", fake_update_env_ssl)
        monkeypatch.setattr(app_module, "_update_env_key", fake_update_env_key)

        try:
            resp = client.post(
                "/api/settings/ssl-enable",
                json={"certfile": str(certfile), "keyfile": str(keyfile)},
            )
        finally:
            os.environ.clear()
            os.environ.update(original_env)

        assert resp.status_code == 200
        assert ("AGENT_SSL", "1") in updates
        row = db_conn.execute("SELECT value FROM settings WHERE key='agent_ssl'").fetchone()
        assert row is not None
        assert row["value"] == "1"

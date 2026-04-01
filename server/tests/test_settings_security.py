"""
test_settings_security.py — authorization tests for settings endpoints.
"""

import os

import app as app_module


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

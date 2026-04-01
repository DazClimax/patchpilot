"""
test_settings_security.py — authorization tests for settings endpoints.
"""

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

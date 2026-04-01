"""
test_security.py — security and isolation tests.
"""

import secrets
import pytest
import app as app_module


def _create_user(db_conn, username: str, role: str = "user", password: str = "secret123") -> int:
    db_conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, app_module.hash_password(password), role),
    )
    db_conn.commit()
    row = db_conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    return int(row["id"])


def _login(client, username: str, password: str) -> str:
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"x-admin-key": ""},
    )
    assert resp.status_code == 200
    return resp.json()["token"]


# ---------------------------------------------------------------------------
# Token validation on agent endpoints
# ---------------------------------------------------------------------------

class TestInvalidToken:
    def test_heartbeat_wrong_token_is_401(self, client, registered_agent):
        agent_id, _ = registered_agent
        resp = client.post(
            f"/api/agents/{agent_id}/heartbeat",
            json={"packages": []},
            headers={"x-token": "completely-wrong"},
        )
        assert resp.status_code == 401

    def test_get_jobs_wrong_token_is_401(self, client, registered_agent):
        agent_id, _ = registered_agent
        resp = client.get(
            f"/api/agents/{agent_id}/jobs",
            headers={"x-token": "wrong-token"},
        )
        assert resp.status_code == 401

    def test_job_result_wrong_token_is_401(self, client, registered_agent):
        agent_id, token = registered_agent
        # Create and poll a job to get its ID
        client.post(f"/api/agents/{agent_id}/jobs", json={"type": "patch", "params": {}})
        jobs = client.get(f"/api/agents/{agent_id}/jobs", headers={"x-token": token}).json()
        job_id = jobs[0]["id"]

        resp = client.post(
            f"/api/agents/{agent_id}/jobs/{job_id}/result",
            json={"status": "done", "output": ""},
            headers={"x-token": "bad-token"},
        )
        assert resp.status_code == 401

    def test_empty_string_token_is_401(self, client, registered_agent):
        agent_id, _ = registered_agent
        resp = client.get(
            f"/api/agents/{agent_id}/jobs",
            headers={"x-token": ""},
        )
        assert resp.status_code == 401


class TestMissingToken:
    def test_heartbeat_no_token_header_is_422(self, client, registered_agent):
        agent_id, _ = registered_agent
        resp = client.post(
            f"/api/agents/{agent_id}/heartbeat",
            json={"packages": []},
            # intentionally no x-token
        )
        assert resp.status_code == 422

    def test_get_jobs_no_token_header_is_422(self, client, registered_agent):
        agent_id, _ = registered_agent
        resp = client.get(f"/api/agents/{agent_id}/jobs")
        assert resp.status_code == 422

    def test_job_result_no_token_header_is_422(self, client, registered_agent):
        agent_id, token = registered_agent
        client.post(f"/api/agents/{agent_id}/jobs", json={"type": "patch", "params": {}})
        jobs = client.get(f"/api/agents/{agent_id}/jobs", headers={"x-token": token}).json()
        job_id = jobs[0]["id"]

        resp = client.post(
            f"/api/agents/{agent_id}/jobs/{job_id}/result",
            json={"status": "done", "output": ""},
            # no x-token header
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Cross-agent isolation — agent A cannot see agent B's jobs
# ---------------------------------------------------------------------------

class TestCrossAgentIsolation:
    def _register(self, client, suffix=""):
        agent_id = f"iso-agent-{suffix}-{secrets.token_hex(4)}"
        token = secrets.token_hex(16)
        resp = client.post(
            "/api/agents/register",
            json={"id": agent_id, "token": token, "hostname": f"host-{suffix}"},
        )
        assert resp.status_code == 200
        return resp.json()["agent_id"], resp.json()["token"]

    def test_agent_cannot_poll_another_agents_jobs(self, client):
        id_a, tok_a = self._register(client, "a")
        id_b, tok_b = self._register(client, "b")

        # Create a job for agent A
        client.post(f"/api/agents/{id_a}/jobs", json={"type": "patch", "params": {}})

        # Agent B polls its own queue — should be empty
        resp = client.get(f"/api/agents/{id_b}/jobs", headers={"x-token": tok_b})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_agent_b_token_rejected_for_agent_a_endpoint(self, client):
        id_a, tok_a = self._register(client, "a2")
        id_b, tok_b = self._register(client, "b2")

        # Agent B's token used on Agent A's heartbeat endpoint
        resp = client.post(
            f"/api/agents/{id_a}/heartbeat",
            json={"packages": []},
            headers={"x-token": tok_b},
        )
        assert resp.status_code == 401

    def test_agent_b_cannot_read_agent_a_job_result_endpoint(self, client):
        id_a, tok_a = self._register(client, "a3")
        id_b, tok_b = self._register(client, "b3")

        # Create and poll a job for agent A
        client.post(f"/api/agents/{id_a}/jobs", json={"type": "refresh_updates", "params": {}})
        jobs = client.get(f"/api/agents/{id_a}/jobs", headers={"x-token": tok_a}).json()
        job_id = jobs[0]["id"]

        # Agent B tries to submit a result for agent A's job
        resp = client.post(
            f"/api/agents/{id_a}/jobs/{job_id}/result",
            json={"status": "done", "output": "hijacked"},
            headers={"x-token": tok_b},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Heartbeat with wrong agent ID
# ---------------------------------------------------------------------------

class TestWrongAgentId:
    def test_heartbeat_nonexistent_agent_id_is_401(self, client):
        """A valid-looking token against a non-existent agent ID must return 401."""
        resp = client.post(
            "/api/agents/nonexistent-id/heartbeat",
            json={"packages": []},
            headers={"x-token": "some-token"},
        )
        assert resp.status_code == 401

    def test_get_jobs_nonexistent_agent_id_is_401(self, client):
        resp = client.get(
            "/api/agents/ghost-agent/jobs",
            headers={"x-token": "some-token"},
        )
        assert resp.status_code == 401

    def test_correct_token_wrong_agent_id_is_401(self, client, registered_agent):
        """Use a real token but for a different (non-existent) agent ID."""
        _, token = registered_agent
        resp = client.post(
            "/api/agents/wrong-agent-id/heartbeat",
            json={"packages": []},
            headers={"x-token": token},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# User-management protection rules
# ---------------------------------------------------------------------------

class TestUserProtection:
    def test_session_admin_cannot_delete_self(self, client, db_conn):
        user_id = _create_user(db_conn, "self-admin", role="admin", password="secret123")
        token = _login(client, "self-admin", "secret123")

        resp = client.delete(
            f"/api/users/{user_id}",
            headers={"Authorization": f"Bearer {token}", "x-admin-key": ""},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Cannot delete yourself"

    def test_last_admin_cannot_be_deleted(self, client, db_conn):
        user_id = _create_user(db_conn, "last-admin", role="admin", password="secret123")

        resp = client.delete(f"/api/users/{user_id}")

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Cannot delete the last admin user"

    def test_session_admin_cannot_remove_own_admin_role(self, client, db_conn):
        user_id = _create_user(db_conn, "role-admin", role="admin", password="secret123")
        token = _login(client, "role-admin", "secret123")

        resp = client.patch(
            f"/api/users/{user_id}",
            json={"role": "user"},
            headers={"Authorization": f"Bearer {token}", "x-admin-key": ""},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "You cannot remove your own admin role"

    def test_last_admin_cannot_be_demoted(self, client, db_conn):
        user_id = _create_user(db_conn, "only-admin", role="admin", password="secret123")

        resp = client.patch(f"/api/users/{user_id}", json={"role": "readonly"})

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Cannot demote the last admin user"

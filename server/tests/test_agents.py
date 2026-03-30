"""
test_agents.py — tests for agent and job endpoints.
"""

import secrets
import pytest


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------

class TestAgentRegistration:
    def test_register_new_agent_returns_id_and_token(self, client):
        resp = client.post(
            "/api/agents/register",
            json={"hostname": "myhost", "ip": "192.168.1.1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "agent_id" in data
        assert "token" in data
        assert len(data["token"]) > 0

    def test_register_with_explicit_id_and_token(self, client):
        agent_id = "explicit-id-001"
        resp = client.post(
            "/api/agents/register",
            json={"id": agent_id, "token": "explicit-token-abc", "hostname": "host1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == agent_id
        assert isinstance(data["token"], str)
        assert len(data["token"]) > 0

    def test_register_same_id_returns_existing_token(self, client):
        agent_id = "duplicate-agent"
        first = client.post("/api/agents/register", json={"id": agent_id, "token": "original-token", "hostname": "h"})
        resp = client.post("/api/agents/register", json={"id": agent_id, "token": "new-token", "hostname": "h"})
        assert resp.status_code == 200
        assert first.status_code == 200
        # Re-registration rotates the returned token.
        assert resp.json()["token"] != first.json()["token"]

    def test_register_stores_agent_metadata(self, client):
        resp = client.post(
            "/api/agents/register",
            json={
                "hostname": "debianhost",
                "ip": "10.10.10.1",
                "os_pretty": "Debian GNU/Linux 12",
                "kernel": "6.1.0-20-amd64",
                "arch": "x86_64",
            },
        )
        assert resp.status_code == 200
        agent_id = resp.json()["agent_id"]
        # Verify via dashboard
        dash = client.get("/api/dashboard")
        agents = dash.json()["agents"]
        found = next((a for a in agents if a["id"] == agent_id), None)
        assert found is not None
        assert found["hostname"] == "debianhost"
        assert found["arch"] == "x86_64"


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

class TestHeartbeat:
    def test_heartbeat_valid_token_returns_ok(self, client, registered_agent):
        agent_id, token = registered_agent
        resp = client.post(
            f"/api/agents/{agent_id}/heartbeat",
            json={"hostname": "testhost", "packages": []},
            headers={"x-token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_heartbeat_invalid_token_returns_401(self, client, registered_agent):
        agent_id, _ = registered_agent
        resp = client.post(
            f"/api/agents/{agent_id}/heartbeat",
            json={"hostname": "testhost", "packages": []},
            headers={"x-token": "wrong-token"},
        )
        assert resp.status_code == 401

    def test_heartbeat_missing_token_returns_422(self, client, registered_agent):
        agent_id, _ = registered_agent
        resp = client.post(
            f"/api/agents/{agent_id}/heartbeat",
            json={"hostname": "testhost", "packages": []},
            # no x-token header
        )
        assert resp.status_code == 422

    def test_heartbeat_updates_packages(self, client, registered_agent):
        agent_id, token = registered_agent
        packages = [
            {"name": "bash", "current": "5.1", "new": "5.2"},
            {"name": "curl", "current": "7.88", "new": "7.90"},
        ]
        resp = client.post(
            f"/api/agents/{agent_id}/heartbeat",
            json={"hostname": "testhost", "packages": packages},
            headers={"x-token": token},
        )
        assert resp.status_code == 200
        detail = client.get(f"/api/agents/{agent_id}")
        pkg_names = [p["name"] for p in detail.json()["packages"]]
        assert "bash" in pkg_names
        assert "curl" in pkg_names

    def test_heartbeat_updates_pending_count(self, client, registered_agent):
        agent_id, token = registered_agent
        packages = [{"name": f"pkg{i}", "current": "1.0", "new": "2.0"} for i in range(5)]
        client.post(
            f"/api/agents/{agent_id}/heartbeat",
            json={"packages": packages},
            headers={"x-token": token},
        )
        detail = client.get(f"/api/agents/{agent_id}")
        assert detail.json()["agent"]["pending_count"] == 5


# ---------------------------------------------------------------------------
# Job polling
# ---------------------------------------------------------------------------

class TestJobPolling:
    def test_poll_jobs_empty(self, client, registered_agent):
        agent_id, token = registered_agent
        resp = client.get(
            f"/api/agents/{agent_id}/jobs",
            headers={"x-token": token},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_poll_jobs_returns_pending_jobs(self, client, registered_agent):
        agent_id, token = registered_agent
        # Create a job via the web API
        client.post(f"/api/agents/{agent_id}/jobs", json={"type": "patch", "params": {}})
        resp = client.get(f"/api/agents/{agent_id}/jobs", headers={"x-token": token})
        assert resp.status_code == 200
        jobs = resp.json()
        assert len(jobs) == 1
        assert jobs[0]["type"] == "patch"

    def test_poll_jobs_marks_running(self, client, registered_agent):
        agent_id, token = registered_agent
        client.post(f"/api/agents/{agent_id}/jobs", json={"type": "patch", "params": {}})
        # First poll returns the job and marks it running
        client.get(f"/api/agents/{agent_id}/jobs", headers={"x-token": token})
        # Second poll should return nothing (already running, not pending)
        resp2 = client.get(f"/api/agents/{agent_id}/jobs", headers={"x-token": token})
        assert resp2.json() == []

    def test_poll_jobs_invalid_token(self, client, registered_agent):
        agent_id, _ = registered_agent
        resp = client.get(f"/api/agents/{agent_id}/jobs", headers={"x-token": "bad"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Job result
# ---------------------------------------------------------------------------

class TestJobResult:
    def test_submit_job_result(self, client, registered_agent):
        agent_id, token = registered_agent
        client.post(f"/api/agents/{agent_id}/jobs", json={"type": "patch", "params": {}})
        jobs = client.get(f"/api/agents/{agent_id}/jobs", headers={"x-token": token}).json()
        job_id = jobs[0]["id"]

        resp = client.post(
            f"/api/agents/{agent_id}/jobs/{job_id}/result",
            json={"status": "done", "output": "All packages upgraded."},
            headers={"x-token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_job_result_updates_status(self, client, registered_agent):
        agent_id, token = registered_agent
        client.post(f"/api/agents/{agent_id}/jobs", json={"type": "patch", "params": {}})
        jobs = client.get(f"/api/agents/{agent_id}/jobs", headers={"x-token": token}).json()
        job_id = jobs[0]["id"]

        client.post(
            f"/api/agents/{agent_id}/jobs/{job_id}/result",
            json={"status": "done", "output": "ok"},
            headers={"x-token": token},
        )
        detail = client.get(f"/api/agents/{agent_id}").json()
        job = next(j for j in detail["jobs"] if j["id"] == job_id)
        assert job["status"] == "done"
        assert job["output"] == "ok"

    def test_job_result_invalid_token(self, client, registered_agent):
        agent_id, token = registered_agent
        client.post(f"/api/agents/{agent_id}/jobs", json={"type": "patch", "params": {}})
        jobs = client.get(f"/api/agents/{agent_id}/jobs", headers={"x-token": token}).json()
        job_id = jobs[0]["id"]

        resp = client.post(
            f"/api/agents/{agent_id}/jobs/{job_id}/result",
            json={"status": "done", "output": ""},
            headers={"x-token": "wrong"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_dashboard_empty(self, client):
        resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "stats" in data
        assert data["stats"]["total"] == 0

    def test_dashboard_reflects_registered_agents(self, client, registered_agent):
        agent_id, _ = registered_agent
        resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stats"]["total"] >= 1
        ids = [a["id"] for a in data["agents"]]
        assert agent_id in ids

    def test_dashboard_stats_reboot_needed(self, client, registered_agent):
        agent_id, token = registered_agent
        client.post(
            f"/api/agents/{agent_id}/heartbeat",
            json={"reboot_required": True, "packages": []},
            headers={"x-token": token},
        )
        resp = client.get("/api/dashboard")
        assert resp.json()["stats"]["reboot_needed"] >= 1


# ---------------------------------------------------------------------------
# Agent detail
# ---------------------------------------------------------------------------

class TestAgentDetail:
    def test_get_agent_detail(self, client, registered_agent):
        agent_id, _ = registered_agent
        resp = client.get(f"/api/agents/{agent_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent"]["id"] == agent_id
        assert "packages" in data
        assert "jobs" in data

    def test_get_nonexistent_agent_returns_404(self, client):
        resp = client.get("/api/agents/does-not-exist")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Create job (web API)
# ---------------------------------------------------------------------------

class TestCreateJob:
    def test_create_job_returns_queued(self, client, registered_agent):
        agent_id, _ = registered_agent
        resp = client.post(
            f"/api/agents/{agent_id}/jobs",
            json={"type": "patch", "params": {"packages": ["bash"]}},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    def test_created_job_appears_in_agent_detail(self, client, registered_agent):
        agent_id, _ = registered_agent
        client.post(f"/api/agents/{agent_id}/jobs", json={"type": "refresh_updates", "params": {}})
        detail = client.get(f"/api/agents/{agent_id}").json()
        job_types = [j["type"] for j in detail["jobs"]]
        assert "refresh_updates" in job_types


# ---------------------------------------------------------------------------
# Delete agent
# ---------------------------------------------------------------------------

class TestDeleteAgent:
    def test_delete_existing_agent(self, client, registered_agent):
        agent_id, _ = registered_agent
        resp = client.delete(f"/api/agents/{agent_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_deleted_agent_no_longer_in_dashboard(self, client, registered_agent):
        agent_id, _ = registered_agent
        client.delete(f"/api/agents/{agent_id}")
        dash = client.get("/api/dashboard").json()
        ids = [a["id"] for a in dash["agents"]]
        assert agent_id not in ids

    def test_delete_nonexistent_agent_returns_200(self, client):
        # DELETE is idempotent — deleting a non-existent agent should not error
        resp = client.delete("/api/agents/ghost-agent")
        assert resp.status_code == 200

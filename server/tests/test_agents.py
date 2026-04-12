"""
test_agents.py — tests for agent and job endpoints.
"""
from datetime import datetime
import json
import secrets
from unittest.mock import patch
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

    def test_dashboard_uses_live_package_count_not_stale_agent_counter(self, client, db_conn):
        db_conn.execute(
            """
            INSERT INTO agents (id, hostname, token, pending_count, last_seen)
            VALUES (?, ?, ?, ?, datetime('now','localtime'))
            """,
            ("ha-agent", "homeassistant", "token", 0),
        )
        db_conn.execute(
            "INSERT INTO packages (agent_id, name, current_ver, new_ver) VALUES (?, ?, ?, ?)",
            ("ha-agent", "Power Flow Card Plus update", "0.2.6", "0.2.7"),
        )
        db_conn.commit()

        dash = client.get("/api/dashboard")
        assert dash.status_code == 200
        payload = dash.json()
        row = next(a for a in payload["agents"] if a["id"] == "ha-agent")
        assert row["pending_count"] == 1
        assert payload["stats"]["total_pending"] == 1


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


class TestUpdateBatchStatus:
    def test_linux_agent_version_marks_batch_done(self, client, registered_agent, db_conn):
        agent_id, token = registered_agent
        batch = "abc123"
        client.post(
            f"/api/agents/{agent_id}/heartbeat",
            json={"hostname": "testhost", "agent_version": "1.3", "packages": []},
            headers={"x-token": token},
        )
        db_conn.execute(
            "INSERT INTO jobs (agent_id, type, status, params) VALUES (?, 'update_agent', 'running', ?)",
            (agent_id, json.dumps({"batch": batch})),
        )
        db_conn.commit()

        resp = client.get(f"/api/agents/update-batch/status?batch={batch}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["total_online"] == 1
        assert data["completed"] == 1
        assert data["agents"][0]["status"] == "done"
        assert data["agents"][0]["phase"] == "done"

    def test_ssl_deploy_status_includes_haos_deploy_ssl_jobs(self, client, db_conn):
        batch = "beefcafe"
        agent_id = "ha-agent-1"
        db_conn.execute(
            """
            INSERT INTO agents (id, hostname, token, agent_type, last_seen)
            VALUES (?, ?, ?, 'haos', datetime('now','localtime'))
            """,
            (agent_id, "homeassistant", "token-ha"),
        )
        db_conn.execute(
            "INSERT INTO jobs (agent_id, type, status, params) VALUES (?, 'deploy_ssl', 'running', ?)",
            (agent_id, json.dumps({"batch": batch})),
        )
        db_conn.commit()

        resp = client.get(f"/api/settings/deploy-ssl/status?batch={batch}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["total_online"] == 1
        assert data["completed"] == 0
        assert data["agents"][0]["hostname"] == "homeassistant"
        assert data["agents"][0]["phase"] == "deploying"
        assert data["agents"][0]["status"] == "running"

    def test_running_update_counts_as_online_during_grace_window(self, client, db_conn):
        agent_id = "busy-agent"
        ten_minutes_ago = "2026-04-12 09:00:00"
        two_minutes_ago = "2026-04-12 09:08:30"
        now = "2026-04-12 09:10:40"
        db_conn.execute(
            """
            INSERT INTO agents (id, hostname, token, last_seen)
            VALUES (?, ?, ?, ?)
            """,
            (agent_id, "worker-1", "token", ten_minutes_ago),
        )
        db_conn.execute(
            """
            INSERT INTO jobs (agent_id, type, status, created, started, params)
            VALUES (?, 'patch', 'running', ?, ?, '{}')
            """,
            (agent_id, two_minutes_ago, two_minutes_ago),
        )
        db_conn.commit()

        with patch("app.datetime") as app_dt, patch("scheduler.datetime") as scheduler_dt:
            real_datetime = datetime
            frozen = real_datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
            app_dt.now.return_value = frozen
            app_dt.strptime.side_effect = lambda *args, **kwargs: real_datetime.strptime(*args, **kwargs)
            scheduler_dt.now.return_value = frozen
            scheduler_dt.strptime.side_effect = lambda *args, **kwargs: real_datetime.strptime(*args, **kwargs)
            dash = client.get("/api/dashboard")

        assert dash.status_code == 200
        data = dash.json()
        assert data["stats"]["online"] == 1
        row = data["agents"][0]
        assert row["effective_online"] is True
        assert row["connectivity_state"] == "busy"


class TestHaUpdateCallback:
    def test_callback_updates_matching_ha_job_output(self, client, registered_agent, db_conn):
        agent_id, token = registered_agent
        batch = "feedcafe"
        db_conn.execute(
            "INSERT INTO jobs (agent_id, type, status, params) VALUES (?, 'ha_trigger_agent_update', 'done', ?)",
            (agent_id, json.dumps({"batch": batch})),
        )
        db_conn.commit()

        resp = client.post(
            f"/api/agents/{agent_id}/ha-update-callback",
            json={"batch": batch, "agent_version": "1.7"},
            headers={"x-token": token},
        )

        assert resp.status_code == 200
        row = db_conn.execute(
            "SELECT output FROM jobs WHERE agent_id=? AND type='ha_trigger_agent_update' ORDER BY id DESC LIMIT 1",
            (agent_id,),
        ).fetchone()
        assert row is not None
        assert "1.7" in row["output"]


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

    def test_monitor_only_ping_target_rejects_jobs(self, client, db_conn):
        db_conn.execute(
            """
            INSERT INTO agents (id, hostname, ip, token, agent_type, protocol)
            VALUES (?, ?, ?, ?, 'ping', 'icmp')
            """,
            ("fritzbox", "FRITZ!Box", "192.168.178.1", "token"),
        )
        db_conn.commit()

        resp = client.post(
            "/api/agents/fritzbox/jobs",
            json={"type": "patch", "params": {}},
        )

        assert resp.status_code == 422
        assert "monitor-only" in resp.json()["detail"]

    def test_ha_entity_update_job_allowed_for_haos_with_capability(self, client, db_conn):
        db_conn.execute(
            """
            INSERT INTO agents (id, hostname, token, agent_type, capabilities)
            VALUES (?, ?, ?, 'haos', ?)
            """,
            ("ha-agent", "homeassistant", "token", "ha_backup,ha_core_update,ha_supervisor_update,ha_os_update,ha_addon_update,ha_addons_update,ha_entity_update"),
        )
        db_conn.commit()

        resp = client.post(
            "/api/agents/ha-agent/jobs",
            json={"type": "ha_entity_update", "params": {"entity_id": "update.power_flow_card_plus_update"}},
        )

        assert resp.status_code == 200
        row = db_conn.execute(
            "SELECT type, params FROM jobs WHERE agent_id='ha-agent' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert row["type"] == "ha_entity_update"
        assert "update.power_flow_card_plus_update" in row["params"]

    def test_running_ha_core_job_is_shown_done_after_heartbeat_without_pending_package(self, client, db_conn):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_conn.execute(
            """
            INSERT INTO agents (id, hostname, token, agent_type, capabilities, last_seen)
            VALUES (?, ?, ?, 'haos', ?, ?)
            """,
            (
                "ha-agent",
                "homeassistant",
                "token",
                "ha_backup,ha_core_update,ha_supervisor_update,ha_os_update,ha_addon_update,ha_addons_update,ha_entity_update",
                now,
            ),
        )
        db_conn.execute(
            """
            INSERT INTO jobs (agent_id, type, status, started, params, created)
            VALUES (?, 'ha_core_update', 'running', ?, '{}', ?)
            """,
            ("ha-agent", now, now),
        )
        db_conn.commit()

        detail = client.get("/api/agents/ha-agent")
        assert detail.status_code == 200
        assert detail.json()["jobs"][0]["status"] == "done"

        dash = client.get("/api/dashboard")
        row = next(a for a in dash.json()["agents"] if a["id"] == "ha-agent")
        assert row["last_job_status"] == "done"


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


class TestPingTargets:
    def test_admin_can_create_ping_target(self, client, monkeypatch):
        monkeypatch.setattr("app.trigger_ping_check_for_agent", lambda agent_id: True)

        resp = client.post(
            "/api/agents/ping-targets",
            json={"hostname": "FRITZ!Box", "address": "192.168.178.1"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert data["reachable"] is True
        assert data["agent"]["agent_type"] == "ping"
        assert data["agent"]["protocol"] == "icmp"

    def test_ping_check_endpoint_triggers_probe(self, client, db_conn, monkeypatch):
        db_conn.execute(
            """
            INSERT INTO agents (id, hostname, ip, token, agent_type, protocol)
            VALUES (?, ?, ?, ?, 'ping', 'icmp')
            """,
            ("fritzbox", "FRITZ!Box", "192.168.178.1", "token"),
        )
        db_conn.commit()
        called = {"agent_id": None}

        def _fake_check(agent_id: str):
            called["agent_id"] = agent_id
            return True

        monkeypatch.setattr("app.trigger_ping_check_for_agent", _fake_check)

        resp = client.post("/api/agents/fritzbox/ping-check")

        assert resp.status_code == 200
        assert resp.json()["reachable"] is True
        assert called["agent_id"] == "fritzbox"

    def test_ping_target_stays_busy_until_third_failed_check(self, client, db_conn):
        db_conn.execute(
            """
            INSERT INTO agents (
                id, hostname, ip, token, agent_type, protocol,
                ping_failures, ping_last_checked, last_seen
            )
            VALUES (?, ?, ?, ?, 'ping', 'icmp', ?, ?, ?)
            """,
            ("fritzbox", "FRITZ!Box", "192.168.178.1", "token", 2, "2026-04-12 10:01:00", "2026-04-12 10:00:00"),
        )
        db_conn.commit()

        dash = client.get("/api/dashboard")

        assert dash.status_code == 200
        row = next(a for a in dash.json()["agents"] if a["id"] == "fritzbox")
        assert row["effective_online"] is True
        assert row["connectivity_state"] == "busy"

    def test_ping_target_becomes_offline_after_third_failed_check(self, client, db_conn):
        db_conn.execute(
            """
            INSERT INTO agents (
                id, hostname, ip, token, agent_type, protocol,
                ping_failures, ping_last_checked, last_seen
            )
            VALUES (?, ?, ?, ?, 'ping', 'icmp', ?, ?, ?)
            """,
            ("fritzbox", "FRITZ!Box", "192.168.178.1", "token", 3, "2026-04-12 10:01:00", "2026-04-12 10:00:00"),
        )
        db_conn.commit()

        dash = client.get("/api/dashboard")

        assert dash.status_code == 200
        row = next(a for a in dash.json()["agents"] if a["id"] == "fritzbox")
        assert row["effective_online"] is False
        assert row["connectivity_state"] == "offline"

    def test_alerts_include_ping_target_after_third_failed_check_even_if_last_seen_is_recent(self, client, db_conn):
        db_conn.execute(
            """
            INSERT INTO agents (
                id, hostname, ip, token, agent_type, protocol,
                ping_failures, ping_last_checked, last_seen
            )
            VALUES (?, ?, ?, ?, 'ping', 'icmp', ?, datetime('now','localtime'), datetime('now','localtime'))
            """,
            ("fritzbox", "FRITZ!Box", "192.168.178.1", "token", 3),
        )
        db_conn.commit()

        resp = client.get("/api/alerts")

        assert resp.status_code == 200
        assert any(row["hostname"] == "FRITZ!Box" for row in resp.json())

    def test_status_badge_counts_busy_ping_target_as_online(self, client, db_conn):
        db_conn.execute(
            """
            INSERT INTO agents (
                id, hostname, ip, token, agent_type, protocol,
                ping_failures, ping_last_checked, last_seen
            )
            VALUES (?, ?, ?, ?, 'ping', 'icmp', ?, datetime('now','localtime'), datetime('now','localtime','-10 minutes'))
            """,
            ("fritzbox", "FRITZ!Box", "192.168.178.1", "token", 2),
        )
        db_conn.commit()

        resp = client.get("/api/status/badge")

        assert resp.status_code == 200
        assert "1/1 online" in resp.text

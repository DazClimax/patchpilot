"""
test_schedules.py — tests for the schedule endpoints.
"""

import pytest


VALID_CRON = "0 3 * * *"


def _create_schedule(client, name="Nightly upgrade", cron=VALID_CRON, action="upgrade", target="all"):
    resp = client.post(
        "/api/schedules",
        json={"name": name, "cron": cron, "action": action, "target": target},
    )
    return resp


class TestListSchedules:
    def test_list_schedules_empty(self, client):
        resp = client.get("/api/schedules")
        assert resp.status_code == 200
        data = resp.json()
        assert "schedules" in data
        assert "agents" in data
        assert data["schedules"] == []

    def test_list_schedules_after_creation(self, client):
        _create_schedule(client)
        resp = client.get("/api/schedules")
        assert resp.status_code == 200
        assert len(resp.json()["schedules"]) == 1

    def test_list_schedules_returns_all_fields(self, client):
        _create_schedule(client, name="Test Sched", cron="0 2 * * 1", action="check", target="all")
        schedule = client.get("/api/schedules").json()["schedules"][0]
        assert schedule["name"] == "Test Sched"
        assert schedule["cron"] == "0 2 * * 1"
        assert schedule["action"] == "check"
        assert schedule["target"] == "all"
        assert schedule["enabled"] == 1


class TestCreateSchedule:
    def test_create_schedule_returns_created(self, client):
        resp = _create_schedule(client)
        assert resp.status_code == 200
        assert resp.json()["status"] == "created"

    def test_create_multiple_schedules(self, client):
        _create_schedule(client, name="Schedule A")
        _create_schedule(client, name="Schedule B", cron="0 4 * * *")
        schedules = client.get("/api/schedules").json()["schedules"]
        assert len(schedules) == 2
        names = [s["name"] for s in schedules]
        assert "Schedule A" in names
        assert "Schedule B" in names

    def test_created_schedule_is_enabled_by_default(self, client):
        _create_schedule(client)
        schedule = client.get("/api/schedules").json()["schedules"][0]
        assert schedule["enabled"] == 1

    def test_list_includes_agents(self, client, registered_agent):
        agent_id, _ = registered_agent
        data = client.get("/api/schedules").json()
        agent_ids = [a["id"] for a in data["agents"]]
        assert agent_id in agent_ids


class TestToggleSchedule:
    def test_disable_schedule(self, client):
        _create_schedule(client)
        sid = client.get("/api/schedules").json()["schedules"][0]["id"]

        resp = client.patch(f"/api/schedules/{sid}", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

        schedule = client.get("/api/schedules").json()["schedules"][0]
        assert schedule["enabled"] == 0

    def test_enable_schedule(self, client):
        _create_schedule(client)
        sid = client.get("/api/schedules").json()["schedules"][0]["id"]

        # Disable first
        client.patch(f"/api/schedules/{sid}", json={"enabled": False})
        # Re-enable
        resp = client.patch(f"/api/schedules/{sid}", json={"enabled": True})
        assert resp.status_code == 200

        schedule = client.get("/api/schedules").json()["schedules"][0]
        assert schedule["enabled"] == 1

    def test_toggle_nonexistent_schedule_returns_200(self, client):
        # Patch on a nonexistent ID performs an UPDATE that matches zero rows — not an error
        resp = client.patch("/api/schedules/99999", json={"enabled": False})
        assert resp.status_code == 200


class TestDeleteSchedule:
    def test_delete_schedule(self, client):
        _create_schedule(client)
        sid = client.get("/api/schedules").json()["schedules"][0]["id"]

        resp = client.delete(f"/api/schedules/{sid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_deleted_schedule_not_in_list(self, client):
        _create_schedule(client)
        sid = client.get("/api/schedules").json()["schedules"][0]["id"]
        client.delete(f"/api/schedules/{sid}")

        schedules = client.get("/api/schedules").json()["schedules"]
        assert all(s["id"] != sid for s in schedules)

    def test_delete_nonexistent_schedule_returns_200(self, client):
        resp = client.delete("/api/schedules/99999")
        assert resp.status_code == 200

"""
test_schedules.py — tests for the schedule endpoints.
"""

import app as app_module


VALID_CRON = "0 3 * * *"


def _create_schedule(client, name="Nightly patch", cron=VALID_CRON, action="patch", target="all"):
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
        _create_schedule(client, name="Test Sched", cron="0 2 * * 1", action="refresh_updates", target="all")
        schedule = client.get("/api/schedules").json()["schedules"][0]
        assert schedule["name"] == "Test Sched"
        assert schedule["cron"] == "0 2 * * 1"
        assert schedule["action"] == "refresh_updates"
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
        scheduler_mock = client.app.state.scheduler_mock

        resp = client.patch(f"/api/schedules/{sid}", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"
        scheduler_mock.remove_job.assert_called_with(str(sid))

        schedule = client.get("/api/schedules").json()["schedules"][0]
        assert schedule["enabled"] == 0

    def test_enable_schedule(self, client):
        _create_schedule(client)
        sid = client.get("/api/schedules").json()["schedules"][0]["id"]
        scheduler_mock = client.app.state.scheduler_mock

        # Disable first
        client.patch(f"/api/schedules/{sid}", json={"enabled": False})
        scheduler_mock.reset_mock()
        # Re-enable
        resp = client.patch(f"/api/schedules/{sid}", json={"enabled": True})
        assert resp.status_code == 200
        scheduler_mock.add_job.assert_called()

        schedule = client.get("/api/schedules").json()["schedules"][0]
        assert schedule["enabled"] == 1

    def test_toggle_nonexistent_schedule_returns_200(self, client):
        # The API now returns 404 for unknown schedules.
        resp = client.patch("/api/schedules/99999", json={"enabled": False})
        assert resp.status_code == 404


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


class TestScheduleUpdate:
    def test_update_disabled_schedule_does_not_re_register_job(self, client):
        _create_schedule(client)
        sid = client.get("/api/schedules").json()["schedules"][0]["id"]
        scheduler_mock = client.app.state.scheduler_mock

        client.patch(f"/api/schedules/{sid}", json={"enabled": False})
        scheduler_mock.reset_mock()

        resp = client.put(
            f"/api/schedules/{sid}",
            json={"name": "Updated", "cron": "0 5 * * *", "action": "patch", "target": "all"},
        )

        assert resp.status_code == 200
        scheduler_mock.add_job.assert_not_called()
        scheduler_mock.remove_job.assert_called_with(str(sid))


class TestPortRouting:
    def test_helper_marks_only_agent_runtime_routes_as_agent_only(self):
        assert app_module._is_agent_only_request("/api/agents/register", "POST") is True
        assert app_module._is_agent_only_request("/api/agents/demo/heartbeat", "POST") is True
        assert app_module._is_agent_only_request("/api/agents/demo/ha-update-callback", "POST") is True
        assert app_module._is_agent_only_request("/api/agents/demo/jobs", "GET") is True
        assert app_module._is_agent_only_request("/api/agents/demo/jobs/1/result", "POST") is True
        assert app_module._is_agent_only_request("/api/agents/demo", "GET") is False
        assert app_module._is_agent_only_request("/api/agents/demo/jobs", "POST") is False

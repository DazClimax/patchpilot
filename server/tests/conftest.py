"""
conftest.py — shared pytest fixtures for PatchPilot server tests.

Strategy:
- Provide a fresh in-memory SQLite database per test.
- Patch the symbols imported into app.py directly, because startup handlers call
  app-local references, not the originals from db.py.
- Disable scheduler/system background work so tests stay deterministic.
"""

import contextlib
import secrets
import sqlite3
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# In-memory DB helpers
# ---------------------------------------------------------------------------

def _make_in_memory_conn():
    """Create a fresh in-memory SQLite connection with the PatchPilot schema."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id          TEXT PRIMARY KEY,
            hostname    TEXT NOT NULL,
            ip          TEXT,
            os_pretty   TEXT,
            kernel      TEXT,
            arch        TEXT,
            package_manager TEXT,
            agent_version TEXT DEFAULT '',
            agent_type  TEXT DEFAULT 'linux',
            capabilities TEXT DEFAULT '',
            reboot_required INTEGER DEFAULT 0,
            pending_count   INTEGER DEFAULT 0,
            last_seen   TEXT,
            registered  TEXT DEFAULT (datetime('now','localtime')),
            token       TEXT NOT NULL,
            tags        TEXT DEFAULT '',
            uptime_seconds INTEGER,
            protocol    TEXT DEFAULT 'http',
            config_review_required INTEGER DEFAULT 0,
            config_review_note TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS packages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id    TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            current_ver TEXT,
            new_ver     TEXT,
            UNIQUE(agent_id, name)
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id    TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            type        TEXT NOT NULL,
            status      TEXT DEFAULT 'pending',
            created     TEXT DEFAULT (datetime('now','localtime')),
            started     TEXT,
            finished    TEXT,
            output      TEXT,
            params      TEXT
        );

        CREATE TABLE IF NOT EXISTS schedules (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            cron        TEXT NOT NULL,
            action      TEXT NOT NULL,
            target      TEXT NOT NULL,
            enabled     INTEGER DEFAULT 1,
            last_run    TEXT,
            next_run    TEXT
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('admin','user','readonly')),
            created       TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS rename_aliases (
            old_id   TEXT PRIMARY KEY,
            new_id   TEXT NOT NULL,
            created  TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_packages_agent_id
            ON packages(agent_id);

        CREATE INDEX IF NOT EXISTS idx_jobs_agent_id_status
            ON jobs(agent_id, status);

        CREATE INDEX IF NOT EXISTS idx_agents_last_seen
            ON agents(last_seen);
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_ADMIN_KEY = "test-admin-key-fixed"
TEST_REGISTER_KEY = "test-register-key"


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch):
    """Fix the admin key so tests can rely on a known value."""
    monkeypatch.setenv("PATCHPILOT_ADMIN_KEY", TEST_ADMIN_KEY)


@pytest.fixture(autouse=True)
def _reset_app_state():
    """Reset global in-memory app state between tests."""
    import app as app_module

    app_module._RATE_LIMIT.clear()
    app_module._AGENT_RATE_LIMIT.clear()
    app_module._sessions.clear()
    app_module._CACHE.clear()
    app_module._last_heartbeat.clear()
    yield
    app_module._RATE_LIMIT.clear()
    app_module._AGENT_RATE_LIMIT.clear()
    app_module._sessions.clear()
    app_module._CACHE.clear()
    app_module._last_heartbeat.clear()


@pytest.fixture()
def db_conn():
    """Provide an isolated in-memory SQLite connection for one test."""
    conn = _make_in_memory_conn()
    yield conn
    conn.close()


@pytest.fixture()
def client(db_conn, monkeypatch):
    """
    FastAPI TestClient backed by an in-memory SQLite database.

    Each call creates a fresh connection from the shared db_conn fixture so
    all operations within a test share the same in-memory database.
    """
    @contextlib.contextmanager
    def _fake_db():
        yield db_conn
        db_conn.commit()

    import app as app_module
    import scheduler as scheduler_module

    monkeypatch.setattr(app_module, "_ADMIN_KEY_ENV", TEST_ADMIN_KEY)
    monkeypatch.setattr(app_module, "get_db_ctx", _fake_db)
    monkeypatch.setattr(app_module, "init_db", lambda: None)
    monkeypatch.setattr(app_module, "_verify_register_key", lambda submitted: None)

    mock_scheduler = MagicMock()
    monkeypatch.setattr(app_module, "scheduler", mock_scheduler)
    monkeypatch.setattr(scheduler_module, "scheduler", mock_scheduler)
    monkeypatch.setattr(app_module, "_load_schedules", lambda: None)
    monkeypatch.setattr(app_module, "register_system_jobs", lambda: None)
    app_module.app.state.scheduler_mock = mock_scheduler

    with TestClient(app_module.app, raise_server_exceptions=True) as c:
        c.headers.update({
            "x-admin-key": TEST_ADMIN_KEY,
            "x-register-key": TEST_REGISTER_KEY,
        })
        yield c


@pytest.fixture()
def admin_headers():
    """HTTP headers for admin-protected endpoints."""
    return {"x-admin-key": TEST_ADMIN_KEY}


@pytest.fixture()
def registered_agent(client):
    """Register a test agent and return (agent_id, token)."""
    agent_id = "test-agent-" + secrets.token_hex(4)
    token = "test-token-" + secrets.token_hex(8)
    resp = client.post(
        "/api/agents/register",
        json={
            "id": agent_id,
            "token": token,
            "hostname": "testhost",
            "ip": "10.0.0.1",
            "os_pretty": "Debian 12",
            "kernel": "6.1.0",
            "arch": "x86_64",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    return data["agent_id"], data["token"]


@pytest.fixture()
def agent_headers(registered_agent):
    """Convenience: return the x-token header for the registered agent."""
    _, token = registered_agent
    return {"x-token": token}

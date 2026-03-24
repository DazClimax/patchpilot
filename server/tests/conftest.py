"""
conftest.py — shared pytest fixtures for PatchPilot server tests.

Strategy:
- Patch db.DB_PATH to an in-memory SQLite database before any import of app.py
  so every test runs against a fresh, isolated database.
- Patch scheduler.scheduler to a dummy object so APScheduler never starts.
- Provide a TestClient, a pre-registered agent fixture, and the admin key.
"""

import sqlite3
import contextlib
import secrets
import os
from unittest.mock import MagicMock, patch

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
            reboot_required INTEGER DEFAULT 0,
            pending_count   INTEGER DEFAULT 0,
            last_seen   TEXT,
            registered  TEXT DEFAULT (datetime('now','localtime')),
            token       TEXT NOT NULL
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
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_ADMIN_KEY = "test-admin-key-fixed"


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch):
    """Fix the admin key so tests can rely on a known value."""
    monkeypatch.setenv("PATCHPILOT_ADMIN_KEY", TEST_ADMIN_KEY)


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
    # Re-import fresh module state is tricky; instead we patch db.db and
    # db.init_db at the module level so app.py uses our in-memory connection.

    @contextlib.contextmanager
    def _fake_db():
        yield db_conn
        db_conn.commit()

    # Patch the admin key at module level (app._ADMIN_KEY_ENV)
    import app as app_module
    import db as db_module

    monkeypatch.setattr(app_module, "_ADMIN_KEY_ENV", TEST_ADMIN_KEY)
    monkeypatch.setattr(db_module, "db", _fake_db)

    # Prevent APScheduler from actually starting
    mock_scheduler = MagicMock()
    monkeypatch.setattr(app_module, "scheduler", mock_scheduler)

    # Skip _load_schedules side-effects on startup
    monkeypatch.setattr(app_module, "_load_schedules", lambda: None)

    # init_db should be a no-op (schema already created in db_conn)
    monkeypatch.setattr(db_module, "init_db", lambda: None)

    with TestClient(app_module.app, raise_server_exceptions=True) as c:
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

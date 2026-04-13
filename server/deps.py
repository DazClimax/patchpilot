import hashlib
import hmac
import logging
import os
import secrets
import sys
import time

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

log = logging.getLogger(__name__)

# Set PATCHPILOT_ADMIN_KEY as an environment variable on the server.
_ADMIN_KEY_ENV = os.environ.get("PATCHPILOT_ADMIN_KEY", "")
if not _ADMIN_KEY_ENV:
    _ADMIN_KEY_ENV = secrets.token_hex(32)
    print(
        f"[patchpilot] WARNING: PATCHPILOT_ADMIN_KEY not set. "
        f"Using ephemeral key for this session: {_ADMIN_KEY_ENV}",
        file=sys.stderr,
    )

_admin_key_header = APIKeyHeader(name="x-admin-key", auto_error=False)


def _current_admin_key() -> str:
    return os.environ.get("PATCHPILOT_ADMIN_KEY", _ADMIN_KEY_ENV)


def _get_db_ctx():
    from app import get_db_ctx as app_get_db_ctx

    return app_get_db_ctx()


def require_admin(x_admin_key: str = Depends(_admin_key_header)):
    """Dependency: validates the admin key for web-UI endpoints."""
    if not x_admin_key or not hmac.compare_digest(
        x_admin_key.encode(), _current_admin_key().encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing admin key")


_sessions: dict[str, dict] = {}
_SESSION_MAX_AGE = 86400  # 24h
_session_last_cleanup = 0.0


def _load_sessions_from_db():
    """Load persisted sessions from DB into memory on startup."""
    now = time.time()
    try:
        with _get_db_ctx() as conn:
            rows = conn.execute("SELECT token, user_id, username, role, created_ts FROM sessions").fetchall()
        for row in rows:
            if now - row["created_ts"] < _SESSION_MAX_AGE:
                _sessions[row["token"]] = {
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "role": row["role"],
                    "created_ts": row["created_ts"],
                }
    except Exception as exc:
        log.warning("_load_sessions_from_db: %s", exc)


def _persist_session(token: str, session: dict):
    """Write a session to the DB for persistence across restarts."""
    try:
        with _get_db_ctx() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (token, user_id, username, role, created_ts) VALUES (?,?,?,?,?)",
                (token, session["user_id"], session["username"], session["role"], session["created_ts"]),
            )
    except Exception as exc:
        log.warning("_persist_session: %s", exc)


def _delete_session_from_db(token: str):
    """Remove a single session from the DB."""
    try:
        with _get_db_ctx() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    except Exception as exc:
        log.warning("_delete_session_from_db: %s", exc)


def _delete_sessions_for_user(user_id: int):
    """Remove all DB sessions for a user (on password change / deletion)."""
    try:
        with _get_db_ctx() as conn:
            conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    except Exception as exc:
        log.warning("_delete_sessions_for_user: %s", exc)


def _cleanup_sessions():
    """Evict expired sessions periodically (every 5 min)."""
    global _session_last_cleanup
    now = time.time()
    if now - _session_last_cleanup < 300:
        return
    _session_last_cleanup = now
    expired = [t for t, s in _sessions.items() if now - s["created_ts"] >= _SESSION_MAX_AGE]
    for token in expired:
        _sessions.pop(token, None)
    try:
        with _get_db_ctx() as conn:
            conn.execute("DELETE FROM sessions WHERE created_ts < ?", (now - _SESSION_MAX_AGE,))
    except Exception as exc:
        log.warning("_cleanup_sessions DB error: %s", exc)


def _get_session(request: Request) -> dict | None:
    """Extract session from Authorization: Bearer <token> header."""
    _cleanup_sessions()
    auth_val = request.headers.get("authorization", "")
    if auth_val.startswith("Bearer "):
        token = auth_val[7:]
        session = _sessions.get(token)
        if session and (time.time() - session["created_ts"]) < _SESSION_MAX_AGE:
            return session
        _sessions.pop(token, None)
    return None


def require_role(*roles: str):
    """Dependency factory: require user to have one of the given roles.
    Also accepts legacy x-admin-key header (treated as admin)."""

    def dependency(request: Request, x_admin_key: str = Depends(_admin_key_header)):
        if x_admin_key and hmac.compare_digest(
            x_admin_key.encode(), _current_admin_key().encode()
        ):
            request.state.user = {"username": "admin", "role": "admin", "user_id": 0}
            return
        session = _get_session(request)
        if session and session["role"] in roles:
            request.state.user = session
            return
        if session:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        raise HTTPException(status_code=401, detail="Authentication required")

    return dependency


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_agent(agent_id: str, x_token: str):
    """Verify agent token against the stored SHA-256 hash."""
    with _get_db_ctx() as conn:
        row = conn.execute(
            "SELECT token FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()

    dummy = _hash_token(secrets.token_hex(32))
    stored = row["token"] if row else dummy
    submitted_hash = _hash_token(x_token)
    hash_ok = hmac.compare_digest(submitted_hash, stored)

    if not row or not hash_ok:
        raise HTTPException(status_code=401, detail="Invalid token")

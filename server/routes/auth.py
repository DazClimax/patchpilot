import logging
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from db import hash_password, verify_password
from deps import (
    _delete_session_from_db,
    _delete_sessions_for_user,
    _get_db_ctx,
    _persist_session,
    _sessions,
    require_role,
)

router = APIRouter()
log = logging.getLogger(__name__)


@router.post("/api/auth/login")
async def auth_login(request: Request):
    from app import _check_rate_limit, _get_client_ip, _remove_bootstrap_password_file

    _check_rate_limit(request)
    data = await request.json()
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not username or not password:
        raise HTTPException(status_code=422, detail="Username and password required")
    if len(password) > 1024:
        raise HTTPException(status_code=422, detail="Password too long")
    with _get_db_ctx() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username=?",
            (username,),
        ).fetchone()
    dummy_hash = hash_password("dummy")
    stored_hash = row["password_hash"] if row else dummy_hash
    valid = verify_password(password, stored_hash)
    if not row or not valid:
        log.warning("AUTH FAIL: username=%r ip=%s", username, _get_client_ip(request))
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = secrets.token_hex(32)
    session = {
        "user_id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "created_ts": time.time(),
    }
    _sessions[token] = session
    _persist_session(token, session)
    _remove_bootstrap_password_file()
    return {"token": token, "role": row["role"], "username": row["username"]}


@router.post("/api/auth/logout")
async def auth_logout(request: Request):
    auth_val = request.headers.get("authorization", "")
    if auth_val.startswith("Bearer "):
        token = auth_val[7:]
        _sessions.pop(token, None)
        _delete_session_from_db(token)
    return {"status": "ok"}


@router.get("/api/auth/me", dependencies=[Depends(require_role("admin", "user", "readonly"))])
def auth_me(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401)
    return {"username": user["username"], "role": user["role"]}


@router.get("/api/users", dependencies=[Depends(require_role("admin"))])
def list_users():
    with _get_db_ctx() as conn:
        rows = conn.execute("SELECT id, username, role, created FROM users ORDER BY id").fetchall()
    return {"users": [dict(r) for r in rows]}


@router.post("/api/users", dependencies=[Depends(require_role("admin"))])
async def create_user(request: Request):
    data = await request.json()
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    role = str(data.get("role", "user"))
    if not username or not password:
        raise HTTPException(status_code=422, detail="Username and password required")
    if role not in ("admin", "user", "readonly"):
        raise HTTPException(status_code=422, detail="Invalid role")
    if len(username) > 64 or len(password) < 4 or len(password) > 1024:
        raise HTTPException(status_code=422, detail="Username max 64 chars, password 4-1024 chars")
    with _get_db_ctx() as conn:
        existing = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Username already exists")
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, hash_password(password), role),
        )
    return {"status": "created"}


@router.patch("/api/users/{user_id}", dependencies=[Depends(require_role("admin"))])
async def update_user(user_id: int, request: Request):
    data = await request.json()
    current_user = getattr(request.state, "user", {})
    with _get_db_ctx() as conn:
        row = conn.execute("SELECT id, role FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        if "role" in data:
            role = str(data["role"])
            if role not in ("admin", "user", "readonly"):
                raise HTTPException(status_code=422, detail="Invalid role")
            if current_user.get("user_id") == user_id and row["role"] == "admin" and role != "admin":
                raise HTTPException(status_code=400, detail="You cannot remove your own admin role")
            if row["role"] == "admin" and role != "admin":
                admin_count = conn.execute("SELECT COUNT(*) as c FROM users WHERE role='admin'").fetchone()["c"]
                if admin_count <= 1:
                    raise HTTPException(status_code=400, detail="Cannot demote the last admin user")
            conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        if "password" in data:
            password = str(data["password"])
            if len(password) < 4:
                raise HTTPException(status_code=422, detail="Password min 4 chars")
            conn.execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                (hash_password(password), user_id),
            )
    to_remove = [t for t, s in _sessions.items() if s.get("user_id") == user_id]
    for token in to_remove:
        _sessions.pop(token, None)
    _delete_sessions_for_user(user_id)
    return {"status": "updated"}


@router.delete("/api/users/{user_id}", dependencies=[Depends(require_role("admin"))])
def delete_user(user_id: int, request: Request):
    user = getattr(request.state, "user", {})
    if user.get("user_id") == user_id and user_id != 0:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    with _get_db_ctx() as conn:
        target = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        if target["role"] == "admin":
            admin_count = conn.execute("SELECT COUNT(*) as c FROM users WHERE role='admin'").fetchone()["c"]
            if admin_count <= 1:
                raise HTTPException(status_code=400, detail="Cannot delete the last admin user")
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    to_remove = [t for t, s in _sessions.items() if s.get("user_id") == user_id]
    for token in to_remove:
        _sessions.pop(token, None)
    _delete_sessions_for_user(user_id)
    return {"status": "deleted"}

# PatchPilot — Security Audit Report

**Last updated:** 2026-03-22
**Scope:** All backend, frontend, agent, and deployment files
**Context:** Private home network (Raspberry Pi), no external exposure planned
**Auditors:** Automated Security Audit Agent (2 rounds)

---

## Summary

| Severity | Found | Fixed | Accepted Risk |
|----------|-------|-------|---------------|
| CRITICAL | 3     | 3     | — |
| HIGH     | 5     | 5     | — |
| MEDIUM   | 13    | 11    | 2 |
| LOW      | 11    | 9     | 2 |

---

## CRITICAL Issues

### C-1: Agent Impersonation via Re-Registration — FIXED (v0.3.0)

**File:** `server/app.py`
**Description:** `POST /api/agents/register` returned the existing token for a known `agent_id` without authentication.

**Fix:** Re-registration requires valid current token. New registration requires a time-limited registration key (5 min, generated on-demand). Rate limited at 20 req/60s per IP.

---

### C-2: Agent ID Shell Metacharacter Injection — FIXED (v0.3.1)

**File:** `frontend/src/pages/Deploy.tsx`, `agent/install.sh`
**Description:** Agent ID accepted arbitrary characters including shell metacharacters.

**Fix:** Validated against `/^[a-zA-Z0-9._-]{1,64}$/`. install.sh uses bash arrays.

---

### C-3: Job Type Not Validated Against Allowlist — FIXED (v0.3.0)

**File:** `server/app.py`, `server/scheduler.py`
**Description:** Arbitrary job types were accepted.

**Fix:** Validated against `ALLOWED_JOB_TYPES = {"patch", "reboot", "autoremove", "update_agent"}`.

---

## HIGH Issues

### H-1: Admin-Only Endpoints Missing Authentication — FIXED (v0.3.0)

**Fix:** All admin endpoints use `Depends(require_admin)`. Timing-safe comparison via `hmac.compare_digest`.

---

### H-2: Token Injection at Agent Registration — FIXED (v0.3.0)

**Fix:** Token always generated server-side via `secrets.token_hex(32)`.

---

### H-3: CORS Wildcard — FIXED (v0.3.0)

**Fix:** Configurable origins via `PATCHPILOT_ALLOWED_ORIGINS`.

---

### H-4: SQL String Concatenation in Scheduler — FIXED (v0.3.0)

**Fix:** Parameterized queries throughout.

---

### H-5: SSRF via SMTP Host / Unvalidated Telegram Token — FIXED (v0.3.0)

**Fix:** `_validate_smtp_host()` checks resolved IPs against private ranges. Telegram token validated and verified via `getMe` API.

---

## MEDIUM Issues (Round 1)

### M-1: install.sh Unquoted Variable Expansion — FIXED (v0.3.1)

**Fix:** Bash arrays: `MISSING_PKGS=()`, `"${MISSING_PKGS[@]}"`.

---

### M-2: No Integrity Verification for agent.py Download — FIXED (v0.3.0)

**Fix:** Server exposes `GET /agent/agent.py.sha256`. Install script and agent self-update verify SHA-256.

---

### M-3: Timing Attack in verify_agent — FIXED (v0.3.0)

**Fix:** `hmac.compare_digest` with constant-time dummy comparison for unknown IDs.

---

### M-4: Unbounded Job Output — FIXED (v0.3.0)

**Fix:** Output capped to 65536 characters.

---

### M-5: No Rate Limiting on Registration — FIXED (v0.3.0)

**Fix:** 20 req/60s per IP. Rate limiter hard-capped at 1000 entries.

---

### M-6: Package Name Validation — FIXED (v0.3.0)

**Fix:** Validated against `^[a-zA-Z0-9][a-zA-Z0-9.+\-]{0,127}$`. No `shell=True`.

---

### M-7: Schedule Input Not Validated — FIXED (v0.3.0)

**Fix:** Action validated against allowlist, cron must be 5 fields, name ≤ 128 chars.

---

## MEDIUM Issues (Round 2)

### M-8: Package Name/Version Not Length-Limited in Heartbeat — FIXED (v0.3.14)

**File:** `server/app.py`
**Description:** Heartbeat accepted arbitrarily long package name/version strings.

**Fix:** Packages array capped at 2000 entries. Tag validation added with 512-char limit.

---

### M-9: Agent Self-Update Skips TLS Verification — FIXED (v0.3.14)

**File:** `agent/agent.py`
**Description:** `_update_self` used `urlreq.urlopen` without SSL context.

**Fix:** Downloads now use the same `_SSL_CTX` as regular requests.

---

### M-10: TOCTOU in Register Endpoint — FIXED (v0.3.14)

**File:** `server/app.py`
**Description:** Existence check and insert were in separate DB transactions.

**Fix:** Combined into single `with get_db_ctx()` block.

---

### M-11: server_url Parameter Override in update_agent — FIXED (v0.3.14)

**File:** `agent/agent.py`
**Description:** `_update_self` accepted `server_url` param allowing arbitrary download source.

**Fix:** Removed `server_url` override. Agent only downloads from its configured server.

---

### M-12: Rate Limit Dicts Not Thread-Safe — ACCEPTED RISK

**Description:** Single uvicorn worker makes this safe. Documented as single-worker requirement.

---

### M-13: update_agent Design Allows Code Push — ACCEPTED RISK

**Description:** Inherent to self-update architecture. Mitigated by SHA-256 verification and admin-key-only access.

---

## LOW Issues

### L-1: Agent Runs as root — ACCEPTED RISK

`apt-get` requires root. Accepted for home network use.

---

### L-2: Stale In-Memory State After Agent Deletion — FIXED (v0.3.0)

**Fix:** Cleanup of `_offline_notified`, `_last_heartbeat`, alias maps on deletion.

---

### L-3: Telegram Message Markdown Injection — FIXED (v0.3.1)

**Fix:** `_tg_escape()` helper escapes special characters.

---

### L-4: Hardcoded http:// in Deploy Page — FIXED (v0.3.1)

**Fix:** Uses configurable server URL set by admin.

---

### L-5: Full HTTP Error Body Logged — FIXED (v0.3.1)

**Fix:** Body capped to 200 bytes.

---

### L-6: Status Badge Unauthenticated — ACCEPTED RISK

Information leak is minimal (agent count only). Kept public for badge embedding.

---

### L-7: Unknown Command Echo Injection — FIXED (v0.3.6)

**File:** `server/telegram_bot.py`
**Fix:** `_esc(cmd)` applied before echoing unknown Telegram commands.

---

### L-8: Python 3.9 Compatibility for is_relative_to — FIXED (v0.3.6)

**Fix:** try/except fallback.

---

### L-9: DB File Permissions — FIXED (v0.3.6)

**Fix:** `DB_PATH.chmod(0o600)` at end of `init_db()`.

---

### L-10: Atomic .env Writes — FIXED (v0.3.6)

**Fix:** Write to `.env.tmp` then `os.replace()`.

---

### L-11: Ephemeral Admin Key Logged to Journal — ACCEPTED RISK

For home network use, journal access is restricted to the admin.

---

## Hardening Applied

- **Systemd:** `User=patchpilot`, `Group=patchpilot`, `NoNewPrivileges=yes`, `PrivateTmp=yes`
- **Sudoers:** Only `/bin/systemctl restart patchpilot` allowed
- **DB permissions:** 0600
- **Non-interactive apt:** `DEBIAN_FRONTEND=noninteractive`, `--force-confdef`, `--force-confold`
- **Forwarder limits:** 50 concurrent connections, 60s idle timeout
- **Uptime validation:** Integer in [0, 2147483647]

"""
PatchPilot Telegram Command Bot

Polls getUpdates every 5 seconds and handles commands.
All commands are restricted to the configured telegram_chat_id.
"""

import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

_HELP = (
    "*PatchPilot Bot* — available commands:\n"
    "\n"
    "/status — VM overview (online/offline count)\n"
    "/vms — List all VMs with details\n"
    "/jobs [n] — Last N jobs (default 5, max 20)\n"
    "/patch <id|all> — Queue patch job\n"
    "/reboot <id> — Queue reboot job\n"
    "/updates <id> — Show pending packages for a VM\n"
    "/help — Show this message"
)

_STATUS_ICON = {"done": "✅", "failed": "❌", "running": "⏳", "pending": "🕐"}


import re
import time as _time

_AGENT_ID_RE = re.compile(r'^[a-zA-Z0-9._-]{1,64}$')

def _esc(text: str) -> str:
    """MED-4: Escape Telegram legacy Markdown special characters."""
    for ch in ('*', '_', '`', '['):
        text = text.replace(ch, f'\\{ch}')
    return text

_SETTINGS_RELOAD_INTERVAL = 60  # seconds


class TelegramCommandBot:
    """Long-poll Telegram bot that executes PatchPilot commands."""

    def __init__(self):
        self._offset: int = 0
        self._token: str = ""
        self._chat_id: str = ""
        self._settings_loaded_at: float = 0.0

    # ------------------------------------------------------------------
    # Settings — reload at most once per minute
    # ------------------------------------------------------------------

    def _load_settings(self):
        now = _time.monotonic()
        if now - self._settings_loaded_at < _SETTINGS_RELOAD_INTERVAL:
            return
        try:
            from db import db as get_db_ctx
            with get_db_ctx() as conn:
                rows = conn.execute("SELECT key, value FROM settings").fetchall()
            cfg = {r["key"]: r["value"] for r in rows}
            self._token = cfg.get("telegram_token", "").strip()
            self._chat_id = cfg.get("telegram_chat_id", "").strip()
            self._settings_loaded_at = now
        except Exception as exc:
            log.warning("TelegramBot: failed to load settings: %s", exc)

    def reload_settings(self):
        """Force a settings reload on the next poll (call after settings save)."""
        self._settings_loaded_at = 0.0

    # ------------------------------------------------------------------
    # Low-level API
    # ------------------------------------------------------------------

    def _api(self, method: str, params: dict | None = None) -> dict | None:
        if not self._token:
            return None
        url = f"https://api.telegram.org/bot{self._token}/{method}"
        body = json.dumps(params or {}).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            log.warning("TelegramBot %s HTTP %s: %s", method, exc.code, exc.read(200))
        except Exception as exc:
            log.warning("TelegramBot %s error: %s", method, exc)
        return None

    def _send(self, chat_id: str, text: str):
        self._api("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        })

    def notify(self, text: str):
        """Send a message to the configured chat (public interface for app.py)."""
        self._load_settings()
        if self._token and self._chat_id:
            self._send(self._chat_id, text)

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def poll_once(self):
        """Called by the scheduler every 5 s. Fetches and processes updates."""
        self._load_settings()
        if not self._token or not self._chat_id:
            return

        result = self._api("getUpdates", {
            "offset": self._offset,
            "timeout": 0,
            "limit": 20,
            "allowed_updates": ["message"],
        })
        if not result or not result.get("ok"):
            return

        for update in result.get("result", []):
            self._offset = update["update_id"] + 1
            msg = update.get("message", {})
            if not msg:
                continue
            chat_id = str(msg.get("chat", {}).get("id", "")).strip()
            text = (msg.get("text") or "").strip()
            if not text or not text.startswith("/"):
                continue
            if not self._chat_id or chat_id != self._chat_id:
                # Silently ignore — don't tell strangers the bot exists
                continue
            self._dispatch(chat_id, text)

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, chat_id: str, text: str):
        parts = text.split()
        # Strip optional @BotName suffix from command
        cmd = parts[0].lower().split("@")[0]
        args = parts[1:]

        handlers = {
            "/help":    self._cmd_help,
            "/status":  self._cmd_status,
            "/vms":     self._cmd_vms,
            "/jobs":    self._cmd_jobs,
            "/patch":   self._cmd_patch,
            "/reboot":  self._cmd_reboot,
            "/updates": self._cmd_updates,
        }
        handler = handlers.get(cmd)
        if handler:
            try:
                handler(chat_id, args)
            except Exception as exc:
                # Log details server-side; send only a generic message to chat
                log.warning("TelegramBot command %s error: %s", cmd, exc)
                self._send(chat_id, f"⚠ Command failed. Check server logs.")
        else:
            self._send(chat_id, f"Unknown command: `{_esc(cmd)}`\n\n" + _HELP)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _cmd_help(self, chat_id: str, args: list):
        self._send(chat_id, _HELP)

    def _cmd_status(self, chat_id: str, args: list):
        from db import db as get_db_ctx
        with get_db_ctx() as conn:
            agents = conn.execute(
                """SELECT hostname,
                   CAST((julianday('now') - julianday(last_seen)) * 86400 AS INTEGER) as secs_ago,
                   pending_count, reboot_required
                   FROM agents ORDER BY hostname"""
            ).fetchall()

        total = len(agents)
        online = sum(1 for a in agents if (a["secs_ago"] or 9999) < 120)
        updates = sum(a["pending_count"] or 0 for a in agents)
        reboots = sum(1 for a in agents if a["reboot_required"])

        lines = [
            "*PatchPilot Status*",
            "",
            f"VMs: *{online}/{total}* online",
            f"Pending updates: *{updates}* packages",
            f"Reboot required: *{reboots}* VM(s)",
        ]
        if total > 0:
            lines.append("")
            for a in agents:
                icon = "🟢" if (a["secs_ago"] or 9999) < 120 else "🔴"
                reboot = " ⚠" if a["reboot_required"] else ""
                lines.append(f"{icon} `{_esc(a['hostname'])}`{reboot}")

        self._send(chat_id, "\n".join(lines))

    def _cmd_vms(self, chat_id: str, args: list):
        from db import db as get_db_ctx
        with get_db_ctx() as conn:
            agents = conn.execute(
                """SELECT id, hostname, ip, os_pretty, pending_count, reboot_required,
                   CAST((julianday('now') - julianday(last_seen)) * 86400 AS INTEGER) as secs_ago
                   FROM agents ORDER BY hostname"""
            ).fetchall()

        if not agents:
            self._send(chat_id, "No VMs registered yet.")
            return

        lines = ["*Registered VMs*", ""]
        for a in agents:
            online = (a["secs_ago"] or 9999) < 120
            status = "ONLINE" if online else "OFFLINE"
            extras = []
            if a["reboot_required"]:
                extras.append("reboot ⚠")
            if (a["pending_count"] or 0) > 0:
                extras.append(f"{a['pending_count']} updates")
            extra_str = "  " + ", ".join(extras) if extras else ""
            lines.append(f"{'🟢' if online else '🔴'} *{_esc(a['hostname'])}* — {status}{extra_str}")
            lines.append(f"   ID: `{_esc(a['id'])}` | IP: {_esc(a['ip'] or 'n/a')}")
            if a["os_pretty"]:
                lines.append(f"   {_esc(a['os_pretty'])}")
            lines.append("")

        self._send(chat_id, "\n".join(lines).rstrip())

    def _cmd_jobs(self, chat_id: str, args: list):
        n = 5
        if args:
            try:
                n = max(1, min(int(args[0]), 20))
            except ValueError:
                self._send(chat_id, "Usage: /jobs [number]  (e.g. /jobs 10)")
                return

        from db import db as get_db_ctx
        with get_db_ctx() as conn:
            jobs = conn.execute(
                """SELECT j.id, j.type, j.status, j.started, j.finished, a.hostname
                   FROM jobs j LEFT JOIN agents a ON j.agent_id = a.id
                   ORDER BY j.id DESC LIMIT ?""",
                (n,),
            ).fetchall()

        if not jobs:
            self._send(chat_id, "No jobs found.")
            return

        lines = [f"*Last {n} Jobs*", ""]
        for j in jobs:
            icon = _STATUS_ICON.get(j["status"], "•")
            host = j["hostname"] or "?"
            lines.append(f"{icon} #{j['id']} *{_esc(j['type'].upper())}* on `{_esc(host)}` — {j['status']}")
            ts = j["finished"] or j["started"]
            if ts:
                lines.append(f"   {ts}")

        self._send(chat_id, "\n".join(lines))

    def _cmd_patch(self, chat_id: str, args: list):
        if not args:
            self._send(chat_id, "Usage: /patch <vm-id|all>\n\nUse /vms to list VM IDs.")
            return
        target = args[0]
        if target != "all" and not _AGENT_ID_RE.match(target):
            self._send(chat_id, "Invalid VM ID format. Use /vms to list valid IDs.")
            return

        from db import db as get_db_ctx
        with get_db_ctx() as conn:
            if target == "all":
                agents = conn.execute("SELECT id FROM agents").fetchall()
                agent_ids = [a["id"] for a in agents]
                if not agent_ids:
                    self._send(chat_id, "No VMs registered.")
                    return
            else:
                row = conn.execute(
                    "SELECT id FROM agents WHERE id=?", (target,)
                ).fetchone()
                if not row:
                    self._send(chat_id, f"VM `{target}` not found.\n\nUse /vms to list VM IDs.")
                    return
                agent_ids = [target]

            for aid in agent_ids:
                conn.execute(
                    "INSERT INTO jobs (agent_id, type, params) VALUES (?, ?, ?)",
                    (aid, "patch", "{}"),
                )

        count = len(agent_ids)
        self._send(chat_id, f"✅ Patch job queued for *{count}* VM(s).")

    def _cmd_reboot(self, chat_id: str, args: list):
        if not args:
            self._send(chat_id, "Usage: /reboot <vm-id>\n\nUse /vms to list VM IDs.")
            return
        target = args[0]
        if not _AGENT_ID_RE.match(target):
            self._send(chat_id, "Invalid VM ID format. Use /vms to list valid IDs.")
            return

        from db import db as get_db_ctx
        with get_db_ctx() as conn:
            row = conn.execute(
                "SELECT id, hostname FROM agents WHERE id=?", (target,)
            ).fetchone()
            if not row:
                self._send(chat_id, f"VM `{target}` not found.\n\nUse /vms to list VM IDs.")
                return
            conn.execute(
                "INSERT INTO jobs (agent_id, type, params) VALUES (?, ?, ?)",
                (target, "reboot", "{}"),
            )

        self._send(chat_id, f"⚡ Reboot job queued for `{_esc(row['hostname'])}`.")

    def _cmd_updates(self, chat_id: str, args: list):
        if not args:
            self._send(chat_id, "Usage: /updates <vm-id>\n\nUse /vms to list VM IDs.")
            return
        target = args[0]
        if not _AGENT_ID_RE.match(target):
            self._send(chat_id, "Invalid VM ID format. Use /vms to list valid IDs.")
            return

        from db import db as get_db_ctx
        with get_db_ctx() as conn:
            agent = conn.execute(
                "SELECT id, hostname FROM agents WHERE id=?", (target,)
            ).fetchone()
            if not agent:
                self._send(chat_id, f"VM `{target}` not found.\n\nUse /vms to list VM IDs.")
                return
            packages = conn.execute(
                """SELECT name, current_ver, new_ver FROM packages
                   WHERE agent_id=? ORDER BY name LIMIT 30""",
                (target,),
            ).fetchall()

        if not packages:
            self._send(chat_id, f"✅ No pending updates for `{_esc(agent['hostname'])}`.")
            return

        lines = [f"*Pending updates for `{_esc(agent['hostname'])}`* ({len(packages)})", ""]
        for p in packages:
            if p["current_ver"] and p["new_ver"]:
                lines.append(f"• `{_esc(p['name'])}`: {_esc(p['current_ver'])} → {_esc(p['new_ver'])}")
            else:
                lines.append(f"• `{_esc(p['name'])}`")
        if len(packages) == 30:
            lines.append("_(showing first 30)_")

        self._send(chat_id, "\n".join(lines))


# Module-level singleton
telegram_bot = TelegramCommandBot()

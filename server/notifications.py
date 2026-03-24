"""
PatchPilot Notification System
Supports Telegram (via Bot API) and Email (via SMTP).
All external I/O uses stdlib only — no requests, no httpx.
"""

import json
import logging
import os
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def _tg_escape(text: str) -> str:
    """Escape special characters for Telegram legacy Markdown mode.

    Legacy Markdown (parse_mode='Markdown') interprets: *bold*, _italic_,
    `code`, [link](url).  Escape these characters in untrusted content so
    user-controlled strings (hostnames, job output) cannot break formatting
    or trigger unintended markup.
    """
    for ch in ('*', '_', '`', '['):
        text = text.replace(ch, '\\' + ch)
    return text


class TelegramNotifier:
    """Sends Markdown messages via the Telegram Bot API (stdlib urllib)."""

    API_BASE = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, token: str, chat_id: str):
        self.token = token.strip()
        self.chat_id = chat_id.strip()

    def send(self, message: str) -> bool:
        """Send *message* (MarkdownV2 is NOT used — plain Markdown mode).
        Returns True on success, False on any failure (silent)."""
        if not self.token or not self.chat_id:
            return False
        url = self.API_BASE.format(token=self.token)
        payload = json.dumps({
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as exc:
            log.warning("Telegram send failed: HTTP %s", exc.code)
        except Exception as exc:
            log.warning("Telegram send error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

class EmailNotifier:
    """Sends plain-text e-mails via SMTP (stdlib smtplib).

    security modes:
      - "starttls" : plain SMTP + STARTTLS upgrade (port 587, default)
      - "ssl"      : SMTP_SSL (port 465)
      - "plain"    : plain SMTP, no encryption, optional login (port 25)
      - "none"     : plain SMTP, no encryption, no login
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        to: str,
        security: str = "starttls",
    ):
        self.host = host.strip()
        self.port = int(port) if port else 587
        self.user = user.strip()
        self.password = password  # intentionally not logged
        # SEC: Sanitize email to prevent header injection
        self.to = to.strip().replace('\n', '').replace('\r', '')
        self.security = (security or "starttls").strip().lower()

    @staticmethod
    def _html(subject: str, body_text: str) -> str:
        lines = body_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        rows = "".join(
            f"<tr><td style='padding:4px 0;color:#b0c8cc;font-family:monospace;font-size:13px'>{l}</td></tr>"
            for l in lines.splitlines()
        )
        return f"""<!DOCTYPE html><html><head><meta charset='utf-8'></head>
<body style='margin:0;padding:0;background:#020c0e;font-family:monospace'>
<table width='100%' cellpadding='0' cellspacing='0'><tr><td align='center' style='padding:40px 20px'>
<table width='560' cellpadding='0' cellspacing='0' style='background:#041418;border:1px solid #1a3a40'>
  <tr><td style='background:#07272e;padding:16px 28px;border-bottom:1px solid #1a3a40'>
    <span style='font-family:monospace;font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:#27e1fa'>
      ⬡ PATCHPILOT
    </span>
  </td></tr>
  <tr><td style='padding:24px 28px 8px'>
    <p style='margin:0 0 20px;font-size:16px;font-weight:700;color:#e0f4f8;letter-spacing:.04em'>{subject}</p>
    <table width='100%' cellpadding='0' cellspacing='0'>{rows}</table>
  </td></tr>
  <tr><td style='padding:16px 28px;border-top:1px solid #1a3a40'>
    <span style='font-size:10px;color:#3a6068;letter-spacing:.1em'>PATCHPILOT AUTOMATED ALERT</span>
  </td></tr>
</table>
</td></tr></table></body></html>"""

    def send(self, subject: str, body: str) -> bool:
        """Send an e-mail.  Returns True on success, False on any failure."""
        if not self.host or not self.to:
            return False
        from_addr = self.user or f"patchpilot@{self.host}"
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"PatchPilot <{from_addr}>"
        msg["To"] = self.to
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(self._html(subject, body), "html", "utf-8"))
        try:
            context = ssl.create_default_context()
            if self.security == "ssl":
                with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=15) as smtp:
                    smtp.ehlo()
                    if self.user and self.password:
                        smtp.login(self.user, self.password)
                    smtp.sendmail(from_addr, [self.to], msg.as_string())
            elif self.security == "starttls":
                with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
                    smtp.ehlo()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                    if self.user and self.password:
                        smtp.login(self.user, self.password)
                    smtp.sendmail(from_addr, [self.to], msg.as_string())
            else:
                with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
                    smtp.ehlo()
                    if self.security == "plain" and self.user and self.password:
                        smtp.login(self.user, self.password)
                    smtp.sendmail(from_addr, [self.to], msg.as_string())
            return True
        except smtplib.SMTPAuthenticationError:
            log.warning("Email: authentication failed (check smtp_user/smtp_password)")
        except smtplib.SMTPException as exc:
            log.warning("Email SMTP error: %s", exc)
        except Exception as exc:
            log.warning("Email send error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Notification Manager
# ---------------------------------------------------------------------------

class NotificationManager:
    """
    Reads configuration from the DB `settings` table (or falls back to
    environment variables) and dispatches notifications to the configured
    channels.  All notification methods are silent-fail when not configured.
    """

    def __init__(self):
        self._telegram: TelegramNotifier | None = None
        self._email: EmailNotifier | None = None
        self._notify_offline = True
        self._notify_patches = True
        self._notify_failures = True
        self._loaded = False

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load(self):
        """Load settings lazily from DB (deferred import to avoid circular)."""
        if self._loaded:
            return
        try:
            from db import db as get_db_ctx  # local import — avoids circular dep
            with get_db_ctx() as conn:
                rows = conn.execute("SELECT key, value FROM settings").fetchall()
            cfg = {r["key"]: r["value"] for r in rows}
        except Exception as exc:
            log.warning("NotificationManager: could not read settings from DB: %s", exc)
            cfg = {}

        # Decrypt sensitive values from DB
        try:
            from crypto import decrypt as _dec
        except ImportError:
            _dec = lambda v: v  # noqa: E731

        # Merge env-variable overrides (env takes precedence)
        def _get(key: str, default: str = "", sensitive: bool = False) -> str:
            env_key = f"PATCHPILOT_{key.upper()}"
            val = os.environ.get(env_key, cfg.get(key, default))
            return _dec(val) if sensitive else val

        tg_token   = _get("telegram_token", sensitive=True)
        tg_chat    = _get("telegram_chat_id")
        smtp_host     = _get("smtp_host")
        smtp_port     = _get("smtp_port", "587")
        smtp_security = _get("smtp_security", "starttls")
        smtp_user     = _get("smtp_user")
        smtp_pass     = _get("smtp_password", sensitive=True)
        smtp_to       = _get("smtp_to")

        self._email_enabled    = _get("email_enabled",    "1") == "1"
        self._notify_offline   = _get("notify_offline",  "1") == "1"
        self._notify_patches   = _get("notify_patches",  "1") == "1"
        self._notify_failures  = _get("notify_failures", "1") == "1"
        self._telegram_enabled = _get("telegram_enabled", "1") == "1"

        # Per-channel event toggles for Telegram
        self._tg_notify_offline  = _get("telegram_notify_offline",  "1") == "1"
        self._tg_notify_patches  = _get("telegram_notify_patches",  "1") == "1"
        self._tg_notify_failures = _get("telegram_notify_failures", "1") == "1"
        self._tg_notify_success  = _get("telegram_notify_success",  "1") == "1"

        self._telegram = TelegramNotifier(tg_token, tg_chat) if (tg_token and self._telegram_enabled) else None
        self._email    = EmailNotifier(smtp_host, smtp_port, smtp_user, smtp_pass, smtp_to, smtp_security) \
                         if (smtp_host and self._email_enabled) else None
        self._loaded = True

    def reload(self):
        """Force-reload settings on next dispatch (call after settings save)."""
        self._loaded = False
        self._telegram = None  # clear stale reference immediately

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    def _send(self, subject: str, body: str, *, telegram: bool = True):
        """Dispatch to all configured channels."""
        self._load()
        if self._telegram and telegram and self._telegram_enabled:
            self._telegram.send(f"*{_tg_escape(subject)}*\n{_tg_escape(body)}")
        if self._email:
            self._email.send(f"[PatchPilot] {subject}", body)

    # ------------------------------------------------------------------
    # Public notification methods
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt_last_seen(last_seen: str | None) -> str:
        """Return a human-readable relative time string for a last_seen timestamp."""
        if not last_seen:
            return "never"
        try:
            # Timestamps are stored as local time (no timezone info)
            dt = datetime.fromisoformat(last_seen.replace("Z", ""))
            secs = int((datetime.now() - dt).total_seconds())
            if secs < 60:
                return f"{secs}s ago"
            elif secs < 3600:
                return f"{secs // 60}m ago"
            elif secs < 86400:
                h, m = divmod(secs // 60, 60)
                return f"{h}h {m}m ago"
            else:
                days = secs // 86400
                h = (secs % 86400) // 3600
                return f"{days}d {h}h ago"
        except Exception:
            return last_seen  # fallback to raw value

    def notify_vm_offline(self, agent: dict):
        """VM has been offline for > 10 minutes."""
        self._load()
        if not self._notify_offline:
            return
        hostname = agent.get("hostname", agent.get("id", "unknown"))
        minutes = int((agent.get("seconds_ago") or 0) / 60)
        last_seen_str = self._fmt_last_seen(agent.get("last_seen"))
        self._send(
            f"VM Offline: {hostname}",
            f"Host {hostname} ({agent.get('ip', 'n/a')}) has not reported in "
            f"for {minutes} minutes.\nLast seen: {last_seen_str}",
            telegram=self._tg_notify_offline,
        )

    def notify_patch_available(self, agent: dict, count: int):
        """New package updates are available on a VM."""
        self._load()
        if not self._notify_patches:
            return
        hostname = agent.get("hostname", agent.get("id", "unknown"))
        self._send(
            f"Updates Available: {hostname}",
            f"{count} package update(s) available on {hostname} ({agent.get('ip', 'n/a')}).",
            telegram=self._tg_notify_patches,
        )

    def notify_job_failed(self, agent: dict, job: dict):
        """A patch job finished with status 'failed'."""
        self._load()
        if not self._notify_failures:
            return
        hostname = agent.get("hostname", agent.get("id", "unknown"))
        job_type = job.get("type", "unknown")
        job_id   = job.get("id", "?")
        output   = (job.get("output") or "")[:500]
        self._send(
            f"Job Failed: {hostname}",
            f"Job #{job_id} ({job_type}) failed on {hostname}.\n\nOutput:\n{output}",
            telegram=self._tg_notify_failures,
        )

    def notify_job_success(self, agent: dict, job: dict):
        """A job finished successfully."""
        self._load()
        hostname = agent.get("hostname", agent.get("id", "unknown"))
        job_type = job.get("type", "unknown")
        job_id   = job.get("id", "?")
        output   = (job.get("output") or "")[:500]
        body = f"Job #{job_id} ({job_type}) completed on {hostname}."
        if "CONFIG NOTICE" in output:
            body += "\n⚠ Config files were kept — review manually"
        # Success notifications go to Telegram only (if enabled), not email
        if self._telegram and self._telegram_enabled and self._tg_notify_success:
            self._telegram.send(f"*Job Completed: {_tg_escape(hostname)}*\n{_tg_escape(body)}")

    def notify_reboot_required(self, agent: dict):
        """A reboot is required after patching."""
        self._load()
        if not self._notify_patches:
            return
        hostname = agent.get("hostname", agent.get("id", "unknown"))
        self._send(
            f"Reboot Required: {hostname}",
            f"Host {hostname} ({agent.get('ip', 'n/a')}) requires a reboot "
            f"after applying patches.",
            telegram=self._tg_notify_patches,
        )


# Module-level singleton
notification_manager = NotificationManager()

import fcntl
import json
import logging
import os
import platform
import subprocess
from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger(__name__)

_DEFAULT_TIMEZONE = "Europe/Berlin"

scheduler = BackgroundScheduler(timezone=_DEFAULT_TIMEZONE)

_ONLINE_WINDOW_SECONDS = 120
_PENDING_JOB_GRACE_SECONDS = 180
_RUNNING_JOB_GRACE_SECONDS = 900
_CONNECTIVITY_GRACE_JOB_TYPES = {
    "patch",
    "dist_upgrade",
    "force_patch",
    "autoremove",
    "reboot",
    "update_agent",
    "deploy_ssl",
    "ha_backup",
    "ha_core_update",
    "ha_backup_update",
    "ha_supervisor_update",
    "ha_os_update",
    "ha_addon_update",
    "ha_addons_update",
    "ha_entity_update",
    "ha_trigger_agent_update",
}


def get_scheduler_timezone() -> str:
    """Read the configured scheduler timezone from the DB, fall back to default."""
    try:
        from db import db as get_db_ctx
        with get_db_ctx() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='scheduler_timezone'"
            ).fetchone()
        if row and row["value"]:
            return row["value"]
    except Exception:
        pass
    return _DEFAULT_TIMEZONE


def _parse_localtime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def agent_connectivity_state(seconds_ago: int | float | None, last_job: dict | None = None) -> str:
    if seconds_ago is not None and seconds_ago < _ONLINE_WINDOW_SECONDS:
        return "online"
    if not last_job:
        return "offline"
    job_type = str(last_job.get("type") or "")
    job_status = str(last_job.get("status") or "")
    if job_type not in _CONNECTIVITY_GRACE_JOB_TYPES or job_status not in {"pending", "running"}:
        return "offline"
    reference_raw = last_job.get("started") if job_status == "running" else last_job.get("created")
    reference_dt = _parse_localtime(str(reference_raw or ""))
    if not reference_dt:
        return "offline"
    grace = _RUNNING_JOB_GRACE_SECONDS if job_status == "running" else _PENDING_JOB_GRACE_SECONDS
    age = (datetime.now() - reference_dt).total_seconds()
    return "busy" if age <= grace else "offline"


def is_effectively_online(seconds_ago: int | float | None, last_job: dict | None = None) -> bool:
    return agent_connectivity_state(seconds_ago, last_job) != "offline"


def _ping_command(target: str) -> list[str]:
    if platform.system().lower() == "darwin":
        return ["ping", "-n", "-c", "1", "-W", "2000", target]
    return ["ping", "-n", "-c", "1", "-W", "2", target]


def _probe_ping_target(target: str) -> bool:
    target = str(target or "").strip()
    if not target:
        return False
    try:
        result = subprocess.run(
            _ping_command(target),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def trigger_ping_check_for_agent(agent_id: str) -> bool:
    from db import db as get_db_ctx

    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT id, hostname, ip, agent_type FROM agents WHERE id=?",
            (agent_id,),
        ).fetchone()
        if not row or str(row["agent_type"] or "") != "ping":
            return False
        target = str(row["ip"] or row["hostname"] or "").strip()

    reachable = _probe_ping_target(target)
    if reachable:
        with get_db_ctx() as conn:
            conn.execute(
                "UPDATE agents SET last_seen=datetime('now','localtime') WHERE id=?",
                (agent_id,),
            )
    return reachable


def configure_timezone(tz: str):
    """Reconfigure the scheduler timezone (call before scheduler.start())."""
    try:
        import zoneinfo
        zoneinfo.ZoneInfo(tz)  # validate
    except Exception:
        log.warning("Invalid scheduler_timezone %r — keeping %r", tz, _DEFAULT_TIMEZONE)
        return
    scheduler.configure(timezone=tz)
    log.info("Scheduler timezone set to %s", tz)

# Tracks agents already notified as offline to avoid repeated notifications.
# Key: agent_id  — value: True (currently offline-notified)
_offline_notified: set[str] = set()

# File lock: only the first process to acquire it runs the scheduled jobs.
# This prevents duplicate notifications when UI and Agent port run as separate processes.
_scheduler_lock_fd = None


def _try_acquire_scheduler_lock() -> bool:
    """Try to acquire an exclusive non-blocking file lock.
    Returns True if this process should register and run scheduled jobs."""
    global _scheduler_lock_fd
    try:
        data_dir = Path(os.environ.get("PATCHPILOT_DATA_DIR", "/opt/patchpilot/data"))
        data_dir.mkdir(parents=True, exist_ok=True)
        lock_path = data_dir / "scheduler.lock"
        _scheduler_lock_fd = open(lock_path, "w")
        fcntl.flock(_scheduler_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (IOError, OSError):
        return False

def _get_offline_threshold() -> int:
    try:
        from db import db as get_db_ctx
        with get_db_ctx() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='notify_offline_minutes'"
            ).fetchone()
        if row:
            return max(1, int(row["value"])) * 60
    except Exception:
        pass
    return 120  # default 2 minutes


def _check_offline_vms():
    """
    Run every 5 minutes.  Queries the DB for agents whose last heartbeat is
    older than the configured threshold and sends a single notification per
    agent per offline episode.  De-duplication is persisted in the DB column
    offline_notified so it survives service restarts.
    """
    try:
        from db import db as get_db_ctx
        from notifications import notification_manager

        with get_db_ctx() as conn:
            agents = conn.execute(
                """SELECT *,
                   CAST((julianday('now','localtime') - julianday(last_seen)) * 86400 AS INTEGER)
                       as seconds_ago
                   FROM agents"""
            ).fetchall()
            last_jobs = conn.execute(
                """SELECT j.agent_id, j.type, j.status, j.created, j.started
                   FROM jobs j
                   INNER JOIN (
                       SELECT agent_id, MAX(id) as max_id
                       FROM jobs
                       GROUP BY agent_id
                   ) latest ON j.id = latest.max_id"""
            ).fetchall()
        last_job_map = {row["agent_id"]: dict(row) for row in last_jobs}

        threshold = _get_offline_threshold()
        for row in agents:
            agent = dict(row)
            agent_id = agent["id"]
            seconds_ago = agent.get("seconds_ago") or 0
            already_notified = bool(agent.get("offline_notified"))

            if is_effectively_online(seconds_ago, last_job_map.get(agent_id)):
                # Agent is back online — reset flag so we can notify again next episode
                if already_notified:
                    with get_db_ctx() as conn:
                        conn.execute("UPDATE agents SET offline_notified=0 WHERE id=?", (agent_id,))
                _offline_notified.discard(agent_id)
                continue

            if seconds_ago > threshold:
                # Only notify once per offline episode (DB-persisted)
                if not already_notified and agent_id not in _offline_notified:
                    log.info(
                        "VM offline notification: %s (offline %ds)",
                        agent.get("hostname"), seconds_ago,
                    )
                    notification_manager.notify_vm_offline(agent)
                    _offline_notified.add(agent_id)
                    with get_db_ctx() as conn:
                        conn.execute("UPDATE agents SET offline_notified=1 WHERE id=?", (agent_id,))

    except Exception as exc:
        log.warning("_check_offline_vms error: %s", exc)


def _check_ping_targets():
    try:
        from db import db as get_db_ctx

        with get_db_ctx() as conn:
            rows = conn.execute(
                "SELECT id FROM agents WHERE COALESCE(agent_type, 'linux')='ping'"
            ).fetchall()
        for row in rows:
            trigger_ping_check_for_agent(row["id"])
    except Exception as exc:
        log.warning("_check_ping_targets error: %s", exc)


_ALLOWED_JOB_TYPES = {"patch", "dist_upgrade", "refresh_updates", "reboot"}

def _run_scheduled_job(schedule_id: int, action: str, target: str):
    # C-3: Validate action against allowlist before inserting into jobs table
    if action not in _ALLOWED_JOB_TYPES:
        log.warning("Blocked invalid scheduled job action: %r", action)
        return
    log.info("Schedule #%s triggered: action=%s target=%s", schedule_id, action, target)
    try:
        from db import db as get_db_ctx

        with get_db_ctx() as conn:
            if target == "all":
                agents = conn.execute("SELECT id FROM agents").fetchall()
                agent_ids = [a["id"] for a in agents]
            else:
                # Support comma-separated list of agent IDs (multi-VM target)
                requested = [t.strip() for t in target.split(",") if t.strip()]
                # Only keep IDs that actually exist in the DB (defensive check)
                placeholders = ",".join("?" * len(requested))
                rows = conn.execute(
                    f"SELECT id FROM agents WHERE id IN ({placeholders})",  # noqa: S608
                    requested,
                ).fetchall()
                agent_ids = [r["id"] for r in rows]

            for agent_id in agent_ids:
                conn.execute(
                    "INSERT INTO jobs (agent_id, type, params, created) VALUES (?, ?, ?, datetime('now','localtime'))",
                    (agent_id, action, "{}"),
                )
            conn.execute(
                "UPDATE schedules SET last_run=datetime('now','localtime') WHERE id=?",
                (schedule_id,),
            )
        log.info("Schedule #%s: queued %d job(s)", schedule_id, len(agent_ids))
    except Exception as exc:
        log.error("Schedule #%s failed: %s", schedule_id, exc)


def _cleanup_stale_jobs():
    """Mark stale pending/running jobs as failed."""
    try:
        from db import db as get_db_ctx
        with get_db_ctx() as conn:
            running = conn.execute(
                "UPDATE jobs SET status='failed', "
                "output=COALESCE(output,'') || '\n[server] Marked as failed: stuck in running state', "
                "finished=datetime('now','localtime') "
                "WHERE status='running' AND started IS NOT NULL "
                "AND (julianday('now','localtime') - julianday(started)) * 86400 > 900"
            ).rowcount
            pending = conn.execute(
                "UPDATE jobs SET status='failed', "
                "output=COALESCE(output,'') || '\n[server] Marked as failed: expired in pending state', "
                "finished=datetime('now','localtime') "
                "WHERE status='pending' AND created IS NOT NULL "
                "AND (julianday('now','localtime') - julianday(created)) * 86400 > 1800"
            ).rowcount
            if running:
                log.info("Cleaned up %d stale running job(s)", running)
            if pending:
                log.info("Cleaned up %d stale pending job(s)", pending)
    except Exception as exc:
        log.error("Stale job cleanup failed: %s", exc)


def schedule_job(schedule_id: int, name: str, cron: str, action: str, target: str):
    parts = cron.strip().split()
    if len(parts) != 5:
        return
    minute, hour, day, month, day_of_week = parts
    try:
        trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=get_scheduler_timezone(),
        )
        scheduler.add_job(
            _run_scheduled_job,
            trigger=trigger,
            args=[schedule_id, action, target],
            id=str(schedule_id),
            name=name,
            replace_existing=True,
        )
    except Exception as e:
        log.error("Failed to schedule job %s: %s", schedule_id, e)


def parse_cron_desc(cron: str) -> str:
    """Return a very basic human-readable description."""
    parts = cron.strip().split()
    if len(parts) != 5:
        return cron
    minute, hour, day, month, dow = parts
    if cron == "0 * * * *":
        return "Every hour"
    if minute == "0" and hour != "*" and day == "*" and month == "*" and dow == "*":
        return f"Daily at {hour}:00 UTC"
    if minute != "*" and hour != "*" and day == "*" and month == "*" and dow != "*":
        days = {"0": "Sun", "1": "Mon", "2": "Tue", "3": "Wed", "4": "Thu", "5": "Fri", "6": "Sat"}
        day_name = days.get(dow, dow)
        return f"Every {day_name} at {hour}:{minute.zfill(2)} UTC"
    return cron


def load_schedules_from_db():
    from db import db as get_db_ctx

    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT id, name, cron, action, target, enabled FROM schedules WHERE enabled=1"
        ).fetchall()
    for row in rows:
        schedule_job(row["id"], row["name"], row["cron"], row["action"], row["target"])


def register_system_jobs():
    """Register internal background jobs (offline VM check, etc.).
    Called once from app.py startup after the scheduler has been started.
    Only the first process to acquire the scheduler lock will register jobs;
    additional processes (e.g. the agent-port uvicorn worker) skip this."""
    if not _try_acquire_scheduler_lock():
        log.info("Scheduler: another process holds the lock — skipping job registration")
        return
    scheduler.add_job(
        _check_offline_vms,
        trigger=IntervalTrigger(minutes=2),
        id="__check_offline_vms__",
        name="Check offline VMs",
        replace_existing=True,
    )

    scheduler.add_job(
        _cleanup_stale_jobs,
        trigger=IntervalTrigger(minutes=5),
        id="__cleanup_stale_jobs__",
        name="Cleanup stale running jobs",
        replace_existing=True,
    )

    scheduler.add_job(
        _check_ping_targets,
        trigger=IntervalTrigger(seconds=60),
        id="__check_ping_targets__",
        name="Check ping-only targets",
        replace_existing=True,
    )

    from telegram_bot import telegram_bot
    scheduler.add_job(
        telegram_bot.poll_once,
        trigger=IntervalTrigger(seconds=5),
        id="__telegram_bot_poll__",
        name="Telegram bot poll",
        replace_existing=True,
    )

import json
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="Europe/Berlin")

# Tracks agents already notified as offline to avoid repeated notifications.
# Key: agent_id  — value: True (currently offline-notified)
_offline_notified: set[str] = set()

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
    return 600  # default 10 minutes


def _check_offline_vms():
    """
    Run every 5 minutes.  Queries the DB for agents whose last heartbeat is
    older than _OFFLINE_THRESHOLD_SECONDS and sends a single notification per
    agent (de-duplicated via _offline_notified).  When an agent comes back
    online it is removed from the set so it can be notified again later.
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

        threshold = _get_offline_threshold()
        for row in agents:
            agent = dict(row)
            agent_id = agent["id"]
            seconds_ago = agent.get("seconds_ago") or 0

            if seconds_ago > threshold:
                # Only notify once per offline episode
                if agent_id not in _offline_notified:
                    log.info(
                        "VM offline notification: %s (offline %ds)",
                        agent.get("hostname"), seconds_ago,
                    )
                    notification_manager.notify_vm_offline(agent)
                    _offline_notified.add(agent_id)
            else:
                # Agent is back online — reset so we can notify again next time
                _offline_notified.discard(agent_id)

    except Exception as exc:
        log.warning("_check_offline_vms error: %s", exc)


_ALLOWED_JOB_TYPES = {"patch", "reboot"}

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
                    "INSERT INTO jobs (agent_id, type, params) VALUES (?, ?, ?)",
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
    """Mark jobs stuck in 'running' for >15 min as failed."""
    try:
        from db import db as get_db_ctx
        with get_db_ctx() as conn:
            n = conn.execute(
                "UPDATE jobs SET status='failed', "
                "output=COALESCE(output,'') || '\n[server] Marked as failed: stuck in running state', "
                "finished=datetime('now','localtime') "
                "WHERE status='running' AND started IS NOT NULL "
                "AND (julianday('now','localtime') - julianday(started)) * 86400 > 900"
            ).rowcount
            if n:
                log.info("Cleaned up %d stale running job(s)", n)
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
            timezone="Europe/Berlin",
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
    Called once from app.py startup after the scheduler has been started."""
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

    from telegram_bot import telegram_bot
    scheduler.add_job(
        telegram_bot.poll_once,
        trigger=IntervalTrigger(seconds=5),
        id="__telegram_bot_poll__",
        name="Telegram bot poll",
        replace_existing=True,
    )

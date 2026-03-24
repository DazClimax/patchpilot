"""
metrics.py — Prometheus-compatible exposition endpoint for PatchPilot.

Exposes GET /metrics in the Prometheus text format (version 0.0.4).
No external prometheus_client dependency — built manually.
"""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from db import db as get_db_ctx

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prom_escape(value: str) -> str:
    """CRIT-3: Escape Prometheus label values per the text format spec.
    Backslash, double-quote, and newline must be escaped."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _gauge(name: str, help_text: str, value: float, labels: dict | None = None) -> str:
    label_str = ""
    if labels:
        pairs = ",".join(f'{k}="{_prom_escape(str(v))}"' for k, v in labels.items())
        label_str = f"{{{pairs}}}"
    return (
        f"# HELP {name} {help_text}\n"
        f"# TYPE {name} gauge\n"
        f"{name}{label_str} {value}\n"
    )


def _counter_block(name: str, help_text: str, rows: list[tuple[dict, float]]) -> str:
    """Emit a counter TYPE block with multiple label-sets."""
    lines = [f"# HELP {name} {help_text}", f"# TYPE {name} counter"]
    for labels, value in rows:
        if labels:
            pairs = ",".join(f'{k}="{_prom_escape(str(v))}"' for k, v in labels.items())
            lines.append(f"{name}{{{pairs}}} {value}")
        else:
            lines.append(f"{name} {value}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Return Prometheus-compatible metrics in text exposition format."""
    with get_db_ctx() as conn:
        # --- agents_total ---
        agents_total = conn.execute("SELECT COUNT(*) as n FROM agents").fetchone()["n"]

        # --- agents_online (seen within last 120 s) ---
        agents_online = conn.execute(
            """SELECT COUNT(*) as n FROM agents
               WHERE (julianday('now','localtime') - julianday(last_seen)) * 86400 < 120"""
        ).fetchone()["n"]

        # --- pending_updates_total ---
        pending_row = conn.execute(
            "SELECT COALESCE(SUM(pending_count), 0) as n FROM agents"
        ).fetchone()
        pending_updates_total = pending_row["n"]

        # --- reboot_required_total ---
        reboot_required_total = conn.execute(
            "SELECT COUNT(*) as n FROM agents WHERE reboot_required = 1"
        ).fetchone()["n"]

        # --- jobs by status ---
        job_rows = conn.execute(
            """SELECT status, COUNT(*) as n FROM jobs GROUP BY status"""
        ).fetchall()

    job_counts = {r["status"]: r["n"] for r in job_rows}

    output_parts: list[str] = []

    output_parts.append(
        _gauge("patchpilot_agents_total", "Total number of registered agents", agents_total)
    )
    output_parts.append(
        _gauge(
            "patchpilot_agents_online",
            "Number of agents seen within the last 2 minutes",
            agents_online,
        )
    )
    output_parts.append(
        _gauge(
            "patchpilot_pending_updates_total",
            "Total number of pending package updates across all agents",
            pending_updates_total,
        )
    )
    output_parts.append(
        _gauge(
            "patchpilot_reboot_required_total",
            "Number of VMs that require a reboot",
            reboot_required_total,
        )
    )

    # jobs counter — emit all known statuses so the metric always exists
    known_statuses = ["done", "failed", "running", "pending"]
    jobs_rows: list[tuple[dict, float]] = [
        ({"status": s}, float(job_counts.get(s, 0))) for s in known_statuses
    ]
    output_parts.append(
        _counter_block(
            "patchpilot_jobs_total",
            "Total number of jobs grouped by status",
            jobs_rows,
        )
    )

    return "".join(output_parts)

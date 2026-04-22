"""Observability layer - structured logging, metrics, notifications, and dashboard data."""

import csv
import json
import logging
import os
import smtplib
import statistics
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    import urllib.request
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

logger = logging.getLogger("actionshot.telemetry")

_LOGS_ROOT = os.path.join(os.path.expanduser("~"), ".actionshot", "logs")


def _ensure_dir(path: str) -> None:
    """Create directory if it doesn't exist."""
    os.makedirs(path, exist_ok=True)


def _utcnow_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


# ---------------------------------------------------------------------------
# 1. WorkflowLogger
# ---------------------------------------------------------------------------

class WorkflowLogger:
    """Structured JSONL logging for every RPA execution.

    All events are written to ``~/.actionshot/logs/{workflow_id}/{date}.jsonl``.
    Older log files are automatically cleaned up based on *retention_days*.
    """

    def __init__(self, logs_root: str | None = None, retention_days: int = 30) -> None:
        self.logs_root = logs_root or _LOGS_ROOT
        self.retention_days = retention_days

    # -- helpers ----------------------------------------------------------

    def _log_dir(self, workflow_id: str) -> str:
        return os.path.join(self.logs_root, workflow_id)

    def _log_path(self, workflow_id: str) -> str:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        return os.path.join(self._log_dir(workflow_id), f"{date_str}.jsonl")

    def _write(self, workflow_id: str, event: dict) -> None:
        path = self._log_path(workflow_id)
        _ensure_dir(os.path.dirname(path))
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")

    # -- public API -------------------------------------------------------

    def start_execution(self, workflow_id: str, params: dict | None = None) -> str:
        """Log the start of a workflow execution. Returns the event timestamp."""
        ts = _utcnow_iso()
        self._write(workflow_id, {
            "event": "execution_start",
            "timestamp": ts,
            "workflow_id": workflow_id,
            "params": params or {},
        })
        self._cleanup_old_logs(workflow_id)
        return ts

    def step_completed(self, workflow_id: str, step_id: str,
                       selector_level_used: str, duration_ms: float) -> None:
        """Log a successfully completed step."""
        self._write(workflow_id, {
            "event": "step_completed",
            "timestamp": _utcnow_iso(),
            "workflow_id": workflow_id,
            "step_id": step_id,
            "selector_level_used": selector_level_used,
            "duration_ms": round(duration_ms, 2),
        })

    def step_failed(self, workflow_id: str, step_id: str,
                    error: str, context: dict | None = None) -> None:
        """Log a step failure with full context."""
        self._write(workflow_id, {
            "event": "step_failed",
            "timestamp": _utcnow_iso(),
            "workflow_id": workflow_id,
            "step_id": step_id,
            "error": error,
            "context": context or {},
        })

    def end_execution(self, workflow_id: str, status: str,
                      duration_ms: float) -> None:
        """Log the completion of a workflow execution."""
        self._write(workflow_id, {
            "event": "execution_end",
            "timestamp": _utcnow_iso(),
            "workflow_id": workflow_id,
            "status": status,
            "duration_ms": round(duration_ms, 2),
        })

    # -- retention --------------------------------------------------------

    def _cleanup_old_logs(self, workflow_id: str) -> None:
        """Delete log files older than *retention_days*."""
        log_dir = self._log_dir(workflow_id)
        if not os.path.isdir(log_dir):
            return

        cutoff = datetime.utcnow() - timedelta(days=self.retention_days)
        for filename in os.listdir(log_dir):
            if not filename.endswith(".jsonl"):
                continue
            date_part = filename.replace(".jsonl", "")
            try:
                file_date = datetime.strptime(date_part, "%Y-%m-%d")
            except ValueError:
                continue
            if file_date < cutoff:
                try:
                    os.remove(os.path.join(log_dir, filename))
                    logger.info("Removed old log file: %s/%s", workflow_id, filename)
                except OSError as exc:
                    logger.warning("Failed to remove old log %s: %s", filename, exc)


# ---------------------------------------------------------------------------
# 2. ExecutionTracker
# ---------------------------------------------------------------------------

class ExecutionTracker:
    """Aggregates metrics across executions by reading JSONL log files."""

    def __init__(self, logs_root: str | None = None) -> None:
        self.logs_root = logs_root or _LOGS_ROOT

    # -- internal ---------------------------------------------------------

    def _read_events(self, workflow_id: str) -> list[dict]:
        """Read all events for a workflow from JSONL files, sorted by time."""
        log_dir = os.path.join(self.logs_root, workflow_id)
        if not os.path.isdir(log_dir):
            return []

        events: list[dict] = []
        for filename in sorted(os.listdir(log_dir)):
            if not filename.endswith(".jsonl"):
                continue
            filepath = os.path.join(log_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return events

    # -- public API -------------------------------------------------------

    def get_stats(self, workflow_id: str) -> dict:
        """Return aggregated statistics for a workflow."""
        events = self._read_events(workflow_id)

        starts = [e for e in events if e.get("event") == "execution_start"]
        ends = [e for e in events if e.get("event") == "execution_end"]
        steps = [e for e in events if e.get("event") == "step_completed"]
        failures = [e for e in events if e.get("event") == "step_failed"]

        total = len(starts)
        successes = [e for e in ends if e.get("status") == "success"]
        fails = [e for e in ends if e.get("status") != "success"]

        durations = [e["duration_ms"] for e in ends if "duration_ms" in e]
        avg_dur = round(statistics.mean(durations), 2) if durations else 0.0
        p95_dur = round(_percentile(durations, 95), 2) if durations else 0.0

        success_rate = round((len(successes) / total) * 100, 2) if total else 0.0

        # Selector fallback rate: steps using a non-primary selector
        primary_selectors = {"id", "automation_id", "primary", "level_0"}
        total_steps = len(steps)
        fallback_steps = sum(
            1 for s in steps
            if s.get("selector_level_used", "primary") not in primary_selectors
        )
        fallback_rate = round((fallback_steps / total_steps) * 100, 2) if total_steps else 0.0

        # Healing iterations: look for healing context in failure events
        healing_counts = [
            e.get("context", {}).get("healing_iterations", 0) for e in failures
        ]
        avg_healing = round(statistics.mean(healing_counts), 2) if healing_counts else 0.0

        # Last execution
        last_exec: dict | None = None
        if ends:
            last = ends[-1]
            last_exec = {"timestamp": last.get("timestamp"), "status": last.get("status")}

        # Last failure
        last_fail: dict | None = None
        if fails:
            last_f = fails[-1]
            last_fail = {"timestamp": last_f.get("timestamp"), "error_summary": last_f.get("status")}
        if not last_fail and failures:
            last_f = failures[-1]
            last_fail = {"timestamp": last_f.get("timestamp"), "error_summary": last_f.get("error", "")}

        return {
            "workflow_id": workflow_id,
            "total_executions": total,
            "success_count": len(successes),
            "failure_count": len(fails),
            "success_rate": success_rate,
            "avg_duration_ms": avg_dur,
            "p95_duration_ms": p95_dur,
            "last_execution": last_exec,
            "last_failure": last_fail,
            "selector_fallback_rate": fallback_rate,
            "healing_iterations": avg_healing,
        }

    def get_all_workflows(self) -> list[dict]:
        """Return a list of all tracked workflow IDs with summary stats."""
        if not os.path.isdir(self.logs_root):
            return []

        results: list[dict] = []
        for name in sorted(os.listdir(self.logs_root)):
            full = os.path.join(self.logs_root, name)
            if os.path.isdir(full):
                stats = self.get_stats(name)
                results.append(stats)
        return results

    def get_failures(self, workflow_id: str, last_n: int = 10) -> list[dict]:
        """Return the last *last_n* failure events with context."""
        events = self._read_events(workflow_id)
        failures = [
            e for e in events
            if e.get("event") in ("step_failed", "execution_end")
            and (e.get("event") == "step_failed" or e.get("status") != "success")
        ]
        return failures[-last_n:]


def _percentile(data: list[float], pct: float) -> float:
    """Compute the *pct*-th percentile of a sorted list."""
    if not data:
        return 0.0
    s = sorted(data)
    k = (pct / 100) * (len(s) - 1)
    f = int(k)
    c = f + 1
    if c >= len(s):
        return s[f]
    return s[f] + (k - f) * (s[c] - s[f])


# ---------------------------------------------------------------------------
# 3. NotificationDispatcher
# ---------------------------------------------------------------------------

class NotificationDispatcher:
    """Sends alerts on failure via configurable channels.

    Channels: ``webhook``, ``email``, ``file``.

    Configuration comes from environment variables or a config dict passed at
    init (e.g. parsed from ``actionshot.yaml``).

    Rate limiting: at most 1 notification per workflow per 5 minutes.
    """

    RATE_LIMIT_SECONDS = 300  # 5 minutes

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        # Track last notification time per workflow to enforce rate limits
        self._last_notified: dict[str, float] = {}

    # -- public API -------------------------------------------------------

    def notify(self, event: dict, channels: list[str] | None = None) -> list[str]:
        """Dispatch *event* to the specified *channels*.

        Returns a list of channels that were successfully notified.
        """
        workflow_id = event.get("workflow_id", "unknown")

        # Rate limiting
        now = time.time()
        last = self._last_notified.get(workflow_id, 0.0)
        if now - last < self.RATE_LIMIT_SECONDS:
            logger.info("Rate-limited notification for workflow %s", workflow_id)
            return []

        if channels is None:
            channels = self._default_channels()

        sent: list[str] = []
        for ch in channels:
            try:
                if ch == "webhook":
                    self._send_webhook(event)
                elif ch == "email":
                    self._send_email(event)
                elif ch == "file":
                    self._send_file(event)
                else:
                    logger.warning("Unknown notification channel: %s", ch)
                    continue
                sent.append(ch)
            except Exception as exc:
                logger.error("Notification via %s failed: %s", ch, exc)

        if sent:
            self._last_notified[workflow_id] = now

        return sent

    # -- channel implementations -----------------------------------------

    def _send_webhook(self, event: dict) -> None:
        url = self._cfg("webhook_url", env="ACTIONSHOT_WEBHOOK_URL")
        if not url:
            raise ValueError("No webhook URL configured (set ACTIONSHOT_WEBHOOK_URL)")

        payload = json.dumps(event, default=str).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"Webhook returned HTTP {resp.status}")

    def _send_email(self, event: dict) -> None:
        host = self._cfg("smtp_host", env="ACTIONSHOT_SMTP_HOST")
        port = int(self._cfg("smtp_port", env="ACTIONSHOT_SMTP_PORT", default="587"))
        user = self._cfg("smtp_user", env="ACTIONSHOT_SMTP_USER")
        password = self._cfg("smtp_password", env="ACTIONSHOT_SMTP_PASSWORD")
        to_addr = self._cfg("smtp_to", env="ACTIONSHOT_SMTP_TO")

        if not all([host, user, password, to_addr]):
            raise ValueError(
                "Incomplete SMTP config (need ACTIONSHOT_SMTP_HOST, _USER, _PASSWORD, _TO)"
            )

        subject = f"[ActionShot] {event.get('event', 'alert')} - {event.get('workflow_id', '?')}"
        body = json.dumps(event, indent=2, default=str)

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to_addr

        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [to_addr], msg.as_string())

    def _send_file(self, event: dict) -> None:
        path = self._cfg(
            "notification_log",
            env="ACTIONSHOT_NOTIFICATION_LOG",
            default=os.path.join(os.path.expanduser("~"), ".actionshot", "notifications.jsonl"),
        )
        _ensure_dir(os.path.dirname(path))
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")

    # -- helpers ----------------------------------------------------------

    def _default_channels(self) -> list[str]:
        """Determine channels from config / env."""
        channels: list[str] = []
        if self._cfg("webhook_url", env="ACTIONSHOT_WEBHOOK_URL"):
            channels.append("webhook")
        if self._cfg("smtp_host", env="ACTIONSHOT_SMTP_HOST"):
            channels.append("email")
        # File channel is always available as a fallback
        channels.append("file")
        return channels

    def _cfg(self, key: str, env: str | None = None, default: str | None = None) -> str | None:
        """Read a value from the config dict, then env vars, then default."""
        val = self.config.get(key)
        if val:
            return str(val)
        if env:
            val = os.environ.get(env)
            if val:
                return val
        return default


# ---------------------------------------------------------------------------
# 4. DashboardData
# ---------------------------------------------------------------------------

class DashboardData:
    """Generates data for a dashboard view of ActionShot executions."""

    def __init__(self, logs_root: str | None = None) -> None:
        self.logs_root = logs_root or _LOGS_ROOT
        self._tracker = ExecutionTracker(logs_root=self.logs_root)

    def summary(self) -> dict:
        """Overall system health: total workflows, avg success rate, active today."""
        workflows = self._tracker.get_all_workflows()
        total = len(workflows)

        rates = [w["success_rate"] for w in workflows if w["total_executions"] > 0]
        avg_rate = round(statistics.mean(rates), 2) if rates else 0.0

        today = datetime.utcnow().strftime("%Y-%m-%d")
        active_today = 0
        for w in workflows:
            last = w.get("last_execution")
            if last and isinstance(last, dict):
                ts = last.get("timestamp", "")
                if ts.startswith(today):
                    active_today += 1

        return {
            "total_workflows": total,
            "avg_success_rate": avg_rate,
            "active_today": active_today,
            "generated_at": _utcnow_iso(),
        }

    def workflow_details(self, workflow_id: str) -> dict:
        """Detailed view for one workflow, including recent failures."""
        stats = self._tracker.get_stats(workflow_id)
        failures = self._tracker.get_failures(workflow_id, last_n=5)
        return {
            **stats,
            "recent_failures": failures,
        }

    def recent_activity(self, limit: int = 50) -> list[dict]:
        """Return the last *limit* events across all workflows."""
        if not os.path.isdir(self.logs_root):
            return []

        all_events: list[dict] = []
        for name in os.listdir(self.logs_root):
            wf_dir = os.path.join(self.logs_root, name)
            if not os.path.isdir(wf_dir):
                continue
            for filename in os.listdir(wf_dir):
                if not filename.endswith(".jsonl"):
                    continue
                filepath = os.path.join(wf_dir, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                all_events.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue

        # Sort by timestamp descending, take the most recent
        all_events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return all_events[:limit]

    def export_csv(self, workflow_id: str, path: str) -> str:
        """Export execution history for *workflow_id* as CSV to *path*.

        Returns the absolute path of the written file.
        """
        events = self._tracker._read_events(workflow_id)
        executions = [e for e in events if e.get("event") == "execution_end"]

        _ensure_dir(os.path.dirname(os.path.abspath(path)))

        fieldnames = [
            "timestamp", "workflow_id", "status", "duration_ms",
        ]

        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for ex in executions:
                writer.writerow({
                    "timestamp": ex.get("timestamp", ""),
                    "workflow_id": ex.get("workflow_id", workflow_id),
                    "status": ex.get("status", ""),
                    "duration_ms": ex.get("duration_ms", ""),
                })

        return os.path.abspath(path)

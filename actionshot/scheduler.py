"""Scheduler - run automation scripts on a schedule."""

import json
import os
import subprocess
import sys
import time
import threading
from datetime import datetime, timedelta


SCHEDULE_FILE = os.path.join(os.path.expanduser("~"), ".actionshot", "schedules.json")


class Scheduler:
    """Manages scheduled automation tasks."""

    def __init__(self):
        self.schedules = []
        self._running = False
        self._thread = None
        self._load()

    def _load(self):
        if os.path.exists(SCHEDULE_FILE):
            with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
                self.schedules = json.load(f)

    def _save(self):
        os.makedirs(os.path.dirname(SCHEDULE_FILE), exist_ok=True)
        with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.schedules, f, indent=2, ensure_ascii=False)

    def add(self, name: str, script_path: str, cron_expr: str = None,
            interval_minutes: int = None, run_at: str = None) -> dict:
        """Add a scheduled task.

        Args:
            name: Human-readable name
            script_path: Path to the Python script to run
            cron_expr: Cron expression (simple: "HH:MM" for daily, "weekday HH:MM", etc.)
            interval_minutes: Run every N minutes
            run_at: One-time run at ISO datetime
        """
        schedule = {
            "id": len(self.schedules) + 1,
            "name": name,
            "script": os.path.abspath(script_path),
            "cron": cron_expr,
            "interval_minutes": interval_minutes,
            "run_at": run_at,
            "enabled": True,
            "last_run": None,
            "next_run": None,
            "created": datetime.now().isoformat(),
        }

        schedule["next_run"] = self._calc_next_run(schedule)
        self.schedules.append(schedule)
        self._save()

        print(f"  Schedule added: #{schedule['id']} '{name}'")
        print(f"  Script: {script_path}")
        print(f"  Next run: {schedule['next_run']}")

        return schedule

    def remove(self, schedule_id: int):
        self.schedules = [s for s in self.schedules if s["id"] != schedule_id]
        self._save()
        print(f"  Schedule #{schedule_id} removed.")

    def list_all(self) -> list[dict]:
        return list(self.schedules)

    def print_schedules(self):
        if not self.schedules:
            print("  No scheduled tasks.")
            return

        print(f"\n  {'ID':>4}  {'Name':<25}  {'Next Run':<22}  {'Enabled'}")
        print(f"  {'─'*4}  {'─'*25}  {'─'*22}  {'─'*7}")

        for s in self.schedules:
            enabled = "Yes" if s["enabled"] else "No"
            next_run = s.get("next_run", "—") or "—"
            print(f"  {s['id']:>4}  {s['name']:<25}  {str(next_run):<22}  {enabled}")
        print()

    def run_daemon(self):
        """Start the scheduler daemon that checks and runs tasks."""
        self._running = True
        print("  ActionShot Scheduler running. Press Ctrl+C to stop.")

        while self._running:
            now = datetime.now()

            for schedule in self.schedules:
                if not schedule["enabled"]:
                    continue

                next_run = schedule.get("next_run")
                if not next_run:
                    continue

                try:
                    next_dt = datetime.fromisoformat(next_run)
                except (ValueError, TypeError):
                    continue

                if now >= next_dt:
                    self._execute(schedule)
                    schedule["last_run"] = now.isoformat()
                    schedule["next_run"] = self._calc_next_run(schedule)
                    self._save()

            time.sleep(30)  # Check every 30 seconds

    def stop(self):
        self._running = False

    def _execute(self, schedule: dict):
        script = schedule["script"]
        name = schedule["name"]
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] Running: {name}")

        try:
            result = subprocess.run(
                [sys.executable, script],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode == 0:
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] Completed: {name}")
            else:
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] Failed: {name}")
                print(f"    stderr: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] Timeout: {name}")
        except Exception as e:
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] Error: {name} — {e}")

    def _calc_next_run(self, schedule: dict) -> str | None:
        now = datetime.now()

        if schedule.get("run_at"):
            try:
                return schedule["run_at"]
            except (ValueError, TypeError):
                return None

        if schedule.get("interval_minutes"):
            last = schedule.get("last_run")
            if last:
                try:
                    base = datetime.fromisoformat(last)
                except (ValueError, TypeError):
                    base = now
            else:
                base = now
            return (base + timedelta(minutes=schedule["interval_minutes"])).isoformat()

        if schedule.get("cron"):
            return self._parse_simple_cron(schedule["cron"], now)

        return None

    @staticmethod
    def _parse_simple_cron(expr: str, now: datetime) -> str | None:
        """Parse simple cron-like expressions.

        Formats:
            "14:30" — daily at 14:30
            "monday 09:00" — weekly on monday at 09:00
        """
        parts = expr.strip().lower().split()

        weekdays = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
        }

        if len(parts) == 1:
            # Daily at HH:MM
            try:
                hour, minute = map(int, parts[0].split(":"))
                target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if target <= now:
                    target += timedelta(days=1)
                return target.isoformat()
            except (ValueError, IndexError):
                return None

        elif len(parts) == 2 and parts[0] in weekdays:
            # Weekly
            try:
                target_day = weekdays[parts[0]]
                hour, minute = map(int, parts[1].split(":"))
                days_ahead = target_day - now.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                target = now + timedelta(days=days_ahead)
                target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
                return target.isoformat()
            except (ValueError, IndexError):
                return None

        return None

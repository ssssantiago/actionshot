"""Replay engine - reproduces recorded sessions with smart waits and retry."""

import json
import logging
import os
import time

import pyautogui

from .smart_wait import wait_for_screen_change
from .env import load_env


pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1

logger = logging.getLogger("actionshot.replay")


class Replayer:
    def __init__(self, session_path: str, speed: float = 1.0,
                 max_retries: int = 3, smart_wait: bool = True,
                 wait_timeout: float = 10.0, env_path: str = None):
        self.session_path = session_path
        self.speed = speed
        self.max_retries = max_retries
        self.smart_wait = smart_wait
        self.wait_timeout = wait_timeout
        self.steps = []
        self.env = {}
        self.variables = {}  # runtime variables extracted during replay
        self._load_session()

        # Load env if available
        env_file = env_path or os.path.join(session_path, ".env")
        if os.path.exists(env_file):
            self.env = load_env(env_file)
            logger.info(f"Loaded {len(self.env)} env vars from {env_file}")

    def _load_session(self):
        summary_path = os.path.join(self.session_path, "session_summary.json")
        if not os.path.exists(summary_path):
            raise FileNotFoundError(f"No session_summary.json found in {self.session_path}")

        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)

        for step_info in summary["steps"]:
            step_num = step_info["step"]
            meta_path = os.path.join(self.session_path, f"{step_num:03d}_metadata.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.steps.append(json.load(f))

    def run(self, dry_run: bool = False) -> dict:
        """Run the replay. Returns a report dict."""
        total = len(self.steps)
        report = {
            "session": self.session_path,
            "total_steps": total,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
        }

        print(f"\n  ActionShot Replay")
        print(f"  Session:     {self.session_path}")
        print(f"  Steps:       {total}")
        print(f"  Speed:       {self.speed}x")
        print(f"  Smart wait:  {'ON' if self.smart_wait else 'OFF'}")
        print(f"  Max retries: {self.max_retries}")
        print(f"  Dry run:     {dry_run}")
        if self.env:
            print(f"  Env vars:    {len(self.env)}")
        print()

        if not dry_run:
            print("  Starting in 3 seconds... (move mouse to top-left corner to abort)")
            time.sleep(3)

        prev_timestamp = None

        for i, step in enumerate(self.steps):
            # Delay between steps
            delay = self._calc_delay(prev_timestamp, step.get("timestamp"))
            if not dry_run and delay > 0:
                time.sleep(delay)

            action = step.get("action", "")
            desc = step.get("description", "")
            step_num = step.get("step", i + 1)

            if dry_run:
                print(f"  [{step_num:03d}/{total}] {desc}")
                prev_timestamp = step.get("timestamp")
                report["completed"] += 1
                continue

            # Execute with retry
            success = False
            last_error = None

            for attempt in range(1, self.max_retries + 1):
                try:
                    self._execute_step(step)
                    success = True
                    print(f"  [{step_num:03d}/{total}] OK  {desc}")
                    break
                except pyautogui.FailSafeException:
                    print(f"\n  ABORTED: Mouse moved to failsafe corner.")
                    report["errors"].append({"step": step_num, "error": "failsafe"})
                    return report
                except Exception as e:
                    last_error = str(e)
                    if attempt < self.max_retries:
                        print(f"  [{step_num:03d}/{total}] RETRY ({attempt}/{self.max_retries}): {e}")
                        time.sleep(0.5 * attempt)
                    else:
                        print(f"  [{step_num:03d}/{total}] FAIL  {desc} -- {e}")

            if success:
                report["completed"] += 1

                # Smart wait: wait for screen to stabilize after action
                if self.smart_wait and action.endswith("_click"):
                    from .capture import take_screenshot
                    ref = take_screenshot()
                    wait_for_screen_change(ref, timeout=self.wait_timeout, threshold=0.01)
            else:
                report["failed"] += 1
                report["errors"].append({"step": step_num, "error": last_error})

            prev_timestamp = step.get("timestamp")

        status = "complete" if report["failed"] == 0 else "completed with errors"
        print(f"\n  Replay {status}.")
        print(f"  OK: {report['completed']}  Failed: {report['failed']}\n")

        # Save report
        report_path = os.path.join(self.session_path, "replay_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        return report

    def _calc_delay(self, prev_ts, curr_ts) -> float:
        if not prev_ts or not curr_ts:
            return 0.3 / self.speed

        try:
            from datetime import datetime
            prev_t = datetime.fromisoformat(prev_ts)
            curr_t = datetime.fromisoformat(curr_ts)
            delay = (curr_t - prev_t).total_seconds() / self.speed
            return min(max(delay, 0.05), 5.0)
        except (ValueError, TypeError):
            return 0.3 / self.speed

    def _execute_step(self, step: dict):
        action = step.get("action", "")

        if action.endswith("_click"):
            self._do_click(step)
        elif action == "keypress":
            self._do_keypress(step)
        elif action == "scroll":
            self._do_scroll(step)
        elif action.startswith("drag"):
            self._do_drag(step)

    def _do_click(self, step: dict):
        pos = step.get("position", {})
        x, y = pos.get("x", 0), pos.get("y", 0)
        action = step.get("action", "left_click")

        button = "left"
        if "right" in action:
            button = "right"
        elif "middle" in action:
            button = "middle"

        pyautogui.click(x, y, button=button)

    def _do_keypress(self, step: dict):
        keys = step.get("keys", [])
        text = step.get("text", "")

        # Check for env variable substitution in text
        resolved_text = self._resolve_vars(text)

        # If text was substituted, type the resolved version
        if resolved_text != text:
            import pyperclip
            pyperclip.copy(resolved_text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)
            return

        for key in keys:
            if key.startswith("[") and key.endswith("]"):
                key_name = key[1:-1]
                mapped = _KEY_MAP.get(key_name, key_name)
                try:
                    pyautogui.press(mapped)
                except Exception:
                    pass
            else:
                pyautogui.typewrite(key, interval=0.02)

    def _do_scroll(self, step: dict):
        pos = step.get("position", {})
        x, y = pos.get("x", 0), pos.get("y", 0)
        dy = step.get("scroll_dy", 0)
        dx = step.get("scroll_dx", 0)
        pyautogui.scroll(dy, x=x, y=y)
        if dx:
            pyautogui.hscroll(dx, x=x, y=y)

    def _do_drag(self, step: dict):
        start = step.get("drag_start", {})
        end = step.get("drag_end", {})
        sx, sy = start.get("x", 0), start.get("y", 0)
        ex, ey = end.get("x", 0), end.get("y", 0)
        pyautogui.moveTo(sx, sy)
        time.sleep(0.1)
        pyautogui.drag(ex - sx, ey - sy, duration=0.5)

    def _resolve_vars(self, text: str) -> str:
        """Replace ${VAR_NAME} patterns with env values."""
        import re
        def _replace(match):
            var = match.group(1)
            return self.env.get(var, os.environ.get(var, match.group(0)))
        return re.sub(r'\$\{(\w+)\}', _replace, text)


_KEY_MAP = {
    "space": " ",
    "enter": "enter",
    "tab": "tab",
    "backspace": "backspace",
    "delete": "delete",
    "shift": "shift",
    "shift_r": "shiftright",
    "ctrl_l": "ctrlleft",
    "ctrl_r": "ctrlright",
    "alt_l": "altleft",
    "alt_r": "altright",
    "alt_gr": "altright",
    "caps_lock": "capslock",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "home": "home",
    "end": "end",
    "page_up": "pageup",
    "page_down": "pagedown",
    "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4",
    "f5": "f5", "f6": "f6", "f7": "f7", "f8": "f8",
    "f9": "f9", "f10": "f10", "f11": "f11", "f12": "f12",
}

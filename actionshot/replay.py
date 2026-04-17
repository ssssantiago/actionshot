"""Replay engine - reproduces recorded sessions."""

import json
import os
import time

import pyautogui


pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3


class Replayer:
    def __init__(self, session_path: str, speed: float = 1.0):
        self.session_path = session_path
        self.speed = speed
        self.steps = []
        self._load_session()

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

    def run(self, dry_run: bool = False):
        total = len(self.steps)
        print(f"\n  ActionShot Replay")
        print(f"  Session: {self.session_path}")
        print(f"  Steps:   {total}")
        print(f"  Speed:   {self.speed}x")
        print(f"  Dry run: {dry_run}")
        print()

        if not dry_run:
            print("  Starting in 3 seconds... (move mouse to top-left corner to abort)")
            time.sleep(3)

        prev_timestamp = None

        for i, step in enumerate(self.steps):
            # Calculate delay from timestamps
            if prev_timestamp and "timestamp" in step:
                try:
                    from datetime import datetime
                    prev_t = datetime.fromisoformat(prev_timestamp)
                    curr_t = datetime.fromisoformat(step["timestamp"])
                    delay = (curr_t - prev_t).total_seconds() / self.speed
                    delay = min(delay, 5.0)  # cap at 5 seconds
                    if not dry_run and delay > 0:
                        time.sleep(delay)
                except (ValueError, TypeError):
                    time.sleep(0.5 / self.speed)

            action = step.get("action", "")
            desc = step.get("description", "")
            print(f"  [{i + 1:03d}/{total}] {desc}")

            if dry_run:
                prev_timestamp = step.get("timestamp")
                continue

            self._execute_step(step)
            prev_timestamp = step.get("timestamp")

        print(f"\n  Replay complete. {total} steps executed.\n")

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
        for key in keys:
            if key.startswith("[") and key.endswith("]"):
                key_name = key[1:-1]
                special_map = {
                    "space": " ",
                    "enter": "enter",
                    "tab": "tab",
                    "backspace": "backspace",
                    "delete": "delete",
                    "shift": "shift",
                    "ctrl_l": "ctrlleft",
                    "ctrl_r": "ctrlright",
                    "alt_l": "altleft",
                    "alt_r": "altright",
                    "caps_lock": "capslock",
                    "up": "up",
                    "down": "down",
                    "left": "left",
                    "right": "right",
                    "home": "home",
                    "end": "end",
                    "page_up": "pageup",
                    "page_down": "pagedown",
                }
                mapped = special_map.get(key_name, key_name)
                try:
                    pyautogui.press(mapped)
                except Exception:
                    pass
            else:
                pyautogui.typewrite(key, interval=0.02)

    def _do_scroll(self, step: dict):
        pos = step.get("position", {})
        x, y = pos.get("x", 0), pos.get("y", 0)
        dx = step.get("scroll_dx", 0)
        dy = step.get("scroll_dy", 0)
        pyautogui.scroll(dy, x=x, y=y)
        if dx:
            pyautogui.hscroll(dx, x=x, y=y)

    def _do_drag(self, step: dict):
        start = step.get("drag_start", {})
        end = step.get("drag_end", {})
        sx, sy = start.get("x", 0), start.get("y", 0)
        ex, ey = end.get("x", 0), end.get("y", 0)
        duration = step.get("drag_duration", 0.5)
        pyautogui.moveTo(sx, sy)
        pyautogui.drag(ex - sx, ey - sy, duration=duration)

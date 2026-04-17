"""Script generator - converts recorded sessions into standalone Python scripts."""

import json
import os
from datetime import datetime


class ScriptGenerator:
    def __init__(self, session_path: str):
        self.session_path = session_path
        self.steps = []
        self._load_session()

    def _load_session(self):
        summary_path = os.path.join(self.session_path, "session_summary.json")
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)

        for step_info in summary["steps"]:
            step_num = step_info["step"]
            meta_path = os.path.join(self.session_path, f"{step_num:03d}_metadata.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.steps.append(json.load(f))

    def generate(self, output_path: str = None) -> str:
        if output_path is None:
            output_path = os.path.join(self.session_path, "replay_script.py")

        lines = [
            '"""',
            f"Auto-generated replay script by ActionShot",
            f"Source session: {os.path.basename(self.session_path)}",
            f"Generated at: {datetime.now().isoformat()}",
            f"Total steps: {len(self.steps)}",
            '"""',
            "",
            "import time",
            "import pyautogui",
            "",
            "pyautogui.FAILSAFE = True",
            "pyautogui.PAUSE = 0.3",
            "",
            "",
            "def run():",
            '    print("Starting replay in 3 seconds... (move mouse to top-left to abort)")',
            "    time.sleep(3)",
            "",
        ]

        prev_timestamp = None

        for i, step in enumerate(self.steps):
            action = step.get("action", "")
            desc = step.get("description", "")

            # Add delay between steps
            if prev_timestamp and "timestamp" in step:
                try:
                    prev_t = datetime.fromisoformat(prev_timestamp)
                    curr_t = datetime.fromisoformat(step["timestamp"])
                    delay = (curr_t - prev_t).total_seconds()
                    delay = min(delay, 5.0)
                    if delay > 0.1:
                        lines.append(f"    time.sleep({delay:.2f})")
                except (ValueError, TypeError):
                    lines.append("    time.sleep(0.5)")

            lines.append(f"    # Step {step.get('step', i+1)}: {desc}")

            if action.endswith("_click"):
                lines.extend(self._gen_click(step))
            elif action == "keypress":
                lines.extend(self._gen_keypress(step))
            elif action == "scroll":
                lines.extend(self._gen_scroll(step))
            elif action.startswith("drag"):
                lines.extend(self._gen_drag(step))

            lines.append("")
            prev_timestamp = step.get("timestamp")

        lines.extend([
            '    print("Replay complete.")',
            "",
            "",
            'if __name__ == "__main__":',
            "    run()",
            "",
        ])

        script = "\n".join(lines)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(script)

        print(f"  Script generated: {output_path}")
        return output_path

    def _gen_click(self, step: dict) -> list[str]:
        pos = step.get("position", {})
        x, y = pos.get("x", 0), pos.get("y", 0)
        action = step.get("action", "left_click")

        button = '"left"'
        if "right" in action:
            button = '"right"'
        elif "middle" in action:
            button = '"middle"'

        return [f"    pyautogui.click({x}, {y}, button={button})"]

    def _gen_keypress(self, step: dict) -> list[str]:
        keys = step.get("keys", [])
        text = step.get("text", "")
        result = []

        # Check if it's mostly regular text
        special_count = sum(1 for k in keys if k.startswith("["))
        if special_count == 0 and text:
            clean = text.replace("\\", "\\\\").replace('"', '\\"')
            result.append(f'    pyautogui.typewrite("{clean}", interval=0.03)')
        else:
            for key in keys:
                if key.startswith("[") and key.endswith("]"):
                    key_name = key[1:-1]
                    special_map = {
                        "space": "space",
                        "enter": "enter",
                        "tab": "tab",
                        "backspace": "backspace",
                        "shift": "shift",
                        "ctrl_l": "ctrlleft",
                        "alt_l": "altleft",
                    }
                    mapped = special_map.get(key_name, key_name)
                    result.append(f'    pyautogui.press("{mapped}")')
                else:
                    escaped = key.replace("\\", "\\\\").replace('"', '\\"')
                    result.append(f'    pyautogui.typewrite("{escaped}", interval=0.03)')

        return result

    def _gen_scroll(self, step: dict) -> list[str]:
        pos = step.get("position", {})
        x, y = pos.get("x", 0), pos.get("y", 0)
        dy = step.get("scroll_dy", 0)
        return [f"    pyautogui.scroll({dy}, x={x}, y={y})"]

    def _gen_drag(self, step: dict) -> list[str]:
        start = step.get("drag_start", {})
        end = step.get("drag_end", {})
        sx, sy = start.get("x", 0), start.get("y", 0)
        ex, ey = end.get("x", 0), end.get("y", 0)
        dur = step.get("drag_duration", 0.5)
        return [
            f"    pyautogui.moveTo({sx}, {sy})",
            f"    pyautogui.drag({ex - sx}, {ey - sy}, duration={dur:.2f})",
        ]

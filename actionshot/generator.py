"""Script generator - converts sessions into robust, production-grade RPA scripts."""

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

        # Extract unique windows, elements, and texts for variables
        windows = set()
        elements = set()
        typed_texts = []

        for step in self.steps:
            win = step.get("window", {}).get("title", "")
            if win:
                windows.add(win)
            elem = step.get("element", {})
            if elem and elem.get("name"):
                elements.add(elem["name"])
            if step.get("text"):
                typed_texts.append(step["text"])

        lines = self._header()
        lines += self._imports()
        lines += self._env_section(typed_texts)
        lines += self._config_section()
        lines += self._helper_functions()
        lines += self._main_function()
        lines += self._step_functions()
        lines += self._runner()

        script = "\n".join(lines)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(script)

        # Generate companion .env template
        env_path = os.path.join(os.path.dirname(output_path), ".env.template")
        self._gen_env_template(env_path, typed_texts)

        print(f"  Script generated: {output_path}")
        print(f"  Env template:     {env_path}")
        return output_path

    def _header(self):
        return [
            '"""',
            f'ActionShot RPA Script',
            f'Source: {os.path.basename(self.session_path)}',
            f'Generated: {datetime.now().isoformat()}',
            f'Steps: {len(self.steps)}',
            '',
            'Usage:',
            '  1. Copy .env.template to .env and fill in values',
            '  2. pip install pyautogui pyperclip python-dotenv',
            '  3. python replay_script.py',
            '',
            'Environment variables:',
            '  ACTIONSHOT_SPEED    - Playback speed multiplier (default: 1.0)',
            '  ACTIONSHOT_RETRIES  - Max retries per step (default: 3)',
            '  ACTIONSHOT_DRY_RUN  - Set to "1" for dry run',
            '"""',
            '',
        ]

    def _imports(self):
        return [
            'import logging',
            'import os',
            'import sys',
            'import time',
            'import traceback',
            '',
            'import pyautogui',
            '',
            'try:',
            '    import pyperclip',
            '    HAS_PYPERCLIP = True',
            'except ImportError:',
            '    HAS_PYPERCLIP = False',
            '',
            'try:',
            '    from dotenv import load_dotenv',
            '    load_dotenv()',
            'except ImportError:',
            '    pass',
            '',
            '',
        ]

    def _env_section(self, typed_texts):
        lines = [
            '# ── Configuration from environment ────────────────────────────────',
            '',
            'SPEED = float(os.environ.get("ACTIONSHOT_SPEED", "1.0"))',
            'MAX_RETRIES = int(os.environ.get("ACTIONSHOT_RETRIES", "3"))',
            'DRY_RUN = os.environ.get("ACTIONSHOT_DRY_RUN", "0") == "1"',
            'WAIT_TIMEOUT = float(os.environ.get("ACTIONSHOT_WAIT_TIMEOUT", "10.0"))',
            '',
        ]

        # Extract typed texts that look like credentials/data
        for i, text in enumerate(typed_texts):
            safe = text.replace("[space]", " ").replace("[enter]", "")
            if len(safe) > 3:
                var_name = f'INPUT_TEXT_{i + 1}'
                escaped = safe.replace('"', '\\"').replace('\\', '\\\\')
                lines.append(f'{var_name} = os.environ.get("{var_name}", "{escaped}")')

        lines += ['', '']
        return lines

    def _config_section(self):
        return [
            '# ── pyautogui config ──────────────────────────────────────────────',
            '',
            'pyautogui.FAILSAFE = True',
            'pyautogui.PAUSE = 0.1',
            '',
            'logging.basicConfig(',
            '    level=logging.INFO,',
            '    format="%(asctime)s [%(levelname)s] %(message)s",',
            '    datefmt="%H:%M:%S",',
            ')',
            'log = logging.getLogger("actionshot")',
            '',
            '',
        ]

    def _helper_functions(self):
        return [
            '# ── Helpers ───────────────────────────────────────────────────────',
            '',
            'def safe_click(x, y, button="left", retries=MAX_RETRIES):',
            '    """Click with retry and logging."""',
            '    for attempt in range(1, retries + 1):',
            '        try:',
            '            pyautogui.click(x, y, button=button)',
            '            return True',
            '        except pyautogui.FailSafeException:',
            '            log.error("Failsafe triggered -- aborting")',
            '            sys.exit(1)',
            '        except Exception as e:',
            '            if attempt < retries:',
            '                log.warning(f"Click ({x},{y}) attempt {attempt} failed: {e}")',
            '                time.sleep(0.5 * attempt)',
            '            else:',
            '                log.error(f"Click ({x},{y}) failed after {retries} attempts: {e}")',
            '                raise',
            '    return False',
            '',
            '',
            'def safe_type(text, interval=0.03):',
            '    """Type text, using clipboard paste for non-ASCII."""',
            '    try:',
            '        # Check for non-ASCII',
            '        text.encode("ascii")',
            '        pyautogui.typewrite(text, interval=interval)',
            '    except UnicodeEncodeError:',
            '        if HAS_PYPERCLIP:',
            '            pyperclip.copy(text)',
            '            pyautogui.hotkey("ctrl", "v")',
            '            time.sleep(0.1)',
            '        else:',
            '            log.warning("Non-ASCII text but pyperclip not available")',
            '            pyautogui.typewrite(text, interval=interval)',
            '',
            '',
            'def wait_and_click(x, y, button="left", timeout=WAIT_TIMEOUT):',
            '    """Wait briefly for screen to stabilize, then click."""',
            '    time.sleep(0.2 / SPEED)',
            '    safe_click(x, y, button=button)',
            '',
            '',
            'def delay(seconds):',
            '    """Speed-adjusted delay."""',
            '    time.sleep(max(seconds / SPEED, 0.05))',
            '',
            '',
        ]

    def _main_function(self):
        lines = [
            '# ── Main workflow ─────────────────────────────────────────────────',
            '',
            'def run():',
            '    """Execute the recorded workflow."""',
            '    log.info(f"ActionShot RPA starting (speed={SPEED}x, retries={MAX_RETRIES})")',
            '',
            '    if DRY_RUN:',
            '        log.info("DRY RUN mode -- no actions will be executed")',
            '',
            '    log.info("Starting in 3 seconds... (move mouse to top-left to abort)")',
            '    if not DRY_RUN:',
            '        time.sleep(3)',
            '',
            '    results = {"ok": 0, "fail": 0, "errors": []}',
            '',
        ]

        text_idx = 0  # track which INPUT_TEXT_ var to use

        for i, step in enumerate(self.steps):
            action = step.get("action", "")
            desc = step.get("description", "").replace('"', '\\"')
            step_num = step.get("step", i + 1)

            # Delay
            lines.append(f'    # Step {step_num}: {desc}')

            if i > 0:
                lines.append(f'    delay(0.3)')

            lines.append(f'    log.info("Step {step_num}: {desc}")')

            if action.endswith("_click"):
                pos = step.get("position", {})
                x, y = pos.get("x", 0), pos.get("y", 0)
                button = '"left"'
                if "right" in action:
                    button = '"right"'
                elif "middle" in action:
                    button = '"middle"'

                lines.append(f'    if not DRY_RUN:')
                lines.append(f'        try:')
                lines.append(f'            wait_and_click({x}, {y}, button={button})')
                lines.append(f'            results["ok"] += 1')
                lines.append(f'        except Exception as e:')
                lines.append(f'            log.error(f"Step {step_num} failed: {{e}}")')
                lines.append(f'            results["fail"] += 1')
                lines.append(f'            results["errors"].append({{"step": {step_num}, "error": str(e)}})')

            elif action == "keypress":
                text = step.get("text", "")
                keys = step.get("keys", [])

                # Check if it's simple text or mixed with special keys
                special_keys = [k for k in keys if k.startswith("[")]

                lines.append(f'    if not DRY_RUN:')
                lines.append(f'        try:')

                if not special_keys and text:
                    # Pure text -- use env var
                    var_name = f'INPUT_TEXT_{text_idx + 1}'
                    lines.append(f'            safe_type({var_name})')
                    text_idx += 1
                else:
                    for key in keys:
                        if key.startswith("[") and key.endswith("]"):
                            key_name = key[1:-1]
                            mapped = _KEY_MAP.get(key_name, key_name)
                            lines.append(f'            pyautogui.press("{mapped}")')
                        else:
                            escaped = key.replace("\\", "\\\\").replace('"', '\\"')
                            lines.append(f'            pyautogui.typewrite("{escaped}", interval=0.03)')

                lines.append(f'            results["ok"] += 1')
                lines.append(f'        except Exception as e:')
                lines.append(f'            log.error(f"Step {step_num} failed: {{e}}")')
                lines.append(f'            results["fail"] += 1')

            elif action == "scroll":
                pos = step.get("position", {})
                x, y = pos.get("x", 0), pos.get("y", 0)
                dy = step.get("scroll_dy", 0)

                lines.append(f'    if not DRY_RUN:')
                lines.append(f'        pyautogui.scroll({dy}, x={x}, y={y})')
                lines.append(f'        results["ok"] += 1')

            elif action.startswith("drag"):
                start = step.get("drag_start", {})
                end = step.get("drag_end", {})
                sx, sy = start.get("x", 0), start.get("y", 0)
                ex, ey = end.get("x", 0), end.get("y", 0)

                lines.append(f'    if not DRY_RUN:')
                lines.append(f'        pyautogui.moveTo({sx}, {sy})')
                lines.append(f'        time.sleep(0.1)')
                lines.append(f'        pyautogui.drag({ex - sx}, {ey - sy}, duration=0.5)')
                lines.append(f'        results["ok"] += 1')

            lines.append('')

        lines += [
            '    # Report',
            '    log.info(f"Done. OK: {results[\'ok\']}  Failed: {results[\'fail\']}")',
            '    if results["errors"]:',
            '        for err in results["errors"]:',
            '            log.error(f"  Step {err[\'step\']}: {err[\'error\']}")',
            '',
            '    return results',
            '',
            '',
        ]

        return lines

    def _step_functions(self):
        return []

    def _runner(self):
        return [
            'if __name__ == "__main__":',
            '    try:',
            '        result = run()',
            '        sys.exit(0 if result["fail"] == 0 else 1)',
            '    except KeyboardInterrupt:',
            '        log.info("Interrupted by user")',
            '        sys.exit(130)',
            '    except Exception:',
            '        log.error(traceback.format_exc())',
            '        sys.exit(1)',
            '',
        ]

    def _gen_env_template(self, path: str, typed_texts: list):
        """Generate a .env.template with all configurable variables."""
        lines = [
            "# ActionShot RPA Environment Variables",
            "# Copy this to .env and fill in your values",
            "",
            "# Playback speed (1.0 = real speed, 2.0 = 2x faster)",
            "ACTIONSHOT_SPEED=1.0",
            "",
            "# Max retries per failed step",
            "ACTIONSHOT_RETRIES=3",
            "",
            "# Set to 1 for dry run (prints steps without executing)",
            "ACTIONSHOT_DRY_RUN=0",
            "",
            "# Max seconds to wait for screen changes",
            "ACTIONSHOT_WAIT_TIMEOUT=10.0",
            "",
            "# ── Input values (customize these) ──────────────────────────────",
            "",
        ]

        for i, text in enumerate(typed_texts):
            safe = text.replace("[space]", " ").replace("[enter]", "")
            if len(safe) > 3:
                lines.append(f"# Original: {safe[:60]}")
                lines.append(f"INPUT_TEXT_{i + 1}={safe}")
                lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


_KEY_MAP = {
    "space": "space",
    "enter": "enter",
    "tab": "tab",
    "backspace": "backspace",
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

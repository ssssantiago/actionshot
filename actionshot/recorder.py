"""Main recorder - listens to interactions and orchestrates capture."""

import json
import threading
from datetime import datetime

from pynput import mouse, keyboard

from .session import Session
from .capture import take_screenshot, annotate_click, annotate_keypress, annotate_scroll, annotate_drag
from .metadata import get_window_info


class Recorder:
    def __init__(self, output_dir="recordings"):
        self.output_dir = output_dir
        self.session = None
        self.running = False
        self._key_buffer = []
        self._key_timer = None
        self._key_lock = threading.Lock()
        self._KEY_FLUSH_DELAY = 0.8

        # Drag tracking
        self._drag_start = None
        self._drag_button = None
        self._is_dragging = False
        self._DRAG_THRESHOLD = 10  # pixels to count as drag

    def start(self):
        self.session = Session(self.output_dir)
        self.running = True
        print(f"\n  ActionShot recording started")
        print(f"  Session: {self.session.name}")
        print(f"  Output:  {self.session.path}")
        print(f"\n  Press ESC to stop recording.\n")

        self._mouse_listener = mouse.Listener(
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._kb_listener = keyboard.Listener(on_press=self._on_key_press)

        self._mouse_listener.start()
        self._kb_listener.start()

        try:
            self._kb_listener.join()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        if not self.running:
            return
        self.running = False
        self._flush_keys()
        self._mouse_listener.stop()
        self._kb_listener.stop()
        total = self.session.step_count
        print(f"\n  Recording stopped. {total} steps captured.")
        print(f"  Saved to: {self.session.path}\n")

    # ── Mouse clicks & drags ──────────────────────────────────────────

    def _on_click(self, x, y, button, pressed):
        if not self.running:
            return

        if pressed:
            # Start potential drag
            self._drag_start = (x, y)
            self._drag_button = button
            self._is_dragging = False
        else:
            # Button released
            if self._drag_start:
                sx, sy = self._drag_start
                dist = ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5
                if dist > self._DRAG_THRESHOLD:
                    self._record_drag(sx, sy, x, y, button)
                else:
                    self._record_click(x, y, button)
                self._drag_start = None
                self._drag_button = None

    def _record_click(self, x, y, button):
        self._flush_keys()

        step_num = self.session.next_step()
        timestamp = datetime.now().isoformat()
        action = f"{button.name}_click"

        screenshot = take_screenshot()
        annotated = annotate_click(screenshot, x, y, action)

        window_info = get_window_info(x, y)
        element = window_info.get("element") or {}
        element_name = element.get("name", "unknown")
        element_type = element.get("control_type", "element")
        description = f"Clicked {element_type} '{element_name}' in '{window_info.get('window_title', 'unknown')}'"

        img_path = self.session.step_path(step_num, f"{action}.png")
        annotated.save(img_path)

        meta = {
            "step": step_num,
            "timestamp": timestamp,
            "action": action,
            "position": {"x": x, "y": y},
            "description": description,
            "window": {
                "title": window_info.get("window_title", ""),
                "class": window_info.get("window_class", ""),
                "process": window_info.get("process_name", ""),
            },
            "element": element,
            "screenshot": f"{step_num:03d}_{action}.png",
        }

        meta_path = self.session.step_path(step_num, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        self.session.add_step({
            "step": step_num,
            "action": action,
            "description": description,
            "timestamp": timestamp,
        })

        print(f"  [{step_num:03d}] {description}")

    def _record_drag(self, sx, sy, ex, ey, button):
        self._flush_keys()

        step_num = self.session.next_step()
        timestamp = datetime.now().isoformat()
        action = f"drag_{button.name}"

        screenshot = take_screenshot()
        annotated = annotate_drag(screenshot, sx, sy, ex, ey)

        window_info = get_window_info(sx, sy)
        description = f"Dragged from ({sx},{sy}) to ({ex},{ey}) in '{window_info.get('window_title', 'unknown')}'"

        img_path = self.session.step_path(step_num, f"{action}.png")
        annotated.save(img_path)

        meta = {
            "step": step_num,
            "timestamp": timestamp,
            "action": action,
            "drag_start": {"x": sx, "y": sy},
            "drag_end": {"x": ex, "y": ey},
            "description": description,
            "window": {
                "title": window_info.get("window_title", ""),
                "class": window_info.get("window_class", ""),
                "process": window_info.get("process_name", ""),
            },
            "screenshot": f"{step_num:03d}_{action}.png",
        }

        meta_path = self.session.step_path(step_num, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        self.session.add_step({
            "step": step_num,
            "action": action,
            "description": description,
            "timestamp": timestamp,
        })

        print(f"  [{step_num:03d}] {description}")

    # ── Scroll ────────────────────────────────────────────────────────

    def _on_scroll(self, x, y, dx, dy):
        if not self.running:
            return

        self._flush_keys()

        step_num = self.session.next_step()
        timestamp = datetime.now().isoformat()
        action = "scroll"

        direction = "down" if dy < 0 else "up"
        screenshot = take_screenshot()
        annotated = annotate_scroll(screenshot, x, y, direction)

        window_info = get_window_info(x, y)
        description = f"Scrolled {direction} (dx={dx}, dy={dy}) at ({x},{y}) in '{window_info.get('window_title', 'unknown')}'"

        img_path = self.session.step_path(step_num, f"{action}.png")
        annotated.save(img_path)

        meta = {
            "step": step_num,
            "timestamp": timestamp,
            "action": action,
            "position": {"x": x, "y": y},
            "scroll_dx": dx,
            "scroll_dy": dy,
            "direction": direction,
            "description": description,
            "window": {
                "title": window_info.get("window_title", ""),
                "class": window_info.get("window_class", ""),
                "process": window_info.get("process_name", ""),
            },
            "screenshot": f"{step_num:03d}_{action}.png",
        }

        meta_path = self.session.step_path(step_num, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        self.session.add_step({
            "step": step_num,
            "action": action,
            "description": description,
            "timestamp": timestamp,
        })

        print(f"  [{step_num:03d}] {description}")

    # ── Keyboard ──────────────────────────────────────────────────────

    def _on_key_press(self, key):
        if not self.running:
            return

        if key == keyboard.Key.esc:
            self.stop()
            return False

        with self._key_lock:
            if hasattr(key, "char") and key.char:
                self._key_buffer.append(key.char)
            else:
                self._key_buffer.append(f"[{key.name}]")

            if self._key_timer:
                self._key_timer.cancel()
            self._key_timer = threading.Timer(self._KEY_FLUSH_DELAY, self._flush_keys)
            self._key_timer.start()

    def _flush_keys(self):
        with self._key_lock:
            if not self._key_buffer:
                return

            keys = list(self._key_buffer)
            self._key_buffer.clear()

            if self._key_timer:
                self._key_timer.cancel()
                self._key_timer = None

        if not self.running and not keys:
            return

        step_num = self.session.next_step()
        timestamp = datetime.now().isoformat()

        key_text = "".join(keys)
        display_text = key_text.replace("[space]", " ").replace("[enter]", "\u23ce")

        screenshot = take_screenshot()
        annotated = annotate_keypress(screenshot, display_text[:60])

        description = f"Typed: '{display_text[:80]}'"

        img_path = self.session.step_path(step_num, "keypress.png")
        annotated.save(img_path)

        meta = {
            "step": step_num,
            "timestamp": timestamp,
            "action": "keypress",
            "keys": keys,
            "text": key_text,
            "description": description,
            "screenshot": f"{step_num:03d}_keypress.png",
        }

        meta_path = self.session.step_path(step_num, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        self.session.add_step({
            "step": step_num,
            "action": "keypress",
            "description": description,
            "timestamp": timestamp,
        })

        print(f"  [{step_num:03d}] {description}")

"""Main recorder - listens to interactions and orchestrates capture via event queue."""

import ctypes
import ctypes.wintypes
import json
import os
import queue
import subprocess
import threading
import time
from datetime import datetime

from pynput import mouse, keyboard

from .session import Session
from .capture import take_screenshot, annotate_click, annotate_keypress, annotate_scroll, annotate_drag
from .metadata import get_window_info
from .ocr import extract_text_around, HAS_TESSERACT
from .monitor import MonitorInfo
from .video import VideoRecorder


def _get_foreground_process_name() -> str:
    """Return the executable name (e.g. 'chrome.exe') of the foreground window."""
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = ctypes.wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
    )
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(260)
        size = ctypes.wintypes.DWORD(260)
        ctypes.windll.kernel32.QueryFullProcessImageNameW(
            handle, 0, buf, ctypes.byref(size)
        )
        return os.path.basename(buf.value)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _normalize_app_name(process_name: str) -> str:
    """Derive a short app name from a process executable name."""
    if not process_name:
        return ""
    name = process_name.lower().replace(".exe", "")
    _MAP = {
        "chrome": "chrome", "msedge": "edge", "brave": "brave",
        "firefox": "firefox", "excel": "excel", "winword": "word",
        "outlook": "outlook", "powerpnt": "powerpoint", "notepad": "notepad",
        "code": "vscode", "explorer": "explorer",
    }
    return _MAP.get(name, name)


class Recorder:
    def __init__(self, output_dir="recordings", scope=None, enable_video=False,
                 enable_ocr=True, video_fps=10, image_format="jpeg",
                 image_quality=85):
        self.output_dir = output_dir
        self.scope = scope  # WorkflowScope or None (None = legacy mode, capture everything as in_scope)
        self.session = None
        self.running = False
        self.enable_video = enable_video
        self.enable_ocr = enable_ocr and HAS_TESSERACT
        self.video_fps = video_fps
        self.image_format = image_format
        self.image_quality = image_quality

        self._key_buffer = []
        self._key_timer = None
        self._key_lock = threading.Lock()
        self._KEY_FLUSH_DELAY = 0.8

        # Drag tracking
        self._drag_start = None
        self._drag_button = None
        self._press_pos = None
        self._DRAG_THRESHOLD = 10

        # Scroll debounce
        self._scroll_buffer = None
        self._scroll_timer = None
        self._scroll_lock = threading.Lock()
        self._SCROLL_FLUSH_DELAY = 0.3

        # Click rate limit
        self._last_click_time = 0
        self._MIN_CLICK_INTERVAL = 0.15  # 150ms between clicks

        # Multi-monitor
        self._monitor_info = MonitorInfo()

        # Video recorder
        self._video_recorder = None

        # Event queue — pynput callbacks push events, worker thread processes them
        self._event_queue = queue.Queue(maxsize=500)
        self._worker_thread = None

        # Hotkeys (integrated into recorder's keyboard listener, not separate)
        self._hotkey_pressed = set()
        self._hotkey_combos = {
            "toggle": {keyboard.Key.shift, keyboard.Key.cmd, keyboard.KeyCode.from_char("r")},
            "pause": {keyboard.Key.shift, keyboard.Key.cmd, keyboard.KeyCode.from_char("p")},
        }

        self._paused = False

    # ── Scope helpers ──────────────────────────────────────────────

    def _resolve_scope(self) -> tuple:
        """Return (process_name, app_name, in_scope) for the current foreground window.

        When *scope* is ``None`` (legacy mode), ``in_scope`` is always ``True``.
        Returns ``None`` instead of a tuple when the event should be skipped
        entirely (blacklisted process).
        """
        process_name = _get_foreground_process_name()
        app_name = _normalize_app_name(process_name)
        if self.scope is not None:
            if self.scope.is_blacklisted(process_name):
                return None
            in_scope = self.scope.is_in_scope(process_name)
        else:
            in_scope = True
        return process_name, app_name, in_scope

    def prepare_scope(self):
        """Prepare declared apps before recording starts."""
        if not self.scope:
            return True

        for app in self.scope.declared_apps:
            if app == "chrome":
                if not self._prepare_chrome():
                    return False
            elif app in ("excel", "word", "outlook"):
                self._prepare_office_app(app)
        return True

    def _prepare_chrome(self) -> bool:
        """Ensure Chrome is running with CDP enabled on port 9222."""
        try:
            from .cdp import ChromeCDP
            cdp = ChromeCDP()
            if cdp.is_available():
                # CDP already reachable -- optionally navigate
                if self.scope and getattr(self.scope, "chrome_url", None):
                    cdp.connect()
                    try:
                        cdp.execute("Page.navigate", {"url": self.scope.chrome_url})
                    finally:
                        cdp.disconnect()
                return True
        except Exception:
            pass

        # Try launching Chrome with remote debugging
        try:
            chrome_paths = [
                os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            ]
            chrome_exe = None
            for p in chrome_paths:
                if os.path.isfile(p):
                    chrome_exe = p
                    break
            if not chrome_exe:
                print("  [scope] Chrome executable not found")
                return False

            cmd = [chrome_exe, "--remote-debugging-port=9222"]
            if self.scope and getattr(self.scope, "chrome_url", None):
                cmd.append(self.scope.chrome_url)

            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)  # Give Chrome time to start

            from .cdp import ChromeCDP
            cdp = ChromeCDP()
            if cdp.is_available():
                print("  [scope] Chrome launched with CDP on port 9222")
                return True
            else:
                print("  [scope] Chrome launched but CDP not available")
                return False
        except Exception as e:
            print(f"  [scope] Failed to launch Chrome: {e}")
            return False

    def _prepare_office_app(self, app: str):
        """Open an Office application, optionally with a file from scope."""
        exe_map = {
            "excel": "excel.exe",
            "word": "winword.exe",
            "outlook": "outlook.exe",
        }
        exe = exe_map.get(app)
        if not exe:
            return
        try:
            cmd = [exe]
            # If scope has a file for this app, pass it
            app_file = getattr(self.scope, f"{app}_file", None) if self.scope else None
            if app_file:
                cmd.append(app_file)
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"  [scope] Launched {app}")
        except Exception as e:
            print(f"  [scope] Failed to launch {app}: {e}")

    # ── Start / Stop ─────────────────────────────────────────────

    def start(self):
        self.session = Session(self.output_dir)
        self.running = True
        self._paused = False

        mon_count = self._monitor_info.count()
        scope_label = "ALL (legacy)" if self.scope is None else ", ".join(self.scope.declared_apps)
        print(f"\n  ActionShot recording started")
        print(f"  Session: {self.session.name}")
        print(f"  Output:  {self.session.path}")
        print(f"  Monitors: {mon_count}")
        print(f"  Scope: {scope_label}")
        print(f"  Video: {'ON' if self.enable_video else 'OFF'}")
        print(f"  OCR: {'ON' if self.enable_ocr else 'OFF'}")
        print(f"  Format: {self.image_format.upper()} (q={self.image_quality})")
        print(f"\n  Hotkeys: Win+Shift+R toggle | Win+Shift+P pause | ESC stop\n")

        # Start video recording
        if self.enable_video:
            import os
            video_path = os.path.join(self.session.path, "recording.mp4")
            self._video_recorder = VideoRecorder(video_path, fps=self.video_fps)
            self._video_recorder.start()

        # Start event processing worker
        self._worker_thread = threading.Thread(target=self._process_events, daemon=True)
        self._worker_thread.start()

        # Single keyboard listener handles both hotkeys and key recording
        self._mouse_listener = mouse.Listener(
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._kb_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )

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

        # Flush pending buffers
        self._flush_keys()
        self._flush_scroll()

        # Signal worker to stop
        self._event_queue.put(None)

        self._mouse_listener.stop()
        self._kb_listener.stop()

        if self._worker_thread:
            self._worker_thread.join(timeout=5)

        if self._video_recorder:
            self._video_recorder.stop()
            print(f"  Video saved: recording.mp4")

        total = self.session.step_count
        print(f"\n  Recording stopped. {total} steps captured.")
        print(f"  Saved to: {self.session.path}\n")

    # ── Event queue worker ────────────────────────────────────────────

    def _process_events(self):
        """Worker thread that processes events from the queue."""
        while True:
            event = self._event_queue.get()
            if event is None:
                break

            try:
                event_type = event["type"]
                if event_type == "click":
                    self._process_click(event)
                elif event_type == "drag":
                    self._process_drag(event)
                elif event_type == "scroll":
                    self._process_scroll(event)
                elif event_type == "keypress":
                    self._process_keypress(event)
            except Exception as e:
                print(f"  [error] Failed to process event: {e}")

    # ── pynput callbacks (lightweight — just enqueue) ─────────────────

    def _on_click(self, x, y, button, pressed):
        if not self.running or self._paused:
            return

        if pressed:
            self._drag_start = (x, y)
            self._drag_button = button
            self._press_pos = (x, y)
        else:
            if self._drag_start:
                # Resolve scope once for the release event
                scope_info = self._resolve_scope()
                if scope_info is None:
                    # Blacklisted — discard
                    self._drag_start = None
                    self._press_pos = None
                    return
                process_name, app_name, in_scope = scope_info

                sx, sy = self._drag_start
                dist = ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5
                if dist > self._DRAG_THRESHOLD:
                    self._event_queue.put({
                        "type": "drag",
                        "sx": sx, "sy": sy, "ex": x, "ey": y,
                        "button": button,
                        "timestamp": datetime.now().isoformat(),
                        "process_name": process_name,
                        "app_name": app_name,
                        "in_scope": in_scope,
                    })
                else:
                    # Rate limit clicks
                    now = time.monotonic()
                    if now - self._last_click_time < self._MIN_CLICK_INTERVAL:
                        self._drag_start = None
                        self._press_pos = None
                        return
                    self._last_click_time = now

                    px, py = self._press_pos
                    self._event_queue.put({
                        "type": "click",
                        "x": px, "y": py,
                        "button": button,
                        "timestamp": datetime.now().isoformat(),
                        "process_name": process_name,
                        "app_name": app_name,
                        "in_scope": in_scope,
                    })
                self._drag_start = None
                self._press_pos = None

    def _on_scroll(self, x, y, dx, dy):
        if not self.running or self._paused:
            return

        # Scope check — resolve once for the first scroll in a batch
        scope_info = self._resolve_scope()
        if scope_info is None:
            return  # blacklisted
        process_name, app_name, in_scope = scope_info

        with self._scroll_lock:
            if self._scroll_buffer is None:
                self._scroll_buffer = {
                    "x": x, "y": y, "dx": dx, "dy": dy,
                    "process_name": process_name,
                    "app_name": app_name,
                    "in_scope": in_scope,
                }
            else:
                self._scroll_buffer["dx"] += dx
                self._scroll_buffer["dy"] += dy

            if self._scroll_timer:
                self._scroll_timer.cancel()
            self._scroll_timer = threading.Timer(self._SCROLL_FLUSH_DELAY, self._flush_scroll)
            self._scroll_timer.start()

    def _on_key_press(self, key):
        if not self.running:
            return

        if key == keyboard.Key.esc:
            self.stop()
            return False

        # Track hotkey state
        self._hotkey_pressed.add(key)
        if self._check_hotkeys():
            return

        if self._paused:
            return

        # Scope check
        scope_info = self._resolve_scope()
        if scope_info is None:
            return  # blacklisted

        process_name, app_name, in_scope = scope_info

        with self._key_lock:
            if hasattr(key, "char") and key.char:
                self._key_buffer.append(key.char)
            else:
                self._key_buffer.append(f"[{key.name}]")

            # Store latest scope info for when the buffer is flushed
            self._key_scope_info = (process_name, app_name, in_scope)

            if self._key_timer:
                self._key_timer.cancel()
            self._key_timer = threading.Timer(self._KEY_FLUSH_DELAY, self._flush_keys)
            self._key_timer.start()

    def _on_key_release(self, key):
        self._hotkey_pressed.discard(key)

    def _check_hotkeys(self) -> bool:
        """Check if a hotkey combo is pressed. Returns True if consumed."""
        if self._hotkey_combos["toggle"].issubset(self._hotkey_pressed):
            self._hotkey_pressed.clear()
            self.stop()
            return True
        if self._hotkey_combos["pause"].issubset(self._hotkey_pressed):
            self._hotkey_pressed.clear()
            self._paused = not self._paused
            state = "PAUSED" if self._paused else "RESUMED"
            print(f"  Recording {state}")
            if self._video_recorder:
                if self._paused:
                    self._video_recorder.pause()
                else:
                    self._video_recorder.resume()
            return True
        return False

    # ── Flush buffers into event queue ────────────────────────────────

    def _flush_keys(self):
        with self._key_lock:
            if not self._key_buffer:
                return
            keys = list(self._key_buffer)
            self._key_buffer.clear()
            scope_info = getattr(self, "_key_scope_info", ("", "", True))
            if self._key_timer:
                self._key_timer.cancel()
                self._key_timer = None

        if not keys:
            return

        process_name, app_name, in_scope = scope_info
        self._event_queue.put({
            "type": "keypress",
            "keys": keys,
            "timestamp": datetime.now().isoformat(),
            "process_name": process_name,
            "app_name": app_name,
            "in_scope": in_scope,
        })

    def _flush_scroll(self):
        with self._scroll_lock:
            if not self._scroll_buffer:
                return
            data = dict(self._scroll_buffer)
            self._scroll_buffer = None
            if self._scroll_timer:
                self._scroll_timer.cancel()
                self._scroll_timer = None

        self._event_queue.put({
            "type": "scroll",
            "x": data["x"], "y": data["y"],
            "dx": data["dx"], "dy": data["dy"],
            "timestamp": datetime.now().isoformat(),
            "process_name": data.get("process_name", ""),
            "app_name": data.get("app_name", ""),
            "in_scope": data.get("in_scope", True),
        })

    # ── Event processors (run on worker thread) ───────────────────────

    def _save_image(self, image, path):
        """Save image in configured format with compression."""
        if self.image_format == "jpeg":
            # Convert to RGB (JPEG doesn't support alpha)
            if image.mode == "RGBA":
                image = image.convert("RGB")
            image.save(path, "JPEG", quality=self.image_quality, optimize=True)
        else:
            image.save(path, "PNG", optimize=True)

    def _get_image_ext(self):
        return "jpg" if self.image_format == "jpeg" else "png"

    def _enqueue_ocr(self, screenshot, meta_path, x, y):
        """Run OCR in background and update the metadata file."""
        def _ocr_task():
            try:
                ocr_text = extract_text_around(screenshot, x, y, radius=150)
                if ocr_text:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    meta["ocr_nearby"] = ocr_text
                    with open(meta_path, "w", encoding="utf-8") as f:
                        json.dump(meta, f, indent=2, ensure_ascii=False, default=str)
            except Exception:
                pass

        threading.Thread(target=_ocr_task, daemon=True).start()

    def _process_click(self, event):
        self._flush_keys()

        x, y = event["x"], event["y"]
        button = event["button"]
        timestamp = event["timestamp"]
        in_scope = event.get("in_scope", True)
        app_name = event.get("app_name", "")

        step_num = self.session.next_step()
        action = f"{button.name}_click"
        ext = self._get_image_ext()

        screenshot = take_screenshot()
        annotated = annotate_click(screenshot, x, y, action)

        window_info = get_window_info(x, y)
        element = window_info.get("element") or {}
        element_name = element.get("name", "unknown")
        element_type = element.get("control_type", "element")
        description = f"Clicked {element_type} '{element_name}' in '{window_info.get('window_title', 'unknown')}'"

        monitor = self._monitor_info.get_monitor_at(x, y)

        img_path = self.session.step_path(step_num, f"{action}.{ext}")
        self._save_image(annotated, img_path)

        meta = {
            "step": step_num,
            "timestamp": timestamp,
            "action": action,
            "position": {"x": x, "y": y},
            "description": description,
            "in_scope": in_scope,
            "app_name": app_name,
            "window": {
                "title": window_info.get("window_title", ""),
                "class": window_info.get("window_class", ""),
                "process": window_info.get("process_name", ""),
            },
            "element": element,
            "monitor": monitor,
            "ocr_nearby": "",
            "screenshot": f"{step_num:03d}_{action}.{ext}",
        }

        meta_path = self.session.step_path(step_num, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False, default=str)

        # Async OCR
        if self.enable_ocr:
            self._enqueue_ocr(screenshot, meta_path, x, y)

        self.session.add_step({
            "step": step_num,
            "action": action,
            "description": description,
            "timestamp": timestamp,
        })

        scope_tag = "" if in_scope else " [out-of-scope]"
        print(f"  [{step_num:03d}] {description}{scope_tag}")

    def _process_drag(self, event):
        self._flush_keys()

        sx, sy = event["sx"], event["sy"]
        ex, ey = event["ex"], event["ey"]
        button = event["button"]
        timestamp = event["timestamp"]
        in_scope = event.get("in_scope", True)
        app_name = event.get("app_name", "")

        step_num = self.session.next_step()
        action = f"drag_{button.name}"
        ext = self._get_image_ext()

        screenshot = take_screenshot()
        annotated = annotate_drag(screenshot, sx, sy, ex, ey)

        window_info = get_window_info(sx, sy)
        description = f"Dragged from ({sx},{sy}) to ({ex},{ey}) in '{window_info.get('window_title', 'unknown')}'"

        monitor = self._monitor_info.get_monitor_at(sx, sy)

        img_path = self.session.step_path(step_num, f"{action}.{ext}")
        self._save_image(annotated, img_path)

        meta = {
            "step": step_num,
            "timestamp": timestamp,
            "action": action,
            "drag_start": {"x": sx, "y": sy},
            "drag_end": {"x": ex, "y": ey},
            "description": description,
            "in_scope": in_scope,
            "app_name": app_name,
            "window": {
                "title": window_info.get("window_title", ""),
                "class": window_info.get("window_class", ""),
                "process": window_info.get("process_name", ""),
            },
            "monitor": monitor,
            "screenshot": f"{step_num:03d}_{action}.{ext}",
        }

        meta_path = self.session.step_path(step_num, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False, default=str)

        self.session.add_step({
            "step": step_num,
            "action": action,
            "description": description,
            "timestamp": timestamp,
        })

        scope_tag = "" if in_scope else " [out-of-scope]"
        print(f"  [{step_num:03d}] {description}{scope_tag}")

    def _process_scroll(self, event):
        x, y = event["x"], event["y"]
        dx, dy = event["dx"], event["dy"]
        timestamp = event["timestamp"]
        in_scope = event.get("in_scope", True)
        app_name = event.get("app_name", "")

        step_num = self.session.next_step()
        action = "scroll"
        ext = self._get_image_ext()

        direction = "down" if dy < 0 else "up"
        screenshot = take_screenshot()
        annotated = annotate_scroll(screenshot, x, y, direction)

        window_info = get_window_info(x, y)
        description = f"Scrolled {direction} (dx={dx}, dy={dy}) at ({x},{y}) in '{window_info.get('window_title', 'unknown')}'"

        monitor = self._monitor_info.get_monitor_at(x, y)

        img_path = self.session.step_path(step_num, f"{action}.{ext}")
        self._save_image(annotated, img_path)

        meta = {
            "step": step_num,
            "timestamp": timestamp,
            "action": action,
            "position": {"x": x, "y": y},
            "scroll_dx": dx,
            "scroll_dy": dy,
            "direction": direction,
            "description": description,
            "in_scope": in_scope,
            "app_name": app_name,
            "window": {
                "title": window_info.get("window_title", ""),
                "class": window_info.get("window_class", ""),
                "process": window_info.get("process_name", ""),
            },
            "monitor": monitor,
            "screenshot": f"{step_num:03d}_{action}.{ext}",
        }

        meta_path = self.session.step_path(step_num, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False, default=str)

        self.session.add_step({
            "step": step_num,
            "action": action,
            "description": description,
            "timestamp": timestamp,
        })

        scope_tag = "" if in_scope else " [out-of-scope]"
        print(f"  [{step_num:03d}] {description}{scope_tag}")

    def _process_keypress(self, event):
        keys = event["keys"]
        timestamp = event["timestamp"]
        in_scope = event.get("in_scope", True)
        app_name = event.get("app_name", "")

        step_num = self.session.next_step()
        ext = self._get_image_ext()

        key_text = "".join(keys)
        display_text = key_text.replace("[space]", " ").replace("[enter]", "\u23ce")

        screenshot = take_screenshot()
        annotated = annotate_keypress(screenshot, display_text[:60])

        description = f"Typed: '{display_text[:80]}'"

        img_path = self.session.step_path(step_num, f"keypress.{ext}")
        self._save_image(annotated, img_path)

        meta = {
            "step": step_num,
            "timestamp": timestamp,
            "action": "keypress",
            "keys": keys,
            "text": key_text,
            "description": description,
            "in_scope": in_scope,
            "app_name": app_name,
            "screenshot": f"{step_num:03d}_keypress.{ext}",
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

        scope_tag = "" if in_scope else " [out-of-scope]"
        print(f"  [{step_num:03d}] {description}{scope_tag}")

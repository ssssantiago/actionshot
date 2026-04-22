"""rpakit - Internal SDK for generated RPA scripts.

Provides a high-level API for interacting with Windows desktop applications
using pywinauto's UIA backend, with hierarchical selector resolution, structured
logging, automatic retries, and screenshot-on-failure.

Usage::

    from actionshot.rpakit import UI, wait, log, run_workflow

    @run_workflow("my_workflow")
    def do_stuff(param: str) -> dict:
        ui = UI.attach("Notepad")
        ui.fill("edit_field", "Hello world")
        ui.click("save_button")
        return {"status": "ok"}
"""

from __future__ import annotations

import datetime
import functools
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Sequence, TypeVar, Union

# ---------------------------------------------------------------------------
# Optional dependency imports (graceful degradation)
# ---------------------------------------------------------------------------

try:
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
except ImportError:
    pyautogui = None  # type: ignore[assignment]

try:
    from pywinauto import Desktop, Application
    from pywinauto.findwindows import ElementNotFoundError
    from pywinauto.timings import wait_until

    _HAS_PYWINAUTO = True
except ImportError:
    _HAS_PYWINAUTO = False

try:
    from actionshot.capture import take_screenshot
except ImportError:
    take_screenshot = None  # type: ignore[assignment]

try:
    from actionshot.ocr import extract_structured
except ImportError:
    extract_structured = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_F = TypeVar("_F", bound=Callable[..., Any])

_LOG_DIR = Path(os.environ.get("RPAKIT_LOG_DIR", "./rpakit_logs"))
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / f"rpakit_{datetime.date.today().isoformat()}.jsonl"
_SCREENSHOT_DIR = _LOG_DIR / "screenshots"
_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

DRY_RUN: bool = os.environ.get("RPAKIT_DRY_RUN", "0") == "1"


def _ts() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def _write_log(entry: dict) -> None:
    """Append a structured JSON line to the log file."""
    entry.setdefault("ts", _ts())
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
    except Exception:
        # Never let logging break the workflow
        pass


def log(message: str, *, level: str = "INFO", **extra: Any) -> None:
    """Public structured logger for RPA scripts."""
    _write_log({"level": level, "msg": message, **extra})


def _capture_error_screenshot(label: str = "error") -> str | None:
    """Take a screenshot and save it.  Returns the file path or None."""
    if take_screenshot is None:
        return None
    try:
        img = take_screenshot()
        fname = f"{label}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        path = _SCREENSHOT_DIR / fname
        img.save(str(path))
        return str(path)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Selector resolution
# ---------------------------------------------------------------------------

# A selector spec is either:
#   - a plain string (treated as AutomationId)
#   - a dict with keys: primary, secondary, tertiary, fallback
#     each value can be a string (AutomationId) or a dict like
#     {"name": ..., "control_type": ..., "auto_id": ..., "coords": (x,y)}

SelectorSpec = Union[str, dict]


class _ResolvedElement:
    """Wrapper around a resolved UI element with metadata about how it was found."""

    __slots__ = ("element", "level", "method", "coords")

    def __init__(self, element: Any, level: str, method: str, coords: tuple[int, int] | None = None):
        self.element = element
        self.level = level  # e.g. "primary", "secondary", ...
        self.method = method  # e.g. "automation_id", "name+type", "ocr", "coords"
        self.coords = coords


class _SelectorResolver:
    """Hierarchical selector resolution engine."""

    def __init__(self, window: Any):
        self._window = window

    # -- public API ----------------------------------------------------------

    def resolve(self, spec: SelectorSpec, *, timeout: float = 5.0) -> _ResolvedElement:
        """Resolve *spec* to a UI element.  Tries each level in order."""
        levels = self._expand(spec)
        last_exc: Exception | None = None
        for level_name, sel in levels:
            try:
                resolved = self._resolve_single(sel, timeout=timeout)
                log(
                    "selector_resolved",
                    level="DEBUG",
                    selector=str(sel),
                    resolved_level=level_name,
                    method=resolved.method,
                )
                resolved.level = level_name
                return resolved
            except Exception as exc:
                last_exc = exc
                continue
        raise LookupError(
            f"Could not resolve selector {spec!r} at any level"
        ) from last_exc

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _expand(spec: SelectorSpec) -> list[tuple[str, Any]]:
        """Normalise a selector spec into ordered (level_name, selector) pairs."""
        if isinstance(spec, str):
            return [("primary", spec)]
        if isinstance(spec, dict):
            ordered = []
            for key in ("primary", "secondary", "tertiary", "fallback"):
                if key in spec:
                    ordered.append((key, spec[key]))
            # Also accept a flat dict as a single selector
            if not ordered:
                return [("primary", spec)]
            return ordered
        raise TypeError(f"Invalid selector spec type: {type(spec)}")

    def _resolve_single(self, sel: Any, *, timeout: float) -> _ResolvedElement:
        """Try the four resolution strategies in order for a single selector value."""
        if isinstance(sel, str):
            # Strategy 1: AutomationId
            return self._by_automation_id(sel, timeout=timeout)

        if isinstance(sel, dict):
            # Explicit coords shortcut
            if "coords" in sel:
                x, y = sel["coords"]
                return _ResolvedElement(None, "", "coords", coords=(int(x), int(y)))

            auto_id = sel.get("auto_id") or sel.get("automation_id")
            name = sel.get("name")
            ctrl = sel.get("control_type")

            # 1. AutomationId
            if auto_id:
                try:
                    return self._by_automation_id(auto_id, timeout=timeout)
                except Exception:
                    pass

            # 2. Name + ControlType
            if name:
                try:
                    return self._by_name_type(name, ctrl, timeout=timeout)
                except Exception:
                    pass

            # 3. OCR
            if name and extract_structured is not None and take_screenshot is not None:
                try:
                    return self._by_ocr(name)
                except Exception:
                    pass

            # 4. Coord fallback
            if "coords" in sel:
                x, y = sel["coords"]
                return _ResolvedElement(None, "", "coords", coords=(int(x), int(y)))

            raise LookupError(f"No resolution strategy succeeded for {sel!r}")

        # If it's a plain string that came through a dict level
        if isinstance(sel, str):
            return self._by_automation_id(sel, timeout=timeout)

        raise TypeError(f"Unsupported selector value: {sel!r}")

    # -- resolution strategies -----------------------------------------------

    def _by_automation_id(self, auto_id: str, *, timeout: float) -> _ResolvedElement:
        elem = self._window.child_window(auto_id=auto_id, found_index=0)
        elem.wait("exists visible", timeout=timeout)
        return _ResolvedElement(elem, "", "automation_id")

    def _by_name_type(self, name: str, control_type: str | None, *, timeout: float) -> _ResolvedElement:
        kwargs: dict[str, Any] = {"title": name, "found_index": 0}
        if control_type:
            kwargs["control_type"] = control_type
        elem = self._window.child_window(**kwargs)
        elem.wait("exists visible", timeout=timeout)
        return _ResolvedElement(elem, "", "name+type")

    def _by_ocr(self, text: str) -> _ResolvedElement:
        img = take_screenshot()  # type: ignore[misc]
        words = extract_structured(img)  # type: ignore[misc]
        text_lower = text.lower()
        # Try exact match first, then substring
        for word in words:
            if word["text"].lower() == text_lower:
                cx = word["x"] + word["width"] // 2
                cy = word["y"] + word["height"] // 2
                return _ResolvedElement(None, "", "ocr", coords=(cx, cy))
        for word in words:
            if text_lower in word["text"].lower():
                cx = word["x"] + word["width"] // 2
                cy = word["y"] + word["height"] // 2
                return _ResolvedElement(None, "", "ocr", coords=(cx, cy))
        raise LookupError(f"OCR could not find text {text!r}")


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def _retry(fn: Callable[..., Any], *, attempts: int = 3, base_delay: float = 0.5,
           label: str = "") -> Any:
    """Execute *fn* with exponential-backoff retries."""
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            log(
                "retry",
                level="WARN",
                label=label,
                attempt=attempt,
                error=str(exc),
            )
            if attempt < attempts:
                time.sleep(base_delay * (2 ** (attempt - 1)))
    raise RuntimeError(
        f"{label}: all {attempts} attempts failed"
    ) from last_exc


# ---------------------------------------------------------------------------
# Wait helper (module-level function)
# ---------------------------------------------------------------------------

def wait(seconds: float, *, reason: str = "") -> None:
    """Explicit wait.  Respects dry-run mode.  Logged."""
    log("wait", seconds=seconds, reason=reason)
    if not DRY_RUN:
        time.sleep(seconds)


# ---------------------------------------------------------------------------
# UI class
# ---------------------------------------------------------------------------

class UI:
    """High-level interface to a desktop application window."""

    def __init__(self, app: Any, window: Any):
        self._app = app
        self._window = window
        self._resolver = _SelectorResolver(window)

    # -- construction --------------------------------------------------------

    @classmethod
    def attach(cls, title_pattern: str, *, timeout: float = 15.0, backend: str = "uia") -> "UI":
        """Find and focus a window whose title contains *title_pattern*.

        Uses pywinauto's UIA backend by default for best accessibility support.
        """
        if not _HAS_PYWINAUTO:
            raise RuntimeError(
                "pywinauto is required but not installed.  "
                "Install it with: pip install pywinauto"
            )

        log("attach", title_pattern=title_pattern)

        if DRY_RUN:
            log("dry_run_attach", title_pattern=title_pattern, level="DEBUG")
            # Return a stub that won't touch any real window
            return cls(None, None)

        regex = re.compile(re.escape(title_pattern), re.IGNORECASE)

        desktop = Desktop(backend=backend)
        deadline = time.monotonic() + timeout

        while True:
            windows = desktop.windows()
            for w in windows:
                try:
                    title = w.window_text()
                except Exception:
                    continue
                if regex.search(title):
                    try:
                        w.set_focus()
                    except Exception:
                        pass
                    # Wrap via Application for richer API
                    try:
                        app = Application(backend=backend).connect(handle=w.handle)
                        win = app.window(handle=w.handle)
                    except Exception:
                        app = None
                        win = w
                    log("attached", title=title)
                    return cls(app, win)

            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"No window matching {title_pattern!r} found within {timeout}s"
                )
            time.sleep(0.5)

    # -- element helpers -----------------------------------------------------

    def _resolve(self, selector: SelectorSpec, *, timeout: float = 5.0) -> _ResolvedElement:
        if DRY_RUN:
            log("dry_run_resolve", selector=str(selector), level="DEBUG")
            return _ResolvedElement(None, "dry_run", "dry_run", coords=(0, 0))
        return self._resolver.resolve(selector, timeout=timeout)

    @staticmethod
    def _click_coords(x: int, y: int) -> None:
        if pyautogui is not None:
            pyautogui.click(x, y)
        else:
            raise RuntimeError("pyautogui is required for coordinate-based clicks")

    @staticmethod
    def _element_center(resolved: _ResolvedElement) -> tuple[int, int]:
        """Get the center coordinates of a resolved element."""
        if resolved.coords:
            return resolved.coords
        if resolved.element is not None:
            rect = resolved.element.rectangle()
            return (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
        raise RuntimeError("Cannot determine coordinates for element")

    # -- public actions ------------------------------------------------------

    def click(self, selector: SelectorSpec, *, timeout: float = 5.0) -> None:
        """Click an element.  Retries up to 3 times with exponential backoff."""
        log("click", selector=str(selector))
        if DRY_RUN:
            return

        def _do_click() -> None:
            resolved = self._resolve(selector, timeout=timeout)
            if resolved.element is not None and resolved.method != "coords":
                try:
                    resolved.element.click_input()
                    return
                except Exception:
                    # Fall through to coordinate click
                    pass
            x, y = self._element_center(resolved)
            self._click_coords(x, y)

        _retry(_do_click, label=f"click({selector})")

    def fill(self, selector: SelectorSpec, value: str, *, timeout: float = 5.0,
             clear_first: bool = True) -> None:
        """Click a field and type a value.

        Uses clipboard paste for text containing non-ASCII characters to avoid
        encoding issues with ``type_keys``.
        """
        log("fill", selector=str(selector), value_len=len(value))
        if DRY_RUN:
            return

        def _do_fill() -> None:
            resolved = self._resolve(selector, timeout=timeout)

            # Focus the field
            if resolved.element is not None:
                try:
                    resolved.element.click_input()
                except Exception:
                    x, y = self._element_center(resolved)
                    self._click_coords(x, y)
            else:
                x, y = self._element_center(resolved)
                self._click_coords(x, y)

            time.sleep(0.1)

            # Clear existing content
            if clear_first:
                if pyautogui is not None:
                    pyautogui.hotkey("ctrl", "a")
                    time.sleep(0.05)

            # Type value: use clipboard paste for non-ASCII
            is_ascii = all(ord(c) < 128 for c in value)
            if is_ascii and resolved.element is not None:
                try:
                    resolved.element.type_keys(value, with_spaces=True, with_tabs=True,
                                               with_newlines=True, pause=0.02)
                    return
                except Exception:
                    pass

            # Clipboard paste fallback
            _clipboard_paste(value)

        _retry(_do_fill, label=f"fill({selector})")

    def select(self, selector: SelectorSpec, option: str, *, timeout: float = 5.0) -> None:
        """Open a dropdown and select an option by text."""
        log("select", selector=str(selector), option=option)
        if DRY_RUN:
            return

        def _do_select() -> None:
            resolved = self._resolve(selector, timeout=timeout)

            # Try native combobox selection first
            if resolved.element is not None:
                try:
                    resolved.element.select(option)
                    return
                except Exception:
                    pass

                # Expand the dropdown
                try:
                    resolved.element.click_input()
                except Exception:
                    x, y = self._element_center(resolved)
                    self._click_coords(x, y)

                time.sleep(0.3)

                # Try to find the option as a child/list item
                try:
                    item = self._window.child_window(title=option, found_index=0)
                    item.wait("exists visible", timeout=3)
                    item.click_input()
                    return
                except Exception:
                    pass

            # Coordinate fallback: click dropdown, then search for option via OCR
            if resolved.coords or resolved.element is not None:
                x, y = self._element_center(resolved)
                self._click_coords(x, y)
                time.sleep(0.3)

                # Try OCR to find the option text
                if extract_structured is not None and take_screenshot is not None:
                    img = take_screenshot()
                    words = extract_structured(img)
                    option_lower = option.lower()
                    for word in words:
                        if option_lower in word["text"].lower():
                            cx = word["x"] + word["width"] // 2
                            cy = word["y"] + word["height"] // 2
                            self._click_coords(cx, cy)
                            return

                raise LookupError(f"Could not find option {option!r} in dropdown")

        _retry(_do_select, label=f"select({selector}, {option})")

    def wait_for(self, selector: SelectorSpec, *, timeout: float = 10.0) -> None:
        """Wait until an element is visible."""
        log("wait_for", selector=str(selector), timeout=timeout)
        if DRY_RUN:
            return

        deadline = time.monotonic() + timeout
        last_exc: Exception | None = None

        while time.monotonic() < deadline:
            try:
                self._resolve(selector, timeout=min(1.0, max(0.5, deadline - time.monotonic())))
                return
            except Exception as exc:
                last_exc = exc
                time.sleep(0.3)

        raise TimeoutError(
            f"Element {selector!r} not visible after {timeout}s"
        ) from last_exc

    def read(self, selector: SelectorSpec, *, timeout: float = 5.0) -> str:
        """Extract text from an element."""
        log("read", selector=str(selector))
        if DRY_RUN:
            return "[DRY_RUN]"

        resolved = self._resolve(selector, timeout=timeout)

        # Try native text extraction
        if resolved.element is not None:
            try:
                texts = resolved.element.texts()
                text = " ".join(t.strip() for t in texts if t.strip())
                if text:
                    return text
            except Exception:
                pass

            try:
                val = resolved.element.get_value()
                if val:
                    return str(val)
            except Exception:
                pass

            try:
                text = resolved.element.window_text()
                if text:
                    return text.strip()
            except Exception:
                pass

        # OCR fallback around the element coordinates
        if take_screenshot is not None:
            try:
                from actionshot.ocr import extract_text_around

                x, y = self._element_center(resolved)
                img = take_screenshot()
                return extract_text_around(img, x, y, radius=100)
            except Exception:
                pass

        return ""

    def navigate(self, path: Sequence[str], *, timeout: float = 5.0) -> None:
        """Click through a menu path, e.g. ``["File", "Save As"]``."""
        log("navigate", path=list(path))
        if DRY_RUN:
            return

        for i, item_name in enumerate(path):
            def _click_item(name: str = item_name) -> None:
                # Try menu item by name
                try:
                    menu_item = self._window.child_window(title=name, control_type="MenuItem",
                                                          found_index=0)
                    menu_item.wait("exists visible enabled", timeout=timeout)
                    menu_item.click_input()
                    return
                except Exception:
                    pass

                # Try generic name match
                try:
                    elem = self._window.child_window(title=name, found_index=0)
                    elem.wait("exists visible", timeout=timeout)
                    elem.click_input()
                    return
                except Exception:
                    pass

                # OCR fallback
                if extract_structured is not None and take_screenshot is not None:
                    img = take_screenshot()
                    words = extract_structured(img)
                    name_lower = name.lower()
                    for word in words:
                        if name_lower in word["text"].lower():
                            cx = word["x"] + word["width"] // 2
                            cy = word["y"] + word["height"] // 2
                            self._click_coords(cx, cy)
                            return

                raise LookupError(f"Menu item {name!r} not found")

            _retry(_click_item, label=f"navigate[{i}]={item_name}")
            # Brief pause between menu levels for animation
            time.sleep(0.3)

    def scroll(self, selector_or_coords: SelectorSpec | tuple[int, int], amount: int) -> None:
        """Scroll at a location.  Positive *amount* = up, negative = down."""
        log("scroll", target=str(selector_or_coords), amount=amount)
        if DRY_RUN:
            return

        if isinstance(selector_or_coords, tuple) and len(selector_or_coords) == 2:
            x, y = selector_or_coords
        else:
            resolved = self._resolve(selector_or_coords)
            x, y = self._element_center(resolved)

        if pyautogui is not None:
            pyautogui.moveTo(x, y)
            pyautogui.scroll(amount)
        else:
            raise RuntimeError("pyautogui is required for scroll")

    def drag(self, from_selector: SelectorSpec, to_selector: SelectorSpec,
             *, duration: float = 0.5, timeout: float = 5.0) -> None:
        """Drag from one element to another."""
        log("drag", from_sel=str(from_selector), to_sel=str(to_selector))
        if DRY_RUN:
            return

        from_resolved = self._resolve(from_selector, timeout=timeout)
        to_resolved = self._resolve(to_selector, timeout=timeout)

        fx, fy = self._element_center(from_resolved)
        tx, ty = self._element_center(to_resolved)

        if pyautogui is not None:
            pyautogui.moveTo(fx, fy, duration=0.15)
            pyautogui.mouseDown()
            time.sleep(0.1)
            pyautogui.moveTo(tx, ty, duration=duration)
            time.sleep(0.05)
            pyautogui.mouseUp()
        else:
            raise RuntimeError("pyautogui is required for drag operations")


# ---------------------------------------------------------------------------
# Clipboard paste helper
# ---------------------------------------------------------------------------

def _clipboard_paste(text: str) -> None:
    """Put *text* on the clipboard and paste it with Ctrl+V."""
    try:
        import subprocess
        # Use clip.exe on Windows (works from Python without extra deps)
        proc = subprocess.Popen(
            ["clip.exe"],
            stdin=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        proc.communicate(input=text.encode("utf-16-le"))
    except Exception:
        # Fallback via pyperclip or tkinter
        try:
            import pyperclip
            pyperclip.copy(text)
        except ImportError:
            import tkinter as _tk
            _r = _tk.Tk()
            _r.withdraw()
            _r.clipboard_clear()
            _r.clipboard_append(text)
            _r.update()
            _r.destroy()

    time.sleep(0.05)
    if pyautogui is not None:
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)


# ---------------------------------------------------------------------------
# run_workflow decorator
# ---------------------------------------------------------------------------

def run_workflow(name: str, *, retries: int = 0, base_delay: float = 2.0) -> Callable[[_F], _F]:
    """Decorator that wraps a workflow function with:

    - Structured JSON logging (start / success / failure)
    - Elapsed-time measurement
    - Auto-screenshot on exception
    - Optional retry with exponential backoff
    - Dry-run awareness
    """

    def decorator(fn: _F) -> _F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            log_ctx = {"workflow": name, "run_id": run_id, "dry_run": DRY_RUN}

            _write_log({"event": "workflow_start", **log_ctx,
                         "args": _safe_repr(args), "kwargs": _safe_repr(kwargs)})

            t0 = time.perf_counter()
            last_exc: Exception | None = None
            max_attempts = 1 + retries

            for attempt in range(1, max_attempts + 1):
                try:
                    result = fn(*args, **kwargs)
                    elapsed = time.perf_counter() - t0
                    _write_log({
                        "event": "workflow_success", **log_ctx,
                        "attempt": attempt,
                        "elapsed_s": round(elapsed, 3),
                        "result": _safe_repr(result),
                    })
                    return result
                except Exception as exc:
                    last_exc = exc
                    elapsed = time.perf_counter() - t0
                    screenshot_path = _capture_error_screenshot(
                        label=f"{name}_attempt{attempt}"
                    )
                    _write_log({
                        "event": "workflow_error", **log_ctx,
                        "attempt": attempt,
                        "elapsed_s": round(elapsed, 3),
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                        "screenshot": screenshot_path,
                    })
                    if attempt < max_attempts:
                        delay = base_delay * (2 ** (attempt - 1))
                        log(f"Retrying workflow {name} in {delay}s", level="WARN",
                            attempt=attempt, max_attempts=max_attempts)
                        time.sleep(delay)

            # All attempts exhausted
            _write_log({
                "event": "workflow_failed", **log_ctx,
                "attempts": max_attempts,
                "error": str(last_exc),
            })
            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator


def _safe_repr(obj: Any, max_len: int = 500) -> str:
    """Produce a truncated repr safe for JSON logging."""
    try:
        r = repr(obj)
    except Exception:
        r = "<unrepresentable>"
    if len(r) > max_len:
        return r[: max_len - 3] + "..."
    return r

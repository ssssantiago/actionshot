"""Extract UI element metadata using Windows accessibility tree and CDP.

Implements a hierarchical selector system with up to 7 levels of priority:
  1. primary_web     - CSS selector via Chrome DevTools Protocol
  2. primary_web_alt - XPath via CDP
  3. secondary_web   - ARIA accessible name/role via CDP
  4. primary         - UIA AutomationId (most stable native selector)
  5. secondary       - Structural UIA path (Window/Pane/Button chain)
  6. tertiary        - OCR anchor (element text + search region)
  7. fallback        - Raw screen coordinates + resolution

For browser-based apps (Chrome, Edge, Brave), CDP web selectors are
attempted first, providing stable DOM-level targeting for systems like
PJe, Projudi, e-SAJ, and eproc.
"""

import ctypes
import ctypes.wintypes
import os
import re
from typing import Any


# ---------------------------------------------------------------------------
# Screen resolution helper
# ---------------------------------------------------------------------------

def _get_screen_resolution() -> tuple[int, int]:
    """Return (width, height) of the primary monitor."""
    w = ctypes.windll.user32.GetSystemMetrics(0)
    h = ctypes.windll.user32.GetSystemMetrics(1)
    return w, h


# ---------------------------------------------------------------------------
# Process name helper
# ---------------------------------------------------------------------------

def _get_process_name(pid: int) -> str:
    """Get process executable name from PID."""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid
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


# ---------------------------------------------------------------------------
# AutomationId heuristic – detect auto-generated / useless ids
# ---------------------------------------------------------------------------

_AUTO_GENERATED_PATTERNS = [
    re.compile(r"^[0-9a-fA-F]{8}-"),       # GUID-like prefix
    re.compile(r"^__\w+_\d+$"),             # __type_123
    re.compile(r"^\d+$"),                   # bare numbers
    re.compile(r"^HwndWrapper\["),          # WPF host wrapper
    re.compile(r"^WindowsForms10\."),       # WinForms auto class
]


def _is_useful_automation_id(aid: str) -> bool:
    """Return True if *aid* looks like a developer-assigned id."""
    if not aid or not aid.strip():
        return False
    for pat in _AUTO_GENERATED_PATTERNS:
        if pat.search(aid):
            return False
    return True


# ---------------------------------------------------------------------------
# comtypes UIA helpers
# ---------------------------------------------------------------------------

def _uia_create():
    """Create a UIA COM object.  Returns (uia, IUIAutomation) or raises."""
    import comtypes.client  # noqa: F811

    uia = comtypes.client.CreateObject(
        "{ff48dba4-60ef-4201-aa87-54103eef594e}",
        interface=comtypes.gen.UIAutomationClient.IUIAutomation,
    )
    return uia


def _uia_element_dict(element) -> dict:
    """Extract basic element properties from a comtypes UIA element."""
    return {
        "name": element.CurrentName or "",
        "control_type": element.CurrentLocalizedControlType or "",
        "automation_id": element.CurrentAutomationId or "",
        "class_name": element.CurrentClassName or "",
    }


def _build_uia_path(element, uia) -> str:
    """Walk parents up to the root and build a structural path string.

    Example: ``Window[@title='Notepad']/Pane[@name='Editor']/Edit[@name='Text']``
    """
    parts: list[str] = []
    current = element
    try:
        root = uia.GetRootElement()
        root_runtime_id = root.GetRuntimeId()
    except Exception:
        root_runtime_id = None

    for _ in range(30):  # safety cap
        try:
            ctrl = current.CurrentLocalizedControlType or "Unknown"
            name = current.CurrentName or ""
            # Escape single quotes in name
            name_escaped = name.replace("'", "\\'") if name else ""
            part = f"{ctrl}[@name='{name_escaped}']"
            parts.append(part)

            # Try to detect root
            try:
                rid = current.GetRuntimeId()
                if root_runtime_id is not None and list(rid) == list(root_runtime_id):
                    break
            except Exception:
                pass

            # Walk up
            parent = uia.RawViewWalker.GetParentElement(current)
            if parent is None:
                break
            current = parent
        except Exception:
            break

    parts.reverse()
    return "/".join(parts)


def _get_ui_element_comtypes(x: int, y: int) -> tuple[dict | None, str, str]:
    """Use comtypes UIA to get element info.

    Returns (element_dict, automation_id, uia_path).
    """
    try:
        uia = _uia_create()
    except Exception:
        return None, "", ""

    try:
        pt = ctypes.wintypes.POINT(x, y)
        element = uia.ElementFromPoint(pt)
        if element is None:
            return None, "", ""

        elem_dict = _uia_element_dict(element)
        aid = elem_dict.get("automation_id", "")
        path = _build_uia_path(element, uia)
        return elem_dict, aid, path
    except Exception:
        return None, "", ""


# ---------------------------------------------------------------------------
# pywinauto fallback helpers
# ---------------------------------------------------------------------------

def _get_element_pywinauto(x: int, y: int) -> tuple[dict | None, str, str]:
    """Fallback using pywinauto.

    Returns (element_dict, automation_id, uia_path).
    """
    try:
        from pywinauto import Desktop

        desktop = Desktop(backend="uia")
        wrapper = desktop.from_point(x, y)
        if wrapper is None:
            return None, "", ""

        elem_dict = {
            "name": wrapper.window_text() or "",
            "control_type": wrapper.friendly_class_name() or "",
            "automation_id": (
                getattr(wrapper, "automation_id", lambda: "")() or ""
            ),
            "class_name": wrapper.class_name() or "",
        }
        aid = elem_dict["automation_id"]
        path = _build_pywinauto_path(wrapper)
        return elem_dict, aid, path
    except Exception:
        return None, "", ""


def _build_pywinauto_path(wrapper) -> str:
    """Build a structural path from a pywinauto wrapper."""
    parts: list[str] = []
    current = wrapper
    for _ in range(30):
        try:
            ctrl = current.friendly_class_name() or "Unknown"
            name = (current.window_text() or "").replace("'", "\\'")
            parts.append(f"{ctrl}[@name='{name}']")
            parent = current.parent()
            if parent is None or parent == current:
                break
            current = parent
        except Exception:
            break
    parts.reverse()
    return "/".join(parts)


# ---------------------------------------------------------------------------
# Build the hierarchical target selector
# ---------------------------------------------------------------------------

def _build_target(
    x: int,
    y: int,
    automation_id: str,
    uia_path: str,
    element_name: str,
    web_selectors: dict | None = None,
) -> dict:
    """Construct the hierarchical target selector dict.

    When *web_selectors* is provided (from CDP), the target gets up to 7
    levels: 3 web + 4 native.  Otherwise falls back to the original 4.
    """
    screen_w, screen_h = _get_screen_resolution()

    # -- web selectors (from CDP, if available) --
    primary_web = None
    primary_web_alt = None
    secondary_web = None
    if web_selectors:
        primary_web = web_selectors.get("primary_web")
        primary_web_alt = web_selectors.get("primary_web_alt")
        secondary_web = web_selectors.get("secondary_web")

    # -- primary: UIA AutomationId (only if useful) --
    if _is_useful_automation_id(automation_id):
        primary = {"method": "uia_automation_id", "value": automation_id}
    else:
        primary = None

    # -- secondary: structural UIA path --
    secondary = {"method": "uia_path", "value": uia_path} if uia_path else None

    # -- tertiary: OCR anchor --
    text = element_name.strip() if element_name else ""
    if text:
        tertiary = {
            "method": "ocr_anchor",
            "text": text,
            "search_region": [x - 90, y - 40, x + 90, y + 40],
        }
    else:
        tertiary = None

    # -- fallback: raw coordinates --
    fallback = {
        "method": "coordinates",
        "x": x,
        "y": y,
        "resolution": [screen_w, screen_h],
    }

    return {
        "primary_web": primary_web,
        "primary_web_alt": primary_web_alt,
        "secondary_web": secondary_web,
        "primary": primary,
        "secondary": secondary,
        "tertiary": tertiary,
        "fallback": fallback,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_window_info(x: int, y: int) -> dict:
    """Get info about the window and UI element at the given screen coordinates.

    Returns a dict with:
      - Legacy top-level keys: ``window_title``, ``window_class``,
        ``process_name``, ``process_id``, ``element``
      - New ``target`` key containing the hierarchical selector
      - New ``context`` key with window/app metadata
    """
    info: dict = {
        "window_title": "",
        "window_class": "",
        "process_name": "",
        "element": None,
        "target": None,
        "context": {},
    }

    # ------------------------------------------------------------------
    # Window-level info via Win32
    # ------------------------------------------------------------------
    point = ctypes.wintypes.POINT(x, y)
    hwnd = ctypes.windll.user32.WindowFromPoint(point)
    if not hwnd:
        # Even with no window, populate fallback target
        info["target"] = _build_target(x, y, "", "", "")
        return info

    # Window title
    buf_len = ctypes.windll.user32.GetWindowTextLengthW(hwnd) + 1
    buf = ctypes.create_unicode_buffer(buf_len)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, buf_len)
    info["window_title"] = buf.value

    # Window class
    class_buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, class_buf, 256)
    info["window_class"] = class_buf.value

    # Process name
    try:
        pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        info["process_id"] = pid.value
        info["process_name"] = _get_process_name(pid.value)
    except Exception:
        pass

    # ------------------------------------------------------------------
    # UI element via UIA (comtypes first, then pywinauto)
    # ------------------------------------------------------------------
    elem_dict: dict | None = None
    automation_id = ""
    uia_path = ""

    elem_dict, automation_id, uia_path = _get_ui_element_comtypes(x, y)

    if elem_dict is None:
        elem_dict, automation_id, uia_path = _get_element_pywinauto(x, y)

    info["element"] = elem_dict

    # ------------------------------------------------------------------
    # CDP web selectors (for browser-based apps)
    # ------------------------------------------------------------------
    web_selectors: dict | None = None
    page_url: str = ""
    process_lower = (info.get("process_name") or "").lower()
    _BROWSER_PROCESSES = {"chrome.exe", "msedge.exe", "brave.exe"}

    if process_lower in _BROWSER_PROCESSES:
        try:
            from actionshot.cdp import ChromeCDP

            cdp = ChromeCDP()
            if cdp.is_available():
                cdp.connect()
                try:
                    web_selectors = cdp.get_element_at(x, y)
                    # Also capture the page URL for context
                    try:
                        page_url = cdp.get_page_url()
                    except Exception:
                        page_url = ""
                finally:
                    cdp.disconnect()
        except Exception:
            # CDP not available or failed -- fall through to UIA-only
            web_selectors = None

    # ------------------------------------------------------------------
    # Hierarchical target selector
    # ------------------------------------------------------------------
    element_name = (elem_dict or {}).get("name", "")
    info["target"] = _build_target(
        x, y, automation_id, uia_path, element_name,
        web_selectors=web_selectors,
    )

    # ------------------------------------------------------------------
    # Context block
    # ------------------------------------------------------------------
    context: dict[str, Any] = {
        "window_title": info["window_title"],
        "app_name": info["process_name"],
        "window_class": info["window_class"],
    }
    if web_selectors and page_url:  # type: ignore[possibly-undefined]
        context["page_url"] = page_url
    info["context"] = context

    return info

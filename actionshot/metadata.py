"""Extract UI element metadata using Windows accessibility tree."""

import ctypes
import ctypes.wintypes


def get_window_info(x: int, y: int) -> dict:
    """Get info about the window and element at the given screen coordinates."""
    info = {
        "window_title": "",
        "window_class": "",
        "process_name": "",
        "element": None,
    }

    # Get window under cursor
    point = ctypes.wintypes.POINT(x, y)
    hwnd = ctypes.windll.user32.WindowFromPoint(point)
    if not hwnd:
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

    # Try to get accessibility element info
    try:
        info["element"] = _get_ui_element(x, y)
    except Exception:
        pass

    return info


def _get_process_name(pid: int) -> str:
    """Get process name from PID."""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(260)
        size = ctypes.wintypes.DWORD(260)
        ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        import os
        return os.path.basename(buf.value)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _get_ui_element(x: int, y: int) -> dict | None:
    """Try to get UI Automation element info at coordinates."""
    try:
        import comtypes.client
        from comtypes import COMError

        # Initialize UI Automation
        uia = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}",
            interface=comtypes.gen.UIAutomationClient.IUIAutomation,
        )
    except Exception:
        # Fallback: try pywinauto
        return _get_element_pywinauto(x, y)

    try:
        element = uia.ElementFromPoint(ctypes.wintypes.POINT(x, y))
        if element:
            return {
                "name": element.CurrentName,
                "control_type": element.CurrentLocalizedControlType,
                "automation_id": element.CurrentAutomationId,
                "class_name": element.CurrentClassName,
            }
    except Exception:
        pass

    return None


def _get_element_pywinauto(x: int, y: int) -> dict | None:
    """Fallback: use pywinauto to get element info."""
    try:
        from pywinauto import Desktop

        desktop = Desktop(backend="uia")
        element = desktop.from_point(x, y)
        if element:
            return {
                "name": element.window_text(),
                "control_type": element.friendly_class_name(),
                "automation_id": getattr(element, "automation_id", lambda: "")(),
                "class_name": element.class_name(),
            }
    except Exception:
        pass

    return None

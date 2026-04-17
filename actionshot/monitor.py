"""Multi-monitor support - identifies which monitor was interacted with."""

import ctypes
import ctypes.wintypes


class MonitorInfo:
    """Detect and track multiple monitors."""

    def __init__(self):
        self.monitors = []
        self._enumerate()

    def _enumerate(self):
        self.monitors = []

        def callback(hmonitor, hdc, lprect, lparam):
            info = ctypes.wintypes.RECT()
            ctypes.memmove(ctypes.byref(info), lprect, ctypes.sizeof(ctypes.wintypes.RECT))

            # Get DPI-aware monitor info
            mi = _MONITORINFOEX()
            mi.cbSize = ctypes.sizeof(_MONITORINFOEX)
            ctypes.windll.user32.GetMonitorInfoW(hmonitor, ctypes.byref(mi))

            self.monitors.append({
                "index": len(self.monitors),
                "name": mi.szDevice.rstrip('\x00'),
                "left": info.left,
                "top": info.top,
                "right": info.right,
                "bottom": info.bottom,
                "width": info.right - info.left,
                "height": info.bottom - info.top,
                "primary": bool(mi.dwFlags & 1),
            })
            return True

        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.wintypes.HMONITOR,
            ctypes.wintypes.HDC,
            ctypes.POINTER(ctypes.wintypes.RECT),
            ctypes.wintypes.LPARAM,
        )
        ctypes.windll.user32.EnumDisplayMonitors(
            None, None, MONITORENUMPROC(callback), 0,
        )

    def get_monitor_at(self, x: int, y: int) -> dict | None:
        """Return monitor info for the given screen coordinates."""
        for mon in self.monitors:
            if (mon["left"] <= x < mon["right"] and
                    mon["top"] <= y < mon["bottom"]):
                return mon
        return self.monitors[0] if self.monitors else None

    def get_all(self) -> list[dict]:
        return list(self.monitors)

    def count(self) -> int:
        return len(self.monitors)


class _MONITORINFOEX(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("rcMonitor", ctypes.wintypes.RECT),
        ("rcWork", ctypes.wintypes.RECT),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("szDevice", ctypes.c_wchar * 32),
    ]

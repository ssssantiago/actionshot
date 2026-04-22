"""Smart wait - wait for screen changes instead of dumb sleep."""

import time
from PIL import Image
from .capture import take_screenshot, take_screenshot_region


def wait_for_screen_change(reference: Image.Image = None, region: tuple = None,
                           timeout: float = 10.0, poll_interval: float = 0.3,
                           threshold: float = 0.02) -> bool:
    """Wait until the screen changes from a reference image.

    Args:
        reference: Baseline screenshot. If None, takes one now.
        region: Optional (x, y, w, h) to only compare a region.
        timeout: Max seconds to wait.
        poll_interval: Seconds between checks.
        threshold: Fraction of pixels that must differ (0.0-1.0).

    Returns:
        True if screen changed, False if timed out.
    """
    if reference is None:
        reference = _grab(region)

    ref_data = list(reference.getdata())
    start = time.monotonic()

    while time.monotonic() - start < timeout:
        time.sleep(poll_interval)
        current = _grab(region)
        cur_data = list(current.getdata())

        if len(ref_data) != len(cur_data):
            return True  # resolution changed

        diff_count = sum(1 for a, b in zip(ref_data, cur_data) if _pixel_diff(a, b) > 30)
        diff_ratio = diff_count / max(len(ref_data), 1)

        if diff_ratio > threshold:
            return True

    return False


def wait_for_pixel_color(x: int, y: int, target_color: tuple,
                         tolerance: int = 30, timeout: float = 10.0) -> bool:
    """Wait until a specific pixel reaches a target color."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        img = take_screenshot_region(x, y, 1, 1)
        pixel = img.getpixel((0, 0))
        if _pixel_diff(pixel, target_color) <= tolerance:
            return True
        time.sleep(0.2)
    return False


def wait_for_element(x: int, y: int, expected_name: str = None,
                     timeout: float = 10.0) -> bool:
    """Wait until a UI element appears at the given coordinates."""
    from .metadata import get_window_info

    start = time.monotonic()
    while time.monotonic() - start < timeout:
        info = get_window_info(x, y)
        element = info.get("element") or {}
        name = element.get("name", "")

        if expected_name:
            if expected_name.lower() in name.lower():
                return True
        else:
            if name:
                return True

        time.sleep(0.3)
    return False


def _grab(region=None) -> Image.Image:
    if region:
        x, y, w, h = region
        return take_screenshot_region(x, y, w, h)
    return take_screenshot()


def _pixel_diff(a, b) -> int:
    if isinstance(a, int):
        return abs(a - b)
    return sum(abs(c1 - c2) for c1, c2 in zip(a[:3], b[:3])) // 3

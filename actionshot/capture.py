"""Screenshot capture with visual annotations. Uses mss for fast capture."""

import math

import mss
import mss.tools
from PIL import Image, ImageDraw, ImageFont

# Reusable mss instance (thread-safe per-thread via __enter__)
_sct = None


def _get_sct():
    global _sct
    if _sct is None:
        _sct = mss.mss()
    return _sct


def _get_font(size: int = 16):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def take_screenshot() -> Image.Image:
    """Capture full screen using mss (much faster than pyautogui)."""
    sct = _get_sct()
    monitor = sct.monitors[0]  # all monitors combined
    raw = sct.grab(monitor)
    return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def take_screenshot_region(x: int, y: int, width: int, height: int) -> Image.Image:
    """Capture a specific screen region."""
    sct = _get_sct()
    region = {"left": x, "top": y, "width": width, "height": height}
    raw = sct.grab(region)
    return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def annotate_click(screenshot: Image.Image, x: int, y: int, action: str = "click") -> Image.Image:
    """Draw a circle, crosshair, and coordinate label at the click position."""
    img = screenshot.copy()
    draw = ImageDraw.Draw(img)
    font = _get_font(16)

    radius = 20
    draw.ellipse(
        [x - radius, y - radius, x + radius, y + radius],
        outline="red", width=3,
    )
    draw.ellipse([x - 4, y - 4, x + 4, y + 4], fill="red")
    draw.line([x - radius - 5, y, x + radius + 5, y], fill="red", width=1)
    draw.line([x, y - radius - 5, x, y + radius + 5], fill="red", width=1)

    label = f"{action} ({x}, {y})"
    label_x = x + radius + 8
    label_y = y - 10
    bbox = draw.textbbox((label_x, label_y), label, font=font)
    draw.rectangle([bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2], fill="white", outline="red")
    draw.text((label_x, label_y), label, fill="red", font=font)

    return img


def annotate_scroll(screenshot: Image.Image, x: int, y: int, direction: str = "down") -> Image.Image:
    """Draw a scroll indicator with coordinates."""
    img = screenshot.copy()
    draw = ImageDraw.Draw(img)
    font = _get_font(16)

    arrow_len = 30
    color = "#00AAFF"

    if direction == "down":
        draw.line([x, y - arrow_len, x, y + arrow_len], fill=color, width=3)
        draw.polygon([(x, y + arrow_len + 8), (x - 8, y + arrow_len - 4), (x + 8, y + arrow_len - 4)], fill=color)
    else:
        draw.line([x, y - arrow_len, x, y + arrow_len], fill=color, width=3)
        draw.polygon([(x, y - arrow_len - 8), (x - 8, y - arrow_len + 4), (x + 8, y - arrow_len + 4)], fill=color)

    label = f"scroll {direction} ({x}, {y})"
    label_x = x + 15
    label_y = y - 10
    bbox = draw.textbbox((label_x, label_y), label, font=font)
    draw.rectangle([bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2], fill="white", outline=color)
    draw.text((label_x, label_y), label, fill=color, font=font)

    return img


def annotate_drag(screenshot: Image.Image, sx: int, sy: int, ex: int, ey: int) -> Image.Image:
    """Draw a drag path with start/end markers and coordinates."""
    img = screenshot.copy()
    draw = ImageDraw.Draw(img)
    font = _get_font(14)

    color = "#FF6600"

    draw.line([sx, sy, ex, ey], fill=color, width=3)

    draw.ellipse([sx - 8, sy - 8, sx + 8, sy + 8], fill="#00CC00", outline="white", width=2)
    draw.ellipse([ex - 8, ey - 8, ex + 8, ey + 8], fill="#CC0000", outline="white", width=2)

    angle = math.atan2(ey - sy, ex - sx)
    arrow_size = 12
    ax1 = ex - arrow_size * math.cos(angle - 0.4)
    ay1 = ey - arrow_size * math.sin(angle - 0.4)
    ax2 = ex - arrow_size * math.cos(angle + 0.4)
    ay2 = ey - arrow_size * math.sin(angle + 0.4)
    draw.polygon([(ex, ey), (int(ax1), int(ay1)), (int(ax2), int(ay2))], fill=color)

    start_label = f"start ({sx}, {sy})"
    bbox = draw.textbbox((sx + 12, sy - 8), start_label, font=font)
    draw.rectangle([bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2], fill="white", outline="#00CC00")
    draw.text((sx + 12, sy - 8), start_label, fill="#00CC00", font=font)

    end_label = f"end ({ex}, {ey})"
    bbox = draw.textbbox((ex + 12, ey - 8), end_label, font=font)
    draw.rectangle([bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2], fill="white", outline="#CC0000")
    draw.text((ex + 12, ey - 8), end_label, fill="#CC0000", font=font)

    return img


def annotate_keypress(screenshot: Image.Image, key_text: str) -> Image.Image:
    """Draw a keyboard indicator on the screenshot."""
    img = screenshot.copy()
    draw = ImageDraw.Draw(img)
    font = _get_font(18)

    label = f"keys: {key_text}"
    margin = 10
    bbox = draw.textbbox((margin, margin), label, font=font)
    draw.rectangle([bbox[0] - 4, bbox[1] - 4, bbox[2] + 4, bbox[3] + 4], fill="#222222", outline="#FFD600", width=2)
    draw.text((margin, margin), label, fill="#FFD600", font=font)

    return img

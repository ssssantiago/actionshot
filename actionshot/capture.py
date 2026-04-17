"""Screenshot capture with visual annotations."""

import pyautogui
from PIL import Image, ImageDraw, ImageFont


def take_screenshot():
    return pyautogui.screenshot()


def annotate_click(screenshot: Image.Image, x: int, y: int, action: str = "click") -> Image.Image:
    """Draw a circle and label on the screenshot at the click position."""
    img = screenshot.copy()
    draw = ImageDraw.Draw(img)

    radius = 20
    # Outer circle (red)
    draw.ellipse(
        [x - radius, y - radius, x + radius, y + radius],
        outline="red",
        width=3,
    )
    # Inner dot
    draw.ellipse(
        [x - 4, y - 4, x + 4, y + 4],
        fill="red",
    )
    # Crosshair lines
    draw.line([x - radius - 5, y, x + radius + 5, y], fill="red", width=1)
    draw.line([x, y - radius - 5, x, y + radius + 5], fill="red", width=1)

    # Label
    label = f"{action} ({x}, {y})"
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default()

    label_x = x + radius + 8
    label_y = y - 10
    # Background for label
    bbox = draw.textbbox((label_x, label_y), label, font=font)
    draw.rectangle(
        [bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2],
        fill="white",
        outline="red",
    )
    draw.text((label_x, label_y), label, fill="red", font=font)

    return img


def annotate_keypress(screenshot: Image.Image, key_text: str) -> Image.Image:
    """Draw a keyboard indicator on the screenshot."""
    img = screenshot.copy()
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()

    label = f"⌨ {key_text}"
    margin = 10
    bbox = draw.textbbox((margin, margin), label, font=font)
    draw.rectangle(
        [bbox[0] - 4, bbox[1] - 4, bbox[2] + 4, bbox[3] + 4],
        fill="#222222",
        outline="#FFD600",
        width=2,
    )
    draw.text((margin, margin), label, fill="#FFD600", font=font)

    return img

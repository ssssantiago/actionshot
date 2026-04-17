"""OCR - extracts visible text from screenshots for richer AI context."""

import os
from PIL import Image

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False


def extract_text(image: Image.Image, region: tuple = None, lang: str = "eng") -> str:
    """Extract text from a PIL Image using Tesseract OCR.

    Args:
        image: PIL Image to extract text from.
        region: Optional (x, y, w, h) tuple to crop before OCR.
        lang: Tesseract language code.

    Returns:
        Extracted text string.
    """
    if not HAS_TESSERACT:
        return "[OCR unavailable - install pytesseract and Tesseract]"

    img = image
    if region:
        x, y, w, h = region
        img = image.crop((x, y, x + w, y + h))

    try:
        text = pytesseract.image_to_string(img, lang=lang)
        return text.strip()
    except Exception as e:
        return f"[OCR error: {e}]"


def extract_text_around(image: Image.Image, x: int, y: int, radius: int = 150, lang: str = "eng") -> str:
    """Extract text from a region around a specific point (e.g., click location)."""
    w, h = image.size
    left = max(0, x - radius)
    top = max(0, y - radius)
    right = min(w, x + radius)
    bottom = min(h, y + radius)

    region = (left, top, right - left, bottom - top)
    return extract_text(image, region=region, lang=lang)


def extract_structured(image: Image.Image, lang: str = "eng") -> list[dict]:
    """Extract text with bounding boxes for each word."""
    if not HAS_TESSERACT:
        return []

    try:
        data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
    except Exception:
        return []

    results = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        if not text:
            continue
        results.append({
            "text": text,
            "x": data["left"][i],
            "y": data["top"][i],
            "width": data["width"][i],
            "height": data["height"][i],
            "confidence": data["conf"][i],
        })

    return results

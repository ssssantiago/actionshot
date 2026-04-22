"""Data redaction pipeline for sanitizing sensitive data before external API calls.

Detects and redacts Brazilian PII (CPF, CNPJ, RG, phone), emails, credit cards,
passwords, and legal process numbers from session metadata and screenshots.
"""

import copy
import json
import os
import re
import shutil
from datetime import datetime
from typing import Any

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ---------------------------------------------------------------------------
# Sensitivity classes
# ---------------------------------------------------------------------------

CLASS_CREDENTIALS = "credentials"
CLASS_PERSONAL_DATA = "personal_data"
CLASS_LEGAL_DATA = "legal_data"
CLASS_PUBLIC_UI = "public_ui"

# ---------------------------------------------------------------------------
# Pattern definitions  (label, compiled regex, replacement, sensitivity class)
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, re.Pattern, str, str]] = [
    # Legal process numbers must come before CPF (both start with digits)
    (
        "processo",
        re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"),
        "<REDACTED_PROCESSO>",
        CLASS_LEGAL_DATA,
    ),
    (
        "cnpj",
        re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}"),
        "<REDACTED_CNPJ>",
        CLASS_PERSONAL_DATA,
    ),
    (
        "cpf",
        re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}"),
        "<REDACTED_CPF>",
        CLASS_PERSONAL_DATA,
    ),
    (
        "rg",
        re.compile(
            r"(?i)(?:RG[:\s]*)"
            r"\d{1,2}\.?\d{3}\.?\d{3}-?[0-9Xx]"
        ),
        "<REDACTED_RG>",
        CLASS_PERSONAL_DATA,
    ),
    (
        "card",
        re.compile(r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}"),
        "<REDACTED_CARD>",
        CLASS_CREDENTIALS,
    ),
    (
        "email",
        re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
        "<REDACTED_EMAIL>",
        CLASS_PERSONAL_DATA,
    ),
    (
        "phone",
        re.compile(r"\(?\d{2}\)?\s?\d{4,5}-?\d{4}"),
        "<REDACTED_PHONE>",
        CLASS_PERSONAL_DATA,
    ),
]

# Password pattern is handled separately via metadata field inspection.
_PASSWORD_PLACEHOLDER = "<REDACTED_PASSWORD>"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def redact_text(text: str) -> tuple[str, list[dict]]:
    """Replace sensitive patterns in *text*.

    Returns:
        A tuple of (redacted_text, redactions) where *redactions* is a list of
        dicts with keys ``type``, ``original``, ``replacement``, ``class``,
        ``start``, ``end``.
    """
    if not isinstance(text, str) or not text:
        return text, []

    redactions: list[dict] = []

    for label, pattern, replacement, sensitivity in _PATTERNS:
        for match in pattern.finditer(text):
            redactions.append(
                {
                    "type": label,
                    "original": match.group(),
                    "replacement": replacement,
                    "class": sensitivity,
                    "start": match.start(),
                    "end": match.end(),
                }
            )

    # Apply replacements from right to left so indices stay valid.
    redactions.sort(key=lambda r: r["start"], reverse=True)
    chars = list(text)
    for r in redactions:
        chars[r["start"]: r["end"]] = list(r["replacement"])

    # Return redactions in reading order.
    redactions.reverse()
    return "".join(chars), redactions


def classify_data(text: str) -> str:
    """Return the sensitivity class for *text*.

    Priority order: credentials > personal_data > legal_data > public_ui.
    """
    if not isinstance(text, str) or not text:
        return CLASS_PUBLIC_UI

    classes_found: set[str] = set()
    for _label, pattern, _repl, sensitivity in _PATTERNS:
        if pattern.search(text):
            classes_found.add(sensitivity)

    if CLASS_CREDENTIALS in classes_found:
        return CLASS_CREDENTIALS
    if CLASS_PERSONAL_DATA in classes_found:
        return CLASS_PERSONAL_DATA
    if CLASS_LEGAL_DATA in classes_found:
        return CLASS_LEGAL_DATA
    return CLASS_PUBLIC_UI


def redact_metadata(meta: dict) -> dict:
    """Deep-copy *meta* and redact every string value.

    If a key hints at a password field (``is_password`` is truthy, or key
    contains ``password``), its value is replaced wholesale.
    """
    return _deep_redact(copy.deepcopy(meta))


def redact_screenshot(image: "Image.Image", regions: list[dict]) -> "Image.Image":
    """Black out rectangular *regions* on a PIL Image.

    Each region dict must contain ``x``, ``y``, ``width``, ``height`` (ints).
    Returns a new Image (the original is not modified).
    """
    if not HAS_PIL:
        raise RuntimeError("Pillow is required for screenshot redaction (pip install Pillow)")

    out = image.copy()
    draw = ImageDraw.Draw(out)
    for r in regions:
        x, y = int(r["x"]), int(r["y"])
        w, h = int(r["width"]), int(r["height"])
        draw.rectangle([x, y, x + w, y + h], fill="black")
    return out


def redact_session(session_path: str) -> str:
    """Create a redacted copy of the session at *session_path*.

    The copy is placed at ``{session_path}_redacted/``.  All JSON metadata
    files are redacted, all PNG/JPEG screenshots are processed (regions listed
    in companion ``*_regions.json`` files are blacked out), and a
    ``redaction_log.json`` audit trail is written.

    Returns the path to the redacted session folder.
    """
    session_path = os.path.normpath(session_path)
    if not os.path.isdir(session_path):
        raise FileNotFoundError(f"Session directory not found: {session_path}")

    dest = session_path.rstrip("/\\") + "_redacted"
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(session_path, dest)

    audit_entries: list[dict] = []

    # --- Redact JSON metadata files ---
    for root, _dirs, files in os.walk(dest):
        for fname in files:
            fpath = os.path.join(root, fname)

            if fname.endswith(".json") and fname != "redaction_log.json":
                _redact_json_file(fpath, audit_entries)

            elif fname.lower().endswith((".png", ".jpg", ".jpeg")):
                _redact_image_file(fpath, audit_entries)

    # --- Write audit log ---
    audit_log = {
        "redacted_at": datetime.now().isoformat(),
        "source": session_path,
        "destination": dest,
        "total_redactions": len(audit_entries),
        "entries": audit_entries,
    }
    log_path = os.path.join(dest, "redaction_log.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(audit_log, f, indent=2, ensure_ascii=False)

    return dest


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _deep_redact(obj: Any, *, _parent_is_password: bool = False) -> Any:
    """Recursively walk *obj* and redact string values in place."""
    if isinstance(obj, dict):
        is_pw = bool(obj.get("is_password"))
        for key, value in obj.items():
            field_is_pw = (
                is_pw
                or _parent_is_password
                or (isinstance(key, str) and "password" in key.lower())
            )
            obj[key] = _deep_redact(value, _parent_is_password=field_is_pw)
        return obj

    if isinstance(obj, list):
        return [
            _deep_redact(item, _parent_is_password=_parent_is_password)
            for item in obj
        ]

    if isinstance(obj, str):
        if _parent_is_password:
            return _PASSWORD_PLACEHOLDER
        redacted, _ = redact_text(obj)
        return redacted

    return obj


def _redact_json_file(fpath: str, audit: list[dict]) -> None:
    """Read a JSON file, redact, and overwrite it."""
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    original_text = json.dumps(data, ensure_ascii=False)
    redacted_data = redact_metadata(data) if isinstance(data, dict) else data
    redacted_text = json.dumps(redacted_data, ensure_ascii=False)

    if original_text != redacted_text:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(redacted_data, f, indent=2, ensure_ascii=False)
        audit.append({"file": os.path.basename(fpath), "action": "metadata_redacted"})


def _redact_image_file(fpath: str, audit: list[dict]) -> None:
    """If a companion ``*_regions.json`` exists, black out those regions."""
    if not HAS_PIL:
        return

    base, ext = os.path.splitext(fpath)
    regions_file = base + "_regions.json"
    if not os.path.isfile(regions_file):
        return

    try:
        with open(regions_file, "r", encoding="utf-8") as f:
            regions = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    if not isinstance(regions, list) or not regions:
        return

    img = Image.open(fpath)
    img = redact_screenshot(img, regions)
    img.save(fpath)

    audit.append({
        "file": os.path.basename(fpath),
        "action": "screenshot_redacted",
        "regions_count": len(regions),
    })

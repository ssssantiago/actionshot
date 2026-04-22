"""Prompt Template - generates structured prompts for Claude Code from workflow IR.

Provides two entry points:
  - ``generate_prompt(ir)``       -> full markdown prompt as a string
  - ``generate_api_payload(ir)``  -> Claude Messages API payload dict
"""

import base64
import glob as glob_mod
import json
import os
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# System section - mandatory rules
# ---------------------------------------------------------------------------

_SYSTEM_RULES = """\
You are an expert desktop RPA engineer.  You receive a declarative workflow IR
(Intermediate Representation) that describes a series of desktop interactions a
user wants to automate.

## Mandatory Rules

1. **Use the rpakit SDK exclusively.**  Do NOT use pyautogui, pywinauto,
   keyboard, mouse, or any other library for UI interaction.  All automation
   MUST go through rpakit's public API.
2. **Follow the selector hierarchy.**  Each step includes a selector with up to
   four levels of specificity.  Always attempt selectors in this order:
   - `primary` (UIA AutomationId) -- most stable
   - `secondary` (structural UIA path)
   - `tertiary` (OCR anchor text)
   - `fallback` (raw screen coordinates) -- last resort
3. **Use variables.**  Any value prefixed with `$` is a workflow input.  Accept
   these as function parameters or read them from a config dict.
4. **Add waits.**  Before interacting with any element, call
   `rpakit.wait_for()` to ensure the element is visible and ready.
5. **Handle errors gracefully.**  Wrap interactions in try/except and use
   rpakit's retry helpers.
6. **Return only the Python script.**  No prose, no markdown fences.
"""


# ---------------------------------------------------------------------------
# SDK reference section
# ---------------------------------------------------------------------------

_SDK_REFERENCE = """\
## rpakit SDK Reference

```python
import rpakit

# -- Initialization --
app = rpakit.connect(title="Window Title")       # connect to a running app
app = rpakit.launch("path/to/app.exe")           # launch and connect

# -- Selectors --
# Build a selector from the IR's selector dict:
sel = rpakit.Selector(automation_id="myId")       # primary
sel = rpakit.Selector(uia_path="Window/Pane/Edit")  # secondary
sel = rpakit.Selector(ocr_text="Label Text", region=(x1, y1, x2, y2))  # tertiary
sel = rpakit.Selector(coords=(x, y))              # fallback

# -- Waits --
rpakit.wait_for(sel, timeout_ms=5000)             # block until element exists
rpakit.wait_until_gone(sel, timeout_ms=5000)      # block until element disappears

# -- Interactions --
rpakit.click(sel)                                 # left click
rpakit.double_click(sel)                          # double click
rpakit.right_click(sel)                           # right click
rpakit.fill(sel, "text value")                    # clear field and type text
rpakit.select_option(sel, "Option Label")         # select from dropdown / combo
rpakit.set_checkbox(sel, checked=True)            # check or uncheck
rpakit.scroll(sel, direction="down", amount=3)    # scroll inside element
rpakit.drag(from_sel, to_sel)                     # drag and drop
rpakit.press_keys("ctrl+c")                       # keyboard shortcut
rpakit.type_text("hello")                         # type without targeting

# -- Reading --
text = rpakit.extract_text(sel)                   # get element's text content
exists = rpakit.exists(sel)                       # bool check
value = rpakit.get_attribute(sel, "Value")        # read UIA attribute

# -- Control flow helpers --
rpakit.retry(fn, retries=3, delay_ms=1000)        # retry a callable
rpakit.loop(fn, times=5)                          # repeat a callable N times
```
"""


# ---------------------------------------------------------------------------
# Few-shot example loading from examples/ directory
# ---------------------------------------------------------------------------

# Location of curated examples (relative to this package)
_EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples")


def _load_all_examples() -> list[dict]:
    """Load all example pairs from the examples/ directory.

    Each subdirectory must contain ``ir.json`` and ``script.py``.
    Returns a list of dicts with keys: name, ir, ir_text, script, has_loop,
    has_conditional, step_count, has_extract.
    """
    examples: list[dict] = []
    if not os.path.isdir(_EXAMPLES_DIR):
        return examples

    for entry in sorted(os.listdir(_EXAMPLES_DIR)):
        subdir = os.path.join(_EXAMPLES_DIR, entry)
        ir_path = os.path.join(subdir, "ir.json")
        script_path = os.path.join(subdir, "script.py")
        if not os.path.isfile(ir_path) or not os.path.isfile(script_path):
            continue

        with open(ir_path, "r", encoding="utf-8") as f:
            ir_data = json.load(f)
        with open(script_path, "r", encoding="utf-8") as f:
            script_text = f.read()

        ir_text = json.dumps(ir_data, indent=2, ensure_ascii=False)

        # Extract features for similarity matching
        ops = _collect_ops(ir_data.get("steps", []))
        examples.append({
            "name": entry,
            "ir": ir_data,
            "ir_text": ir_text,
            "script": script_text,
            "has_loop": "loop" in ops,
            "has_conditional": "if_condition" in ops,
            "has_extract": "extract_text" in ops,
            "step_count": len(ir_data.get("steps", [])),
        })

    return examples


def _collect_ops(steps: list[dict]) -> set[str]:
    """Recursively collect all operation types from an IR step list."""
    ops: set[str] = set()
    for step in steps:
        ops.add(step.get("op", ""))
        for nested_key in ("body", "then_steps", "else_steps"):
            nested = step.get(nested_key, [])
            if nested:
                ops.update(_collect_ops(nested))
    return ops


def _select_examples(ir: dict, max_examples: int = 3) -> list[dict]:
    """Select the most relevant examples by similarity to the target IR.

    Similarity heuristic:
      - +3 if loop presence matches
      - +3 if conditional presence matches
      - +2 if extract_text presence matches
      - +1 if step count is within 3 of the target
    """
    all_examples = _load_all_examples()
    if not all_examples:
        return []

    target_ops = _collect_ops(ir.get("steps", []))
    target_has_loop = "loop" in target_ops
    target_has_cond = "if_condition" in target_ops
    target_has_extract = "extract_text" in target_ops
    target_step_count = len(ir.get("steps", []))

    scored: list[tuple[int, dict]] = []
    for ex in all_examples:
        score = 0
        if ex["has_loop"] == target_has_loop:
            score += 3
        if ex["has_conditional"] == target_has_cond:
            score += 3
        if ex["has_extract"] == target_has_extract:
            score += 2
        if abs(ex["step_count"] - target_step_count) <= 3:
            score += 1
        scored.append((score, ex))

    # Sort descending by score, take top N
    scored.sort(key=lambda t: t[0], reverse=True)
    return [ex for _, ex in scored[:max_examples]]


def _format_few_shot(ir: dict) -> str:
    """Build the few-shot examples section by selecting relevant examples."""
    examples = _select_examples(ir, max_examples=3)
    if not examples:
        # Fallback: no examples directory found
        return ""

    parts = ["## Examples\n"]
    for idx, ex in enumerate(examples, 1):
        parts.append(f"### Example {idx} -- {ex['name']}\n")
        parts.append(f"**IR:**\n```json\n{ex['ir_text']}\n```\n")
        parts.append(f"**Generated script:**\n```python\n{ex['script']}\n```\n")
        parts.append("---\n")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Assertion instructions for prompts
# ---------------------------------------------------------------------------

_ASSERTION_INSTRUCTIONS = """\
## Assertions

The IR includes an `assertions` list.  For each assertion, add a runtime
validation in the generated script at the appropriate point:

- **`field_has_value`**: After filling a field, read back its value with
  `rpakit.get_attribute(sel, "Value")` and assert it matches the expected value.
- **`element_visible`**: After a submit/save click, call `rpakit.wait_for(sel)`
  to confirm the expected next element appeared.
- **`output_not_empty`**: After extracting text, assert the result is truthy
  (non-empty string).

If an assertion fails, raise a descriptive ``AssertionError`` with the step id
and expected vs actual values.
"""


# ---------------------------------------------------------------------------
# IR formatting helpers
# ---------------------------------------------------------------------------

def _format_ir_section(ir: dict) -> str:
    """Format the IR dict as a markdown code block for the prompt."""
    ir_json = json.dumps(ir, indent=2, ensure_ascii=False)
    return f"""\
## Your Task

Convert the following workflow IR into a Python script using the rpakit SDK.

```json
{ir_json}
```

Generate the complete, runnable Python script now.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_prompt(ir: dict, include_screenshots: bool = False) -> str:
    """Build the full markdown prompt string from an IR dict.

    Parameters
    ----------
    ir : dict
        The workflow IR produced by ``IRCompiler.compile()``.
    include_screenshots : bool
        Placeholder flag.  When True a note is added indicating that
        screenshots are attached in the API payload (they cannot be
        embedded in plain text).

    Returns
    -------
    str
        The complete prompt ready to send to Claude Code.
    """
    few_shot = _format_few_shot(ir)
    sections = [
        _SYSTEM_RULES,
        _SDK_REFERENCE,
    ]
    if few_shot:
        sections.append(few_shot)
    # Include assertion instructions when the IR has assertions
    if ir.get("assertions"):
        sections.append(_ASSERTION_INSTRUCTIONS)
    sections.append(_format_ir_section(ir))

    if include_screenshots:
        sections.append(
            "**Note:** Screenshots of each step are attached as images in the "
            "message.  Use them to verify element locations and visual context.\n"
        )

    return "\n\n".join(sections)


def generate_api_payload(
    ir: dict,
    screenshots: list[str] | None = None,
) -> dict:
    """Build a Claude Messages API payload dict from an IR dict.

    Parameters
    ----------
    ir : dict
        The workflow IR produced by ``IRCompiler.compile()``.
    screenshots : list[str] | None
        Optional list of file paths to PNG screenshots to include as
        images in the message.

    Returns
    -------
    dict
        A dict with ``system``, ``messages``, and ``max_tokens`` keys,
        ready to pass to ``anthropic.Anthropic().messages.create(**payload)``.
    """
    include_screenshots = bool(screenshots)
    prompt_text = generate_prompt(ir, include_screenshots=include_screenshots)

    # Build the user message content blocks
    content: list[dict[str, Any]] = [
        {"type": "text", "text": prompt_text},
    ]

    # Attach screenshots if provided
    if screenshots:
        for img_path in screenshots:
            if not os.path.exists(img_path):
                continue
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            # Determine media type
            ext = os.path.splitext(img_path)[1].lower()
            media_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            media_type = media_map.get(ext, "image/png")
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64,
                },
            })

    return {
        "model": "claude-sonnet-4-6-20250514",
        "max_tokens": 8192,
        "system": _SYSTEM_RULES,
        "messages": [
            {"role": "user", "content": content},
        ],
    }

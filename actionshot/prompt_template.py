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
You are an expert desktop RPA engineer. You receive a declarative workflow IR
and generate a Python script using the rpakit SDK.

## MANDATORY RULES — violating any of these is a generation failure

1. **Use ONLY the rpakit SDK.** Never import pyautogui, pywinauto, keyboard,
   mouse, subprocess, or any other UI library. Every interaction goes through
   the `UI` class instance.

2. **The @run_workflow decorator is mandatory.** Every generated script must
   wrap the main function with `@rpakit.run_workflow("workflow_name")`.

3. **Selector hierarchy is handled by rpakit internally.** Pass the full
   selector dict from the IR directly to UI methods. Do NOT implement your own
   fallback logic, try/except chains for selectors, or manual resolution.
   rpakit.UI resolves primary → secondary → tertiary → fallback automatically.

4. **NEVER use time.sleep() as a fallback.** If ui.wait_for() fails, let the
   exception propagate. The @run_workflow decorator captures failure context
   automatically.

5. **NEVER fabricate success.** If the IR has an extract_text step, use
   ui.read() and return the extracted value. If the IR has NO extract_text
   step, return an empty dict `{}`. NEVER return `{"result": "success"}` or
   `{"result": "Login successful"}` — that is lying about verification.

6. **$variables become function parameters.** Any value prefixed with $ in the
   IR maps to a typed function parameter with the same name.

7. **Return ONLY the Python script.** No prose, no markdown fences, no
   explanation. Just the code.
"""


# ---------------------------------------------------------------------------
# SDK reference section
# ---------------------------------------------------------------------------

_SDK_REFERENCE = """\
## rpakit SDK Reference (EXACT public API — use nothing else)

```python
from actionshot.rpakit import UI, run_workflow, wait, log

# -- Initialization --
# UI.attach() is a classmethod that finds a window by title substring
ui = UI.attach("Window Title")

# -- Decorator (MANDATORY) --
@run_workflow("workflow_name")
def my_workflow(param1: str, param2: str) -> dict:
    ui = UI.attach("Window Title")
    # ... workflow steps ...
    return {"output_field": value}

# -- Selectors --
# Pass the IR's selector dict directly. rpakit resolves the hierarchy
# internally (primary → secondary → tertiary → fallback). Example:
selector = {
    "primary": {"method": "uia_automation_id", "value": "btnSave"},
    "secondary": {"method": "uia_path", "value": "Window/Pane/Button"},
    "tertiary": {"method": "ocr_anchor", "text": "Save"},
    "fallback": {"method": "coordinates", "x": 500, "y": 300}
}
# You can also pass a plain string for AutomationId: ui.click("btnSave")

# -- Interactions (all are methods on the ui instance) --
ui.click(selector)                    # click element (auto-retry 3x)
ui.fill(selector, "text value")       # clear + type into field
ui.select(selector, "Option Label")   # select from dropdown/combobox
ui.navigate(["Menu", "Submenu"])      # click through menu path
ui.scroll(selector, amount=3)         # scroll element
ui.drag(from_selector, to_selector)   # drag and drop

# -- Waits --
ui.wait_for(selector)                 # wait until element visible (default 10s timeout)

# -- Reading --
text = ui.read(selector)              # extract text from element

# -- Browser (if app is Chrome/Edge) --
result = ui.execute_js("document.title")

# -- Utilities (top-level, not on ui) --
wait(2, reason="page loading")        # explicit wait with reason (use sparingly)
log("Step completed")                 # structured log entry
```

## What NOT to do
- Do NOT call `rpakit.connect()`, `rpakit.Selector()`, `rpakit.exists()` — these do not exist
- Do NOT implement manual selector fallback logic — rpakit handles this
- Do NOT use `time.sleep()` — use `ui.wait_for()` or `wait()`
- Do NOT catch exceptions to retry selectors — rpakit retries internally
- Do NOT return `{"result": "success"}` without calling `ui.read()` to verify
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
        "model": "claude-sonnet-4-5-20250929",
        "max_tokens": 8192,
        "system": _SYSTEM_RULES,
        "messages": [
            {"role": "user", "content": content},
        ],
    }

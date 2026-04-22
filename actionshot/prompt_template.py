"""Prompt Template - generates structured prompts for Claude Code from workflow IR.

Provides two entry points:
  - ``generate_prompt(ir)``       -> full markdown prompt as a string
  - ``generate_api_payload(ir)``  -> Claude Messages API payload dict
"""

import base64
import json
import os
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
# Few-shot examples
# ---------------------------------------------------------------------------

_FEW_SHOT_EXAMPLES = """\
## Examples

### Example 1 -- Fill a form and submit

**IR (abbreviated):**
```json
{
  "inputs": [{"name": "username", "type": "string", "example": "jdoe"}],
  "steps": [
    {"id": 1, "op": "open_app", "target": "MyApp - Login"},
    {"id": 2, "op": "fill_field", "selector": {"primary": {"method": "uia_automation_id", "value": "txtUser"}}, "value": "$username"},
    {"id": 3, "op": "fill_field", "selector": {"primary": {"method": "uia_automation_id", "value": "txtPass"}}, "value": "$password"},
    {"id": 4, "op": "click", "selector": {"primary": {"method": "uia_automation_id", "value": "btnLogin"}}}
  ]
}
```

**Generated script:**
```python
import rpakit

def run(username: str, password: str):
    app = rpakit.connect(title="MyApp - Login")

    user_sel = rpakit.Selector(automation_id="txtUser")
    pass_sel = rpakit.Selector(automation_id="txtPass")
    login_sel = rpakit.Selector(automation_id="btnLogin")

    rpakit.wait_for(user_sel, timeout_ms=5000)
    rpakit.fill(user_sel, username)

    rpakit.wait_for(pass_sel, timeout_ms=5000)
    rpakit.fill(pass_sel, password)

    rpakit.wait_for(login_sel, timeout_ms=5000)
    rpakit.click(login_sel)

if __name__ == "__main__":
    run(username="jdoe", password="secret")
```

---

### Example 2 -- Loop over table rows

**IR (abbreviated):**
```json
{
  "inputs": [],
  "steps": [
    {"id": 1, "op": "open_app", "target": "Inventory Manager"},
    {"id": 2, "op": "loop", "iterations": 5, "body": [
      {"id": 3, "op": "click", "selector": {"tertiary": {"method": "ocr_anchor", "text": "Edit"}}},
      {"id": 4, "op": "fill_field", "selector": {"primary": {"method": "uia_automation_id", "value": "qtyField"}}, "value": "0"},
      {"id": 5, "op": "click", "selector": {"tertiary": {"method": "ocr_anchor", "text": "Save"}}}
    ]}
  ]
}
```

**Generated script:**
```python
import rpakit

def run():
    app = rpakit.connect(title="Inventory Manager")

    def update_row():
        edit_sel = rpakit.Selector(ocr_text="Edit")
        qty_sel = rpakit.Selector(automation_id="qtyField")
        save_sel = rpakit.Selector(ocr_text="Save")

        rpakit.wait_for(edit_sel, timeout_ms=5000)
        rpakit.click(edit_sel)

        rpakit.wait_for(qty_sel, timeout_ms=5000)
        rpakit.fill(qty_sel, "0")

        rpakit.wait_for(save_sel, timeout_ms=5000)
        rpakit.click(save_sel)

    rpakit.loop(update_row, times=5)

if __name__ == "__main__":
    run()
```

---

### Example 3 -- Select from dropdown and copy result

**IR (abbreviated):**
```json
{
  "inputs": [{"name": "department", "type": "string", "example": "Engineering"}],
  "steps": [
    {"id": 1, "op": "open_app", "target": "HR Portal"},
    {"id": 2, "op": "select_option", "selector": {"primary": {"method": "uia_automation_id", "value": "cboDept"}}, "option": "$department"},
    {"id": 3, "op": "click", "selector": {"tertiary": {"method": "ocr_anchor", "text": "Search"}}},
    {"id": 4, "op": "wait_for", "selector": {"primary": {"method": "uia_automation_id", "value": "resultsGrid"}}, "timeout_ms": 10000},
    {"id": 5, "op": "extract_text", "selector": {"primary": {"method": "uia_automation_id", "value": "lblTotal"}}}
  ]
}
```

**Generated script:**
```python
import rpakit

def run(department: str) -> str:
    app = rpakit.connect(title="HR Portal")

    dept_sel = rpakit.Selector(automation_id="cboDept")
    rpakit.wait_for(dept_sel, timeout_ms=5000)
    rpakit.select_option(dept_sel, department)

    search_sel = rpakit.Selector(ocr_text="Search")
    rpakit.wait_for(search_sel, timeout_ms=5000)
    rpakit.click(search_sel)

    grid_sel = rpakit.Selector(automation_id="resultsGrid")
    rpakit.wait_for(grid_sel, timeout_ms=10000)

    total_sel = rpakit.Selector(automation_id="lblTotal")
    rpakit.wait_for(total_sel, timeout_ms=5000)
    return rpakit.extract_text(total_sel)

if __name__ == "__main__":
    result = run(department="Engineering")
    print("Total:", result)
```
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
    sections = [
        _SYSTEM_RULES,
        _SDK_REFERENCE,
        _FEW_SHOT_EXAMPLES,
        _format_ir_section(ir),
    ]

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

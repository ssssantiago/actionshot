"""IR Compiler - transforms a curated recording session into a declarative Intermediate Representation.

The IR is a JSON structure that describes a workflow as a sequence of high-level
operations (click, fill_field, select_option, etc.) with selector hierarchies,
detected variables, and semantic groupings.  It serves as the bridge between raw
session recordings and code-generation prompts.
"""

import json
import os
import re
import uuid
from typing import Any


# ---------------------------------------------------------------------------
# Canonical IR operations
# ---------------------------------------------------------------------------

CANONICAL_OPS = frozenset({
    "open_app",
    "navigate",
    "click",
    "fill_field",
    "select_option",
    "set_checkbox",
    "wait_for",
    "extract_text",
    "keyboard_shortcut",
    "copy",
    "paste",
    "scroll",
    "drag",
    "if_condition",
    "loop",
    "custom_step",
})


# ---------------------------------------------------------------------------
# Heuristics for variable detection
# ---------------------------------------------------------------------------

# Patterns that suggest "data" rather than UI interaction text
_DATA_PATTERNS = [
    re.compile(r"^[^@\s]+@[^@\s]+\.\w+$"),           # email
    re.compile(r"^\d{2,4}[/-]\d{2}[/-]\d{2,4}$"),     # date
    re.compile(r"^\d{3}[\.\-]?\d{3}[\.\-]?\d{3}[\.\-]?\d{2}$"),  # CPF-like
    re.compile(r"^\d+[\.,]\d{2}$"),                    # currency / decimal
    re.compile(r"^\+?\d[\d\s\-]{7,}$"),                # phone number
    re.compile(r"^https?://"),                         # URL
    re.compile(r"\\\\|[A-Z]:\\"),                      # file path
]

# Short fixed UI strings that are NOT variables
_UI_KEYWORDS = {
    "ok", "cancel", "yes", "no", "apply", "close", "save", "open",
    "next", "back", "finish", "submit", "search", "enter", "tab",
    "delete", "copy", "paste", "cut", "undo", "redo", "select all",
}


def _looks_like_variable(text: str) -> bool:
    """Return True if *text* looks like user data rather than a UI label."""
    if not text or not text.strip():
        return False
    t = text.strip()
    if t.lower() in _UI_KEYWORDS:
        return False
    # Longer free-form text is likely data
    if len(t) > 30:
        return True
    for pat in _DATA_PATTERNS:
        if pat.match(t):
            return True
    # Mixed alpha + digits with length > 4 often indicates data
    if len(t) > 4 and any(c.isdigit() for c in t) and any(c.isalpha() for c in t):
        return True
    return False


def _slugify(text: str) -> str:
    """Turn a human string into a safe variable name."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    slug = slug.strip("_")
    return slug[:40] or "value"


# ---------------------------------------------------------------------------
# Selector builder
# ---------------------------------------------------------------------------

def _build_selector(step: dict) -> dict:
    """Build a selector dict from a step's target / element metadata."""
    target = step.get("target")
    element = step.get("element") or {}

    selector: dict[str, Any] = {}

    if target:
        if target.get("primary"):
            selector["primary"] = target["primary"]
        if target.get("secondary"):
            selector["secondary"] = target["secondary"]
        if target.get("tertiary"):
            selector["tertiary"] = target["tertiary"]
        if target.get("fallback"):
            selector["fallback"] = target["fallback"]
    else:
        # Fall back to element dict fields
        if element.get("automation_id"):
            selector["primary"] = {
                "method": "uia_automation_id",
                "value": element["automation_id"],
            }
        if element.get("name"):
            selector["tertiary"] = {
                "method": "ocr_anchor",
                "text": element["name"],
            }
        if step.get("position"):
            pos = step["position"]
            selector["fallback"] = {
                "method": "coordinates",
                "x": pos.get("x"),
                "y": pos.get("y"),
            }

    # Always include a human-readable label
    selector["label"] = element.get("name") or ""
    selector["control_type"] = element.get("control_type") or ""

    return selector


# ---------------------------------------------------------------------------
# Semantic grouping (raw steps -> IR steps)
# ---------------------------------------------------------------------------

class _StepGrouper:
    """Consumes raw metadata steps and emits higher-level IR operations."""

    def __init__(self, steps: list[dict]):
        self.raw = steps
        self.ir_steps: list[dict] = []
        self.variables: dict[str, dict] = {}  # name -> {type, example}
        self._next_id = 1

    def _id(self) -> int:
        sid = self._next_id
        self._next_id += 1
        return sid

    # -- helpers to register a detected variable --

    def _maybe_register_var(self, text: str, field_hint: str = "") -> str | None:
        """If *text* looks like data, register a variable and return ``$var``."""
        if not _looks_like_variable(text):
            return None
        name = _slugify(field_hint) if field_hint else _slugify(text[:20])
        # Avoid collisions
        base = name
        counter = 2
        while name in self.variables and self.variables[name]["example"] != text:
            name = f"{base}_{counter}"
            counter += 1
        self.variables[name] = {"type": "string", "example": text}
        return f"${name}"

    # -- pattern matchers --

    def _try_fill_field(self, i: int) -> int | None:
        """click + keypress => fill_field.  Returns steps consumed or None."""
        if i + 1 >= len(self.raw):
            return None
        step = self.raw[i]
        nxt = self.raw[i + 1]
        action = step.get("action", "")
        if not action.endswith("_click"):
            return None
        if nxt.get("action") != "keypress":
            return None

        element = step.get("element") or {}
        field_name = element.get("name", "field")
        typed_text = nxt.get("text", "")

        var_ref = self._maybe_register_var(typed_text, field_name)

        self.ir_steps.append({
            "id": self._id(),
            "op": "fill_field",
            "selector": _build_selector(step),
            "value": var_ref if var_ref else typed_text,
        })
        return 2

    def _try_select_option(self, i: int) -> int | None:
        """click dropdown/combobox + click item => select_option."""
        if i + 1 >= len(self.raw):
            return None
        step = self.raw[i]
        nxt = self.raw[i + 1]
        action = step.get("action", "")
        if not action.endswith("_click"):
            return None
        if not nxt.get("action", "").endswith("_click"):
            return None

        elem1 = step.get("element") or {}
        elem2 = nxt.get("element") or {}
        ct1 = elem1.get("control_type", "")
        ct2 = elem2.get("control_type", "")

        selectable = {"ComboBox", "MenuItem", "ListItem", "TreeItem", "List", "DropDown"}
        if ct1 not in selectable and ct2 not in selectable:
            return None
        # Both in the same window
        w1 = (step.get("window") or {}).get("title", "")
        w2 = (nxt.get("window") or {}).get("title", "")
        if w1 != w2:
            return None

        self.ir_steps.append({
            "id": self._id(),
            "op": "select_option",
            "selector": _build_selector(step),
            "option": elem2.get("name", ""),
        })
        return 2

    def _try_keyboard_shortcut(self, step: dict) -> bool:
        """Detect keyboard shortcuts (Ctrl+C, etc.) from keypress steps."""
        action = step.get("action", "")
        if action != "keypress":
            return False
        text = step.get("text", "")
        key = step.get("key", "")
        modifiers = step.get("modifiers") or []
        if not modifiers:
            return False

        combo = "+".join(modifiers) + "+" + (key or text)

        # Map common shortcuts to specific ops
        combo_lower = combo.lower()
        if combo_lower in ("ctrl+c", "control+c"):
            self.ir_steps.append({"id": self._id(), "op": "copy"})
        elif combo_lower in ("ctrl+v", "control+v"):
            self.ir_steps.append({"id": self._id(), "op": "paste"})
        else:
            self.ir_steps.append({
                "id": self._id(),
                "op": "keyboard_shortcut",
                "keys": combo,
            })
        return True

    # -- main grouping loop --

    def run(self) -> None:
        i = 0
        seen_app: str | None = None

        while i < len(self.raw):
            step = self.raw[i]
            action = step.get("action", "")

            # Detect app context change -> open_app
            window = step.get("window") or step.get("context") or {}
            app_title = window.get("title") or window.get("window_title") or ""
            if app_title and app_title != seen_app:
                self.ir_steps.append({
                    "id": self._id(),
                    "op": "open_app",
                    "target": app_title,
                })
                seen_app = app_title

            # Try multi-step patterns first
            consumed = self._try_fill_field(i)
            if consumed:
                i += consumed
                continue

            consumed = self._try_select_option(i)
            if consumed:
                i += consumed
                continue

            # Single-step patterns
            if self._try_keyboard_shortcut(step):
                i += 1
                continue

            # Scroll
            if step.get("scroll_dy") is not None:
                self.ir_steps.append({
                    "id": self._id(),
                    "op": "scroll",
                    "direction": step.get("direction", "down"),
                    "amount": step.get("scroll_dy", 0),
                    "selector": _build_selector(step),
                })
                i += 1
                continue

            # Drag
            if "drag_start" in step and "drag_end" in step:
                ds = step["drag_start"]
                de = step["drag_end"]
                self.ir_steps.append({
                    "id": self._id(),
                    "op": "drag",
                    "from": {"x": ds["x"], "y": ds["y"]},
                    "to": {"x": de["x"], "y": de["y"]},
                })
                i += 1
                continue

            # Checkbox toggle
            element = step.get("element") or {}
            if element.get("control_type") == "CheckBox" and action.endswith("_click"):
                self.ir_steps.append({
                    "id": self._id(),
                    "op": "set_checkbox",
                    "selector": _build_selector(step),
                    "checked": True,  # cannot infer toggle direction from a recording
                })
                i += 1
                continue

            # Generic click
            if action.endswith("_click"):
                self.ir_steps.append({
                    "id": self._id(),
                    "op": "click",
                    "selector": _build_selector(step),
                })
                i += 1
                continue

            # Plain keypress (not shortcut, not part of fill_field)
            if action == "keypress":
                typed = step.get("text", "")
                if typed:
                    var_ref = self._maybe_register_var(typed)
                    self.ir_steps.append({
                        "id": self._id(),
                        "op": "fill_field",
                        "selector": _build_selector(step),
                        "value": var_ref if var_ref else typed,
                    })
                i += 1
                continue

            # Fallback: custom_step
            self.ir_steps.append({
                "id": self._id(),
                "op": "custom_step",
                "raw_action": action,
                "description": step.get("description", ""),
                "selector": _build_selector(step),
            })
            i += 1


# ---------------------------------------------------------------------------
# Loop integration (from PatternDetector)
# ---------------------------------------------------------------------------

def _inject_loops(ir_steps: list[dict], loops: list[dict]) -> list[dict]:
    """Wrap repeated step ranges in ``loop`` operations.

    *loops* comes from ``PatternDetector.detect_loops()``.
    """
    if not loops:
        return ir_steps

    # Build a set of IR-step ids that fall inside a loop body
    loop_ranges: list[tuple[int, int, int]] = []  # (start_id, end_id, repeats)
    for loop in loops:
        start = loop.get("start_step", 0)
        end = loop.get("end_step", 0)
        repeats = loop.get("repeat_count", 2)
        loop_ranges.append((start, end, repeats))

    # For simplicity, wrap contiguous IR steps whose original raw-step ids
    # overlap with the detected loop range.  This is a best-effort heuristic.
    result: list[dict] = []
    used: set[int] = set()

    for lr_start, lr_end, repeats in loop_ranges:
        body: list[dict] = []
        for s in ir_steps:
            sid = s["id"]
            if lr_start <= sid <= lr_end and sid not in used:
                body.append(s)
                used.add(sid)
        if body:
            result.append({
                "id": body[0]["id"],
                "op": "loop",
                "iterations": repeats,
                "body": body,
            })

    # Add non-looped steps in original order
    for s in ir_steps:
        if s["id"] not in used:
            result.append(s)

    result.sort(key=lambda s: s["id"])
    return result


# ---------------------------------------------------------------------------
# Automatic assertion generation
# ---------------------------------------------------------------------------

# Button labels (Portuguese + English) that indicate a submit/save action
_SUBMIT_KEYWORDS = {"salvar", "enviar", "submit", "confirmar", "ok"}


def _is_submit_button(selector: dict) -> bool:
    """Return True if the selector targets a submit/save button."""
    label = (selector.get("label") or "").strip().lower()
    for kw in _SUBMIT_KEYWORDS:
        if kw in label:
            return True
    return False


def _generate_assertions(ir_steps: list[dict]) -> list[dict]:
    """Walk the IR steps and produce automatic assertions.

    Rules:
      - After a ``click`` on a submit/save button, assert that the next
        element in the workflow is visible (confirming a page/state transition).
      - After a ``fill_field``, assert the field holds the expected value.
      - After an ``extract_text``, assert the output is not empty.
    """
    assertions: list[dict] = []
    flat_steps = _flatten_steps(ir_steps)

    for idx, step in enumerate(flat_steps):
        op = step.get("op", "")
        step_id = step.get("id", idx + 1)

        if op == "click" and _is_submit_button(step.get("selector", {})):
            # Look ahead for the next step's selector to verify transition
            if idx + 1 < len(flat_steps):
                next_step = flat_steps[idx + 1]
                next_sel = next_step.get("selector", {})
                if next_sel:
                    assertions.append({
                        "after_step": step_id,
                        "check": "element_visible",
                        "selector": next_sel,
                    })

        elif op == "fill_field":
            selector = step.get("selector", {})
            value = step.get("value", "")
            if selector:
                assertions.append({
                    "after_step": step_id,
                    "check": "field_has_value",
                    "selector": selector,
                    "expected": value,
                })

        elif op == "extract_text":
            # Derive the output field name from the selector label
            selector = step.get("selector", {})
            field_name = _slugify(selector.get("label", "")) or "extracted_value"
            assertions.append({
                "after_step": step_id,
                "check": "output_not_empty",
                "field": field_name,
            })

    return assertions


def _flatten_steps(ir_steps: list[dict]) -> list[dict]:
    """Flatten loop bodies so assertions can reference all steps linearly."""
    flat: list[dict] = []
    for step in ir_steps:
        if step.get("op") == "loop" and "body" in step:
            flat.extend(step["body"])
        else:
            flat.append(step)
    return flat


# ---------------------------------------------------------------------------
# Public compiler class
# ---------------------------------------------------------------------------

class IRCompiler:
    """Compile a recorded session into a declarative IR JSON."""

    def __init__(self, session_path: str):
        self.session_path = session_path
        self.steps: list[dict] = []
        self.session_name: str = ""
        self._load()

    # -- loading --

    def _load(self):
        summary_path = os.path.join(self.session_path, "session_summary.json")
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)

        self.session_name = summary.get("session", "unnamed_session")

        for step_info in summary["steps"]:
            step_num = step_info["step"]
            meta_path = os.path.join(
                self.session_path, f"{step_num:03d}_metadata.json"
            )
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.steps.append(json.load(f))

    # -- compile --

    def compile(self, detect_loops: bool = True) -> dict:
        """Run the full compilation pipeline and return the IR dict.

        Steps:
          1. Semantic grouping (click+type -> fill_field, etc.)
          2. Variable detection
          3. Loop detection (optional, requires PatternDetector)
          4. Build final IR JSON
        """
        grouper = _StepGrouper(self.steps)
        grouper.run()

        ir_steps = grouper.ir_steps
        variables = grouper.variables

        # Optionally integrate loop detection from PatternDetector
        if detect_loops:
            try:
                from actionshot.patterns import PatternDetector
                pd = PatternDetector(self.session_path)
                loops = pd.detect_loops()
                ir_steps = _inject_loops(ir_steps, loops)
            except Exception:
                pass  # loop detection is best-effort

        # Build inputs / outputs from detected variables
        inputs = [
            {"name": name, "type": info["type"], "example": info["example"]}
            for name, info in variables.items()
        ]

        # Generate automatic assertions
        assertions = _generate_assertions(ir_steps)

        ir: dict[str, Any] = {
            "workflow_id": _slugify(self.session_name) or f"workflow_{uuid.uuid4().hex[:8]}",
            "description": f"Auto-generated from session recording: {self.session_name}",
            "inputs": inputs,
            "outputs": [{"name": "result", "type": "string"}],
            "steps": ir_steps,
            "assertions": assertions,
        }

        return ir

    def compile_and_save(self, output_path: str | None = None) -> str:
        """Compile and write the IR JSON to disk.  Returns the output path."""
        ir = self.compile()

        if output_path is None:
            output_path = os.path.join(self.session_path, "workflow_ir.json")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(ir, f, indent=2, ensure_ascii=False)

        print(f"  IR compiled: {output_path}")
        print(f"  Steps: {len(ir['steps'])}  |  Variables: {len(ir['inputs'])}")
        return output_path

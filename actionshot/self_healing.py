"""Self-Healing System - captures failures, diagnoses patterns, and applies fixes.

When an RPA workflow step fails at runtime, this module:
  1. Captures a rich failure context package (screenshot, UIA tree, env info)
  2. Matches the failure against a catalog of known patterns
  3. Applies automatic fixes for known patterns, or generates an AI-assisted
     fix prompt for unknown failures
  4. Tracks healing history for continuous improvement

Usage::

    from actionshot.self_healing import FailureCapture, SelfHealingLoop

    capture = FailureCapture()
    pkg = capture.capture(exception, workflow_id, step_spec, last_steps)

    healer = SelfHealingLoop()
    diagnosis = healer.diagnose(pkg)
    fixed_ir = healer.auto_fix(pkg) or healer.request_ai_fix(pkg, ir, script)
"""

from __future__ import annotations

import copy
import datetime
import json
import locale
import os
import platform
import sys
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional dependency imports
# ---------------------------------------------------------------------------

try:
    from pywinauto import Desktop
    _HAS_PYWINAUTO = True
except ImportError:
    _HAS_PYWINAUTO = False

try:
    from actionshot.capture import take_screenshot
except ImportError:
    take_screenshot = None  # type: ignore[assignment]

try:
    import ctypes
    _HAS_CTYPES = True
except ImportError:
    _HAS_CTYPES = False


# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------

_HEALING_DIR = Path(os.environ.get("ACTIONSHOT_HEALING_DIR", "./healing_data"))
_HEALING_DIR.mkdir(parents=True, exist_ok=True)
_FAILURE_DIR = _HEALING_DIR / "failures"
_FAILURE_DIR.mkdir(parents=True, exist_ok=True)
_SCREENSHOT_DIR = _HEALING_DIR / "screenshots"
_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# KnownPatternCatalog
# ---------------------------------------------------------------------------

class KnownPatternCatalog:
    """Registry of common RPA failure patterns with automatic fix strategies.

    Each pattern entry contains:
      - ``match``: callable that accepts a failure package and returns True/False
      - ``fix``: the fix strategy name
      - ``description``: human-readable explanation
      - ``confidence``: float 0-1 indicating how reliable the auto-fix is
    """

    PATTERNS: dict[str, dict[str, Any]] = {
        "selector_not_found": {
            "description": (
                "Primary selector could not locate the target element, but a "
                "secondary or fallback selector may still work."
            ),
            "fix": "promote_secondary",
            "confidence": 0.85,
            "match_exception_types": {"LookupError", "SelectorNotFound", "ElementNotFoundError"},
        },
        "timeout_exceeded": {
            "description": (
                "The operation timed out waiting for an element or condition."
            ),
            "fix": "double_timeout",
            "confidence": 0.70,
            "match_exception_types": {"TimeoutError", "TimeoutExpired"},
        },
        "unexpected_modal": {
            "description": (
                "An unexpected modal dialog appeared and blocked the target "
                "element from being interacted with."
            ),
            "fix": "dismiss_and_retry",
            "confidence": 0.60,
            "match_keywords": ["modal", "dialog", "popup", "blocked", "not enabled"],
        },
        "resolution_mismatch": {
            "description": (
                "Coordinate-based selectors landed on the wrong location, "
                "likely due to a resolution or DPI scaling change."
            ),
            "fix": "recalibrate_coords",
            "confidence": 0.75,
            "match_keywords": ["coordinates", "coords", "outside", "offscreen"],
        },
        "window_not_active": {
            "description": (
                "The target window was not found or not in the foreground."
            ),
            "fix": "wait_for_window",
            "confidence": 0.80,
            "match_exception_types": {"TimeoutError"},
            "match_keywords": ["window", "not found", "no window", "not visible"],
        },
    }

    @classmethod
    def match(cls, failure_package: dict) -> str | None:
        """Return the pattern name that best matches *failure_package*, or None."""
        exc_info = failure_package.get("exception", {})
        exc_type = exc_info.get("type", "")
        exc_message = exc_info.get("message", "").lower()

        # Score each pattern and return the best match
        best_pattern: str | None = None
        best_score: float = 0.0

        for name, pattern in cls.PATTERNS.items():
            score = 0.0

            # Check exception type match
            match_types = pattern.get("match_exception_types", set())
            if exc_type in match_types:
                score += 2.0

            # Check keyword match in exception message
            match_keywords = pattern.get("match_keywords", [])
            keyword_hits = sum(1 for kw in match_keywords if kw.lower() in exc_message)
            if match_keywords:
                score += keyword_hits / len(match_keywords)

            # Check attempted selectors for selector-specific patterns
            if name == "selector_not_found":
                attempted = exc_info.get("attempted_selectors", [])
                if attempted and all(s.get("result") == "not_found" for s in attempted):
                    score += 1.5

            if name == "resolution_mismatch":
                step_spec = failure_package.get("step_spec", {})
                selector = step_spec.get("selector", {})
                fallback = selector.get("fallback", {})
                if fallback.get("method") == "coordinates" or "coords" in str(fallback):
                    score += 1.0

            if name == "window_not_active":
                step_spec = failure_package.get("step_spec", {})
                op = step_spec.get("op", "")
                if op == "open_app":
                    score += 1.0

            if score > best_score:
                best_score = score
                best_pattern = name

        # Require a minimum confidence threshold
        if best_score < 0.5:
            return None
        return best_pattern

    @classmethod
    def get_fix_strategy(cls, pattern_name: str) -> str | None:
        """Return the fix strategy string for a known pattern."""
        pattern = cls.PATTERNS.get(pattern_name)
        if pattern:
            return pattern["fix"]
        return None

    @classmethod
    def get_description(cls, pattern_name: str) -> str:
        """Return the human-readable description for a known pattern."""
        pattern = cls.PATTERNS.get(pattern_name)
        if pattern:
            return pattern["description"]
        return "Unknown pattern"


# ---------------------------------------------------------------------------
# FailureCapture
# ---------------------------------------------------------------------------

class FailureCapture:
    """Captures rich failure context when an RPA step fails at runtime."""

    def capture(
        self,
        exception: Exception,
        workflow_id: str,
        step_spec: dict,
        last_steps: list[dict] | None = None,
    ) -> dict:
        """Build and persist a failure context package.

        Parameters
        ----------
        exception : Exception
            The exception raised by rpakit during step execution.
        workflow_id : str
            Identifier of the workflow that was running.
        step_spec : dict
            The IR step dict that failed.
        last_steps : list[dict] | None
            The last N successful steps with their evidence (screenshots, etc.).

        Returns
        -------
        dict
            The complete failure package, also saved as JSON on disk.
        """
        failure_id = uuid.uuid4().hex

        # Capture screenshot at failure time
        screenshot_path = self._capture_screenshot(failure_id)

        # Capture UIA tree for the active window
        window_title = self._infer_window_title(step_spec)
        uia_tree = self.dump_uia_tree(window_title)

        # Build attempted selectors from exception and step spec
        attempted_selectors = self._extract_attempted_selectors(exception, step_spec)

        package: dict[str, Any] = {
            "failure_id": failure_id,
            "workflow_id": workflow_id,
            "failed_step_id": step_spec.get("id"),
            "step_spec": step_spec,
            "exception": {
                "type": type(exception).__name__,
                "message": str(exception),
                "attempted_selectors": attempted_selectors,
            },
            "screenshot_at_failure": screenshot_path,
            "uia_tree_at_failure": uia_tree,
            "last_successful_steps": (last_steps or [])[-3:],
            "runtime_env": self.get_runtime_env(),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec="milliseconds"
            ),
        }

        # Persist to disk
        failure_path = _FAILURE_DIR / f"{failure_id}.json"
        try:
            with open(failure_path, "w", encoding="utf-8") as fh:
                json.dump(package, fh, indent=2, default=str, ensure_ascii=False)
        except Exception:
            pass  # never let persistence break the caller

        return package

    # -- helpers --------------------------------------------------------------

    def dump_uia_tree(self, window_title: str | None) -> dict:
        """Dump the UIA element tree for the window matching *window_title*.

        Returns a nested dict representing the element hierarchy, or an empty
        dict if pywinauto is unavailable or the window cannot be found.
        """
        if not _HAS_PYWINAUTO or not window_title:
            return {}

        try:
            desktop = Desktop(backend="uia")
            for win in desktop.windows():
                try:
                    title = win.window_text()
                except Exception:
                    continue
                if window_title.lower() in title.lower():
                    return self._walk_element(win, depth=0, max_depth=5)
        except Exception:
            pass
        return {}

    def get_runtime_env(self) -> dict:
        """Collect OS, resolution, DPI scaling, and locale information."""
        env: dict[str, Any] = {
            "os": f"{platform.system()} {platform.release()} ({platform.version()})",
            "python": platform.python_version(),
            "machine": platform.machine(),
            "locale": self._get_locale(),
        }

        # Screen resolution
        env["resolution"] = self._get_resolution()

        # DPI scaling
        env["dpi_scaling"] = self._get_dpi_scaling()

        return env

    # -- private helpers -------------------------------------------------------

    @staticmethod
    def _capture_screenshot(label: str) -> str | None:
        """Take a screenshot and save it.  Returns path or None."""
        if take_screenshot is None:
            return None
        try:
            img = take_screenshot()
            fname = f"failure_{label}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            path = _SCREENSHOT_DIR / fname
            img.save(str(path))
            return str(path)
        except Exception:
            return None

    @staticmethod
    def _infer_window_title(step_spec: dict) -> str | None:
        """Try to extract a window title hint from the step spec."""
        # open_app steps have a direct target
        if step_spec.get("op") == "open_app":
            return step_spec.get("target")
        # selector may carry a label
        selector = step_spec.get("selector", {})
        label = selector.get("label")
        if label:
            return label
        return None

    @staticmethod
    def _extract_attempted_selectors(exception: Exception, step_spec: dict) -> list[dict]:
        """Build a list of selector attempts from the step spec and exception."""
        selectors: list[dict] = []
        selector = step_spec.get("selector", {})

        for level in ("primary", "secondary", "tertiary", "fallback"):
            sel_value = selector.get(level)
            if sel_value is not None:
                selectors.append({
                    "level": level,
                    "value": sel_value,
                    "result": "not_found",
                })

        return selectors

    def _walk_element(self, element: Any, depth: int, max_depth: int) -> dict:
        """Recursively walk a UIA element tree into a dict."""
        if depth > max_depth:
            return {"truncated": True}

        node: dict[str, Any] = {}
        try:
            node["control_type"] = element.element_info.control_type
        except Exception:
            node["control_type"] = ""
        try:
            node["name"] = element.element_info.name
        except Exception:
            node["name"] = ""
        try:
            node["automation_id"] = element.element_info.automation_id
        except Exception:
            node["automation_id"] = ""
        try:
            rect = element.element_info.rectangle
            node["rect"] = {
                "left": rect.left, "top": rect.top,
                "right": rect.right, "bottom": rect.bottom,
            }
        except Exception:
            pass

        # Children
        try:
            children = element.children()
            if children:
                node["children"] = [
                    self._walk_element(child, depth + 1, max_depth)
                    for child in children[:50]  # cap to avoid huge trees
                ]
        except Exception:
            pass

        return node

    @staticmethod
    def _get_locale() -> str:
        try:
            return locale.getlocale()[0] or locale.getdefaultlocale()[0] or "unknown"
        except Exception:
            return "unknown"

    @staticmethod
    def _get_resolution() -> str:
        if _HAS_CTYPES and platform.system() == "Windows":
            try:
                user32 = ctypes.windll.user32  # type: ignore[attr-defined]
                w = user32.GetSystemMetrics(0)
                h = user32.GetSystemMetrics(1)
                return f"{w}x{h}"
            except Exception:
                pass
        return "unknown"

    @staticmethod
    def _get_dpi_scaling() -> float:
        if _HAS_CTYPES and platform.system() == "Windows":
            try:
                # SetProcessDPIAware to get real metrics
                ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
                hdc = ctypes.windll.user32.GetDC(0)  # type: ignore[attr-defined]
                dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
                ctypes.windll.user32.ReleaseDC(0, hdc)  # type: ignore[attr-defined]
                return round(dpi / 96.0, 2)
            except Exception:
                pass
        return 1.0


# ---------------------------------------------------------------------------
# SelfHealingLoop
# ---------------------------------------------------------------------------

class SelfHealingLoop:
    """Diagnoses RPA failures and applies automatic or AI-assisted fixes."""

    def __init__(self) -> None:
        self.healing_history: list[dict] = []

    # -- public API -----------------------------------------------------------

    def diagnose(self, failure_package: dict) -> dict:
        """Identify the failure pattern and return a diagnosis dict.

        Returns
        -------
        dict
            Keys: ``pattern`` (str or None), ``description``, ``fix_strategy``,
            ``confidence``, ``auto_fixable`` (bool).
        """
        pattern_name = KnownPatternCatalog.match(failure_package)

        if pattern_name is None:
            return {
                "pattern": None,
                "description": "Unknown failure pattern - AI assistance recommended.",
                "fix_strategy": None,
                "confidence": 0.0,
                "auto_fixable": False,
            }

        pattern = KnownPatternCatalog.PATTERNS[pattern_name]
        return {
            "pattern": pattern_name,
            "description": pattern["description"],
            "fix_strategy": pattern["fix"],
            "confidence": pattern["confidence"],
            "auto_fixable": True,
        }

    def auto_fix(self, failure_package: dict) -> dict | None:
        """Attempt an automatic fix for a known failure pattern.

        Returns the patched IR step dict, or None if no auto-fix is possible.
        """
        diagnosis = self.diagnose(failure_package)
        if not diagnosis["auto_fixable"]:
            return None

        strategy = diagnosis["fix_strategy"]
        step_spec = copy.deepcopy(failure_package.get("step_spec", {}))

        fix_fn = {
            "promote_secondary": self._fix_promote_secondary,
            "double_timeout": self._fix_double_timeout,
            "dismiss_and_retry": self._fix_dismiss_and_retry,
            "recalibrate_coords": self._fix_recalibrate_coords,
            "wait_for_window": self._fix_wait_for_window,
        }.get(strategy)

        if fix_fn is None:
            return None

        fixed_step = fix_fn(step_spec, failure_package)

        # Record in history
        self._record_healing(failure_package, diagnosis, fixed_step)

        return fixed_step

    def request_ai_fix(
        self,
        failure_package: dict,
        ir: dict,
        script: str,
    ) -> str:
        """Generate a prompt for Claude requesting a minimal-diff fix.

        Parameters
        ----------
        failure_package : dict
            The failure context captured by ``FailureCapture``.
        ir : dict
            The full workflow IR.
        script : str
            The generated Python script that failed.

        Returns
        -------
        str
            A prompt string ready to send to Claude for fix generation.
        """
        exc_info = failure_package.get("exception", {})
        step_spec = failure_package.get("step_spec", {})
        runtime_env = failure_package.get("runtime_env", {})
        last_steps = failure_package.get("last_successful_steps", [])
        uia_tree = failure_package.get("uia_tree_at_failure", {})

        # Include healing history for context
        relevant_history = [
            h for h in self.healing_history
            if h.get("workflow_id") == failure_package.get("workflow_id")
        ]

        prompt = f"""\
You are an expert RPA debugging engineer.  A desktop automation workflow has
failed at runtime.  Your job is to produce a MINIMAL diff fix -- change as
little as possible to make the workflow succeed.

## Failure Context

**Workflow ID:** {failure_package.get('workflow_id', 'unknown')}
**Failed Step ID:** {failure_package.get('failed_step_id', '?')}
**Exception:** {exc_info.get('type', 'Unknown')}: {exc_info.get('message', '')}

### Attempted Selectors
```json
{json.dumps(exc_info.get('attempted_selectors', []), indent=2)}
```

### Failed Step Spec
```json
{json.dumps(step_spec, indent=2)}
```

### Last 3 Successful Steps
```json
{json.dumps(last_steps, indent=2)}
```

### Runtime Environment
```json
{json.dumps(runtime_env, indent=2)}
```

### UIA Element Tree at Failure (truncated)
```json
{json.dumps(uia_tree, indent=2, default=str)[:3000]}
```

## Full Workflow IR
```json
{json.dumps(ir, indent=2, ensure_ascii=False)[:5000]}
```

## Current Script (excerpt around failure)
```python
{script[:4000]}
```

## Previous Healing Attempts for This Workflow
```json
{json.dumps(relevant_history[-5:], indent=2, default=str) if relevant_history else '[]'}
```

## Instructions

1. Analyze the failure context, UIA tree, and previous healing attempts.
2. Identify the root cause of the failure.
3. Produce a fix as a JSON object with this structure:
   ```json
   {{
     "fix_type": "ir_patch" | "script_patch",
     "description": "Short explanation of the fix",
     "changes": [
       {{
         "step_id": <int>,
         "field": "<field to change>",
         "old_value": <current value>,
         "new_value": <fixed value>
       }}
     ]
   }}
   ```
4. If the fix requires adding a new step (e.g., a wait or dismiss), include it
   with ``"action": "insert_before"`` or ``"action": "insert_after"`` and the
   full new step spec.
5. Keep changes minimal.  Do NOT rewrite the entire workflow.
"""
        return prompt

    def apply_fix(self, fix_diff: dict, ir: dict) -> dict:
        """Apply a fix diff (from auto_fix or AI) to the workflow IR.

        Parameters
        ----------
        fix_diff : dict
            A dict with ``changes`` list, where each change specifies
            ``step_id``, ``field``, ``old_value``, ``new_value`` and optionally
            ``action`` (``insert_before`` / ``insert_after``).
        ir : dict
            The workflow IR to patch.

        Returns
        -------
        dict
            A new IR dict with the fixes applied.
        """
        patched_ir = copy.deepcopy(ir)
        steps = patched_ir.get("steps", [])
        changes = fix_diff.get("changes", [])

        # Sort insertions so we process from high step_id to low (to preserve indices)
        insertions = [c for c in changes if c.get("action") in ("insert_before", "insert_after")]
        modifications = [c for c in changes if c.get("action") not in ("insert_before", "insert_after")]

        # Apply field modifications
        for change in modifications:
            target_id = change.get("step_id")
            field = change.get("field")
            new_value = change.get("new_value")

            for step in steps:
                if step.get("id") == target_id and field:
                    self._set_nested_field(step, field, new_value)
                    break

        # Apply insertions (reverse order to preserve indices)
        insertions.sort(key=lambda c: c.get("step_id", 0), reverse=True)
        for change in insertions:
            target_id = change.get("step_id")
            action = change.get("action")
            new_step = change.get("new_value", {})

            for i, step in enumerate(steps):
                if step.get("id") == target_id:
                    if action == "insert_before":
                        steps.insert(i, new_step)
                    elif action == "insert_after":
                        steps.insert(i + 1, new_step)
                    break

        # Re-number step IDs to keep them sequential
        for idx, step in enumerate(steps, start=1):
            step["id"] = idx

        patched_ir["steps"] = steps
        return patched_ir

    # -- fix strategies -------------------------------------------------------

    @staticmethod
    def _fix_promote_secondary(step_spec: dict, failure_package: dict) -> dict:
        """Promote secondary selector to primary when primary fails."""
        selector = step_spec.get("selector", {})

        # Shift each level up
        if "secondary" in selector:
            selector["primary"] = selector.pop("secondary")
        if "tertiary" in selector:
            selector["secondary"] = selector.pop("tertiary")
        if "fallback" in selector:
            if "secondary" not in selector:
                selector["secondary"] = selector.pop("fallback")
            elif "tertiary" not in selector:
                selector["tertiary"] = selector.pop("fallback")

        step_spec["selector"] = selector
        step_spec["_healed"] = True
        step_spec["_heal_strategy"] = "promote_secondary"
        return step_spec

    @staticmethod
    def _fix_double_timeout(step_spec: dict, failure_package: dict) -> dict:
        """Double the timeout value, capped at 30 seconds."""
        MAX_TIMEOUT_MS = 30000
        MAX_TIMEOUT_S = 30.0

        # Handle timeout_ms field (IR-level)
        current_ms = step_spec.get("timeout_ms", 5000)
        new_ms = min(current_ms * 2, MAX_TIMEOUT_MS)
        step_spec["timeout_ms"] = new_ms

        # Handle timeout field in seconds (runtime-level)
        current_s = step_spec.get("timeout")
        if current_s is not None:
            new_s = min(float(current_s) * 2, MAX_TIMEOUT_S)
            step_spec["timeout"] = new_s

        step_spec["_healed"] = True
        step_spec["_heal_strategy"] = "double_timeout"
        return step_spec

    @staticmethod
    def _fix_dismiss_and_retry(step_spec: dict, failure_package: dict) -> dict:
        """Insert a dismiss_modal action before retrying the step.

        Returns the step wrapped with a pre-action to dismiss modals.
        """
        step_spec["pre_actions"] = step_spec.get("pre_actions", [])
        step_spec["pre_actions"].append({
            "op": "dismiss_modal",
            "strategies": [
                {"method": "send_keys", "keys": "Escape"},
                {"method": "click_button", "button_names": ["OK", "Close", "Cancel", "Yes", "No"]},
            ],
        })
        step_spec["_healed"] = True
        step_spec["_heal_strategy"] = "dismiss_and_retry"
        return step_spec

    @staticmethod
    def _fix_recalibrate_coords(step_spec: dict, failure_package: dict) -> dict:
        """Recalibrate coordinate-based selectors using current resolution."""
        runtime_env = failure_package.get("runtime_env", {})
        current_res = runtime_env.get("resolution", "")
        current_dpi = runtime_env.get("dpi_scaling", 1.0)

        selector = step_spec.get("selector", {})

        # Look for coordinate-based selectors at any level
        for level in ("primary", "secondary", "tertiary", "fallback"):
            sel = selector.get(level, {})
            if not isinstance(sel, dict):
                continue

            if sel.get("method") == "coordinates" or "x" in sel or "coords" in sel:
                # Parse the recorded resolution if available in step metadata
                recorded_res = step_spec.get("_recorded_resolution", "")

                if recorded_res and current_res and recorded_res != current_res:
                    try:
                        rec_w, rec_h = map(int, recorded_res.split("x"))
                        cur_w, cur_h = map(int, current_res.split("x"))
                        scale_x = cur_w / rec_w
                        scale_y = cur_h / rec_h
                    except (ValueError, ZeroDivisionError):
                        scale_x = scale_y = 1.0
                else:
                    # If we don't know the recorded resolution, apply DPI correction
                    scale_x = scale_y = 1.0 / current_dpi if current_dpi else 1.0

                # Scale x/y coordinates
                if "x" in sel and "y" in sel:
                    sel["x"] = round(sel["x"] * scale_x)
                    sel["y"] = round(sel["y"] * scale_y)
                if "coords" in sel:
                    x, y = sel["coords"]
                    sel["coords"] = (round(x * scale_x), round(y * scale_y))

                selector[level] = sel

        step_spec["selector"] = selector
        step_spec["_healed"] = True
        step_spec["_heal_strategy"] = "recalibrate_coords"
        step_spec["_recalibrated_for"] = current_res
        return step_spec

    @staticmethod
    def _fix_wait_for_window(step_spec: dict, failure_package: dict) -> dict:
        """Insert a wait_for_window pre-action before the failing step."""
        window_title = step_spec.get("target", "")
        if not window_title:
            selector = step_spec.get("selector", {})
            window_title = selector.get("label", "")

        step_spec["pre_actions"] = step_spec.get("pre_actions", [])
        step_spec["pre_actions"].append({
            "op": "wait_for_window",
            "title": window_title,
            "timeout_ms": 15000,
        })

        # Also bump the step's own timeout
        current_timeout = step_spec.get("timeout_ms", 5000)
        step_spec["timeout_ms"] = min(current_timeout + 5000, 30000)

        step_spec["_healed"] = True
        step_spec["_heal_strategy"] = "wait_for_window"
        return step_spec

    # -- helpers --------------------------------------------------------------

    def _record_healing(self, failure_package: dict, diagnosis: dict, fixed_step: dict) -> None:
        """Track the healing action in history."""
        record = {
            "failure_id": failure_package.get("failure_id"),
            "workflow_id": failure_package.get("workflow_id"),
            "failed_step_id": failure_package.get("failed_step_id"),
            "pattern": diagnosis.get("pattern"),
            "fix_strategy": diagnosis.get("fix_strategy"),
            "confidence": diagnosis.get("confidence"),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "fixed_step": fixed_step,
        }
        self.healing_history.append(record)

    @staticmethod
    def _set_nested_field(obj: dict, field_path: str, value: Any) -> None:
        """Set a potentially dot-separated field path on a dict.

        Example: ``_set_nested_field(step, "selector.primary.value", "newId")``
        """
        parts = field_path.split(".")
        target = obj
        for part in parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value


# ---------------------------------------------------------------------------
# AutoHealingRunner
# ---------------------------------------------------------------------------

class AutoHealingRunner:
    """Runs a workflow with automatic self-healing on failure.

    Executes a generated RPA script and, when it fails, captures failure
    context, diagnoses the issue, applies a fix (automatic or AI-assisted),
    regenerates the script, and retries -- up to *max_healing_cycles* times.
    """

    def __init__(
        self,
        workflow_id: str,
        ir: dict,
        script_path: str,
        max_healing_cycles: int = 3,
    ) -> None:
        self.workflow_id = workflow_id
        self.ir = copy.deepcopy(ir)
        self.script_path = script_path
        self.max_healing_cycles = max_healing_cycles

        self._capture = FailureCapture()
        self._healer = SelfHealingLoop()
        self.healing_history: list[dict] = []

    # -- public API -----------------------------------------------------------

    def run(self, inputs: dict) -> dict:
        """Execute workflow. On failure, capture context -> diagnose -> fix -> retry.

        Loop: execute -> fail -> capture -> diagnose -> auto_fix or ai_fix ->
              patch IR -> regenerate script -> retry -> success or give up

        Returns
        -------
        dict
            A result dict with keys ``status``, ``output`` (on success),
            ``healing_history``, and ``cycles_used``.
        """
        current_ir = copy.deepcopy(self.ir)
        current_script = self.script_path
        last_steps: list[dict] = []

        for cycle in range(self.max_healing_cycles + 1):
            is_retry = cycle > 0
            try:
                output = self._execute_script(current_script, inputs)
                result: dict[str, Any] = {
                    "status": "success",
                    "output": output,
                    "healing_history": self.healing_history,
                    "cycles_used": cycle,
                }
                if is_retry and self.healing_history:
                    winning = self.healing_history[-1]
                    result["healed_by"] = winning.get("fix_strategy") or "ai_fix"
                    _write_healing_log(
                        self.workflow_id,
                        f"Healed after {cycle} cycle(s) via "
                        f"{result['healed_by']}",
                    )
                return result

            except Exception as exc:
                # No more healing budget -- give up
                if cycle >= self.max_healing_cycles:
                    self._notify_give_up(exc)
                    return {
                        "status": "failed",
                        "error": str(exc),
                        "healing_history": self.healing_history,
                        "cycles_used": cycle,
                    }

                # --- Capture -------------------------------------------------
                step_spec = self._guess_failed_step(exc, current_ir)
                failure_pkg = self._capture.capture(
                    exception=exc,
                    workflow_id=self.workflow_id,
                    step_spec=step_spec,
                    last_steps=last_steps,
                )

                # --- Diagnose ------------------------------------------------
                diagnosis = self._healer.diagnose(failure_pkg)

                # --- Fix -----------------------------------------------------
                fix_diff: dict | None = None
                fix_source = "none"

                if diagnosis["auto_fixable"]:
                    fixed_step = self._healer.auto_fix(failure_pkg)
                    if fixed_step is not None:
                        fix_diff = {
                            "fix_type": "ir_patch",
                            "description": diagnosis["description"],
                            "changes": [{
                                "step_id": fixed_step.get("id"),
                                "field": "step_spec",
                                "old_value": step_spec,
                                "new_value": fixed_step,
                            }],
                        }
                        fix_source = diagnosis.get("fix_strategy", "auto")

                if fix_diff is None:
                    # AI-assisted fix path
                    script_text = self._read_script(current_script)
                    prompt = self._healer.request_ai_fix(
                        failure_pkg, current_ir, script_text,
                    )
                    fix_diff = self._call_ai_for_fix(prompt)
                    fix_source = "ai_fix"

                if fix_diff is None:
                    # Could not produce any fix -- record and continue to
                    # exhaust cycles so the give-up notification fires.
                    self._record_cycle(cycle, diagnosis, fix_source, success=False)
                    continue

                # --- Patch IR & regenerate script ----------------------------
                current_ir = self._healer.apply_fix(fix_diff, current_ir)
                current_script = self._patch_and_regenerate(current_ir, fix_diff)

                self._record_cycle(cycle, diagnosis, fix_source, success=None)

        # Should not reach here, but just in case
        return {
            "status": "failed",
            "error": "Exhausted healing cycles",
            "healing_history": self.healing_history,
            "cycles_used": self.max_healing_cycles,
        }

    # -- execution ------------------------------------------------------------

    @staticmethod
    def _execute_script(script_path: str, inputs: dict) -> str:
        """Run the RPA script as a subprocess, capture stdout/stderr.

        The *inputs* dict is passed as a JSON string via the
        ``ACTIONSHOT_INPUTS`` environment variable.
        """
        import subprocess

        env = {**os.environ, "ACTIONSHOT_INPUTS": json.dumps(inputs, default=str)}
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "unknown error").strip()
            raise RuntimeError(
                f"Script exited with code {proc.returncode}: {detail}"
            )
        return proc.stdout

    # -- regeneration ---------------------------------------------------------

    def _patch_and_regenerate(self, ir: dict, fix_diff: dict) -> str:
        """Apply fix to IR, regenerate script via prompt_template + Claude.

        If the codegen module is not available, falls back to writing the
        patched IR as a JSON file and returning the original script path.
        """
        try:
            from actionshot.codegen import generate_script
            new_script_path = str(
                Path(self.script_path).with_suffix(".healed.py")
            )
            generate_script(ir, output_path=new_script_path)
            return new_script_path
        except ImportError:
            # Codegen not available -- write patched IR for manual regen
            patched_path = str(
                Path(self.script_path).with_suffix(".patched_ir.json")
            )
            with open(patched_path, "w", encoding="utf-8") as fh:
                json.dump(ir, fh, indent=2, default=str, ensure_ascii=False)
            return self.script_path

    # -- AI fix helper --------------------------------------------------------

    @staticmethod
    def _call_ai_for_fix(prompt: str) -> dict | None:
        """Send the AI fix prompt to Claude and parse the JSON response.

        Returns a fix_diff dict or None if the call fails.
        """
        try:
            from actionshot.llm import call_claude
            response = call_claude(prompt)
            # Try to extract JSON from the response
            import re as _re
            match = _re.search(r"\{[\s\S]*\}", response)
            if match:
                return json.loads(match.group(0))
        except Exception:
            pass
        return None

    # -- bookkeeping ----------------------------------------------------------

    def _record_cycle(
        self,
        cycle: int,
        diagnosis: dict,
        fix_source: str,
        success: bool | None,
    ) -> None:
        record = {
            "cycle": cycle,
            "workflow_id": self.workflow_id,
            "pattern": diagnosis.get("pattern"),
            "fix_strategy": fix_source,
            "confidence": diagnosis.get("confidence"),
            "auto_fixable": diagnosis.get("auto_fixable"),
            "success": success,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec="milliseconds"
            ),
        }
        self.healing_history.append(record)

    def _notify_give_up(self, exc: Exception) -> None:
        """Send a notification when healing is exhausted."""
        try:
            from actionshot.telemetry import NotificationDispatcher
            notifier = NotificationDispatcher()
            notifier.notify({
                "event": "healing_exhausted",
                "workflow_id": self.workflow_id,
                "error": str(exc),
                "cycles": self.max_healing_cycles,
                "healing_history": self.healing_history,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(
                    timespec="milliseconds"
                ),
            })
        except Exception:
            pass  # never let notification break the runner

    @staticmethod
    def _guess_failed_step(exc: Exception, ir: dict) -> dict:
        """Try to identify which IR step caused the failure."""
        steps = ir.get("steps", [])
        msg = str(exc).lower()
        # Look for a step id reference in the error message
        for step in steps:
            step_id = str(step.get("id", ""))
            if step_id and step_id in msg:
                return step
        # Default to the last step
        return steps[-1] if steps else {"id": "unknown", "op": "unknown"}

    @staticmethod
    def _read_script(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        except Exception:
            return ""


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _write_healing_log(workflow_id: str, message: str) -> None:
    """Write a healing event to the healing data directory."""
    log_path = _HEALING_DIR / "healing_log.jsonl"
    entry = {
        "workflow_id": workflow_id,
        "message": message,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="milliseconds"
        ),
    }
    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        pass

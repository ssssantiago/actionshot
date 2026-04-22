# Debugging Failed RPAs

## Quick checklist

1. Check the workflow log
2. Look at the failure screenshot
3. Inspect the UIA tree dump
4. Check selector resolution order
5. Review the self-healing diagnosis

## Workflow logs

Generated scripts log to `logs/<workflow_id>/` by default. Each run creates a timestamped log file with:
- Step-by-step execution trace
- Selector resolution attempts (which level matched)
- Timing information
- Error tracebacks

## Failure packages

When a step fails, `self_healing.py` captures a failure package containing:

- **Screenshot** at the moment of failure
- **UIA tree** dump of the active window
- **Environment info** (screen resolution, OS version, locale)
- **Step spec** from the IR that was being executed
- **Recent step history** (last 5 steps that succeeded)

These are saved to `failures/<workflow_id>/<timestamp>/`.

## Common failure patterns

### Selector not found

The element is not on screen. Possible causes:
- **App changed its UI** - AutomationIds or control structure changed after an update. Check if the primary selector still exists in the UIA tree dump.
- **Timing issue** - The element has not loaded yet. Increase `timeout_ms` in the IR's `wait_for` step.
- **Wrong window** - The app opened a dialog or popup that took focus. Check the window title in the failure screenshot.

Fix: Update the selector in the IR, or add a `wait_for` step before the failing step.

### Field value mismatch

A `field_has_value` assertion failed. The field contains a different value than expected. Possible causes:
- **Input masking** - CPF/phone fields auto-format (e.g., `12345678900` becomes `123.456.789-00`). Update the expected value format.
- **Field not cleared** - `rpakit.fill()` should clear before typing, but some custom controls do not support this. Try adding an explicit select-all + delete before fill.

### Element visible but not interactable

The element exists in the UIA tree but clicking it does nothing. Possible causes:
- **Element is disabled** - Check the `IsEnabled` property in the UIA dump.
- **Overlay/modal blocking** - Another element is on top. Check the failure screenshot for popups.
- **Coordinates are off** - Multi-monitor setups can cause coordinate offset. Verify `monitor.py` is detecting all screens.

### Extract text returns empty

An `output_not_empty` assertion failed. Possible causes:
- **Wrong element** - The selector matched a container instead of the text label. Narrow the selector.
- **Content loaded asynchronously** - Add a longer wait or poll for non-empty text.
- **OCR fallback needed** - Some controls do not expose text via UIA. The script may need to use OCR extraction.

## Self-healing

The `SelfHealingLoop` in `self_healing.py` attempts automatic fixes:

1. **Known pattern match** - Compares the failure against a catalog of known issues and applies pre-built fixes (e.g., adding a wait, trying a fallback selector).
2. **AI-assisted fix** - For unknown failures, it sends the failure package to Claude to generate a patched IR.
3. **History tracking** - Records what worked so the same fix applies automatically next time.

To trigger self-healing manually:

```python
from actionshot.self_healing import FailureCapture, SelfHealingLoop

capture = FailureCapture()
pkg = capture.capture(exception, workflow_id, step_spec, recent_steps)

healer = SelfHealingLoop()
diagnosis = healer.diagnose(pkg)
print(diagnosis)
```

## Useful rpakit debug calls

```python
# Check if an element exists without failing
exists = rpakit.exists(sel)

# Dump the UIA tree for the current window
rpakit.debug_dump_tree()

# Take a diagnostic screenshot
rpakit.debug_screenshot("debug_step_5.png")
```

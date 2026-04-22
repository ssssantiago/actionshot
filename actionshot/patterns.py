"""Pattern detection - identifies loops, groups related steps, and finds repetitive actions.

Also provides session curation: deterministic preprocessing that cleans a raw
recording before it is handed to AI-based code generation.
"""

import json
import os
from collections import Counter
from datetime import datetime


class PatternDetector:
    """Analyzes a recorded session for patterns and repetitive actions."""

    def __init__(self, session_path: str):
        self.session_path = session_path
        self.steps = []
        self._load()

    def _load(self):
        summary_path = os.path.join(self.session_path, "session_summary.json")
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)

        for step_info in summary["steps"]:
            step_num = step_info["step"]
            meta_path = os.path.join(self.session_path, f"{step_num:03d}_metadata.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.steps.append(json.load(f))

    def detect_loops(self, min_repeat: int = 2) -> list[dict]:
        """Find repeated sequences of actions (loops).

        Uses a sliding window to find action sequences that repeat.
        """
        if len(self.steps) < min_repeat * 2:
            return []

        signatures = [self._step_signature(s) for s in self.steps]
        loops = []

        # Try pattern lengths from 1 to half the total steps
        for pattern_len in range(1, len(signatures) // 2 + 1):
            i = 0
            while i <= len(signatures) - pattern_len * 2:
                pattern = signatures[i:i + pattern_len]
                repeat_count = 1
                j = i + pattern_len

                while j + pattern_len <= len(signatures):
                    if signatures[j:j + pattern_len] == pattern:
                        repeat_count += 1
                        j += pattern_len
                    else:
                        break

                if repeat_count >= min_repeat:
                    loop_steps = self.steps[i:i + pattern_len]
                    loops.append({
                        "pattern_length": pattern_len,
                        "repeat_count": repeat_count,
                        "start_step": self.steps[i].get("step", i),
                        "end_step": self.steps[j - 1].get("step", j - 1),
                        "pattern": pattern,
                        "steps": [
                            {
                                "action": s.get("action", ""),
                                "description": s.get("description", ""),
                                "element": s.get("element", {}),
                            }
                            for s in loop_steps
                        ],
                    })
                    i = j  # Skip past this loop
                else:
                    i += 1

        # Remove sub-patterns (keep longest)
        loops.sort(key=lambda l: l["pattern_length"] * l["repeat_count"], reverse=True)
        filtered = []
        used_ranges = set()
        for loop in loops:
            step_range = set(range(loop["start_step"], loop["end_step"] + 1))
            if not step_range & used_ranges:
                filtered.append(loop)
                used_ranges |= step_range

        return filtered

    def group_steps(self) -> list[dict]:
        """Group related sequential steps into logical actions.

        Examples:
            click on text field + type text = "filled field X with Y"
            click on dropdown + click on option = "selected option Y from dropdown X"
        """
        groups = []
        i = 0

        while i < len(self.steps):
            step = self.steps[i]
            action = step.get("action", "")

            # Pattern: click on field + keypress = fill field
            if action.endswith("_click") and i + 1 < len(self.steps):
                next_step = self.steps[i + 1]
                if next_step.get("action") == "keypress":
                    element = step.get("element", {})
                    field_name = element.get("name", "unknown")
                    field_type = element.get("control_type", "element")
                    typed_text = next_step.get("text", "")

                    groups.append({
                        "type": "fill_field",
                        "description": f"Filled {field_type} '{field_name}' with '{typed_text[:50]}'",
                        "steps": [step.get("step"), next_step.get("step")],
                        "field": field_name,
                        "value": typed_text,
                        "element": element,
                    })
                    i += 2
                    continue

            # Pattern: click + click in same window within 1s = multi-click action
            if action.endswith("_click") and i + 1 < len(self.steps):
                next_step = self.steps[i + 1]
                if (next_step.get("action", "").endswith("_click") and
                        step.get("window", {}).get("title") == next_step.get("window", {}).get("title")):
                    # Check if they're on the same element type (e.g., dropdown items)
                    elem1 = step.get("element", {})
                    elem2 = next_step.get("element", {})
                    if (elem1.get("control_type") == elem2.get("control_type") and
                            elem1.get("control_type") in ("MenuItem", "ListItem", "TreeItem", "ComboBox")):
                        groups.append({
                            "type": "select_from_menu",
                            "description": f"Selected '{elem2.get('name', '?')}' from '{elem1.get('name', '?')}'",
                            "steps": [step.get("step"), next_step.get("step")],
                            "menu": elem1.get("name", ""),
                            "selection": elem2.get("name", ""),
                        })
                        i += 2
                        continue

            # Single step — no pattern matched
            groups.append({
                "type": "single",
                "description": step.get("description", ""),
                "steps": [step.get("step")],
            })
            i += 1

        return groups

    def find_frequent_targets(self) -> list[dict]:
        """Find the most frequently interacted-with elements."""
        targets = Counter()

        for step in self.steps:
            if step.get("action", "").endswith("_click"):
                element = step.get("element", {})
                name = element.get("name", "")
                ctrl_type = element.get("control_type", "")
                window = step.get("window", {}).get("title", "")
                if name:
                    key = f"{ctrl_type}::{name}::{window}"
                    targets[key] += 1

        return [
            {
                "target": key,
                "count": count,
                "control_type": key.split("::")[0],
                "name": key.split("::")[1],
                "window": key.split("::")[2],
            }
            for key, count in targets.most_common(20)
        ]

    def analyze(self, output_path: str = None) -> dict:
        """Run full analysis and save results."""
        if output_path is None:
            output_path = os.path.join(self.session_path, "analysis.json")

        result = {
            "total_steps": len(self.steps),
            "loops": self.detect_loops(),
            "grouped_actions": self.group_steps(),
            "frequent_targets": self.find_frequent_targets(),
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"  Analysis saved: {output_path}")
        print(f"  Loops found: {len(result['loops'])}")
        print(f"  Grouped actions: {len(result['grouped_actions'])}")
        print(f"  Frequent targets: {len(result['frequent_targets'])}")

        return result

    # ------------------------------------------------------------------
    # Session Curation
    # ------------------------------------------------------------------

    def curate_session(self) -> dict:
        """Apply deterministic transformations to clean the recording before AI processing.

        Pipeline order:
        1. Dedup clicks (same position within 200ms)
        2. Undo detection (Ctrl+Z / Esc sequences)
        3. Idle removal (pauses > 10s become WAIT_MANUAL_REVIEW markers)
        4. Semantic grouping (fill_field, select_option, copy_text, set_checkbox)
        5. Ghost window removal (windows focused < 500ms with no interaction)

        Returns a dict with curated_steps, curation_log, and stats.
        The result is also saved as curated_session.json in the session folder.
        """
        curation_log: list[dict] = []
        removed_count = 0
        merged_count = 0
        grouped_count = 0

        # Start with a copy of steps so the original list is untouched
        working = [dict(s) for s in self.steps]

        # --- 1. Dedup clicks ---
        working, log_entries, m = self._dedup_clicks(working)
        curation_log.extend(log_entries)
        merged_count += m

        # --- 2. Undo detection ---
        working, log_entries, r = self._detect_undos(working)
        curation_log.extend(log_entries)
        removed_count += r

        # --- 3. Idle removal ---
        working, log_entries, r = self._remove_idles(working)
        curation_log.extend(log_entries)
        removed_count += r

        # --- 4. Semantic grouping ---
        working, log_entries, g = self._semantic_group(working)
        curation_log.extend(log_entries)
        grouped_count += g

        # --- 5. Ghost window removal ---
        working, log_entries, r = self._remove_ghost_windows(working)
        curation_log.extend(log_entries)
        removed_count += r

        result = {
            "curated_steps": working,
            "curation_log": curation_log,
            "stats": {
                "original": len(self.steps),
                "curated": len(working),
                "removed": removed_count,
                "merged": merged_count,
                "grouped": grouped_count,
            },
        }

        output_path = os.path.join(self.session_path, "curated_session.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"  Curation saved: {output_path}")
        print(f"  Original: {result['stats']['original']}  ->  Curated: {result['stats']['curated']}")
        print(f"  Removed: {removed_count}  Merged: {merged_count}  Grouped: {grouped_count}")

        return result

    # ---- internal curation helpers ----

    @staticmethod
    def _parse_timestamp(ts: str) -> datetime | None:
        """Parse an ISO-format timestamp string, returning None on failure."""
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _position_close(pos_a: dict, pos_b: dict, tolerance: int = 5) -> bool:
        """Return True if two positions are within *tolerance* pixels."""
        if not pos_a or not pos_b:
            return False
        dx = abs(pos_a.get("x", 0) - pos_b.get("x", 0))
        dy = abs(pos_a.get("y", 0) - pos_b.get("y", 0))
        return dx <= tolerance and dy <= tolerance

    @classmethod
    def _time_delta_ms(cls, step_a: dict, step_b: dict) -> float | None:
        """Milliseconds between two steps (None if timestamps are missing)."""
        ts_a = cls._parse_timestamp(step_a.get("timestamp", ""))
        ts_b = cls._parse_timestamp(step_b.get("timestamp", ""))
        if ts_a is None or ts_b is None:
            return None
        return abs((ts_b - ts_a).total_seconds() * 1000)

    # -- 1. Dedup clicks --

    def _dedup_clicks(self, steps: list[dict]) -> tuple[list[dict], list[dict], int]:
        """Remove duplicate clicks at the same position within 200ms."""
        if len(steps) < 2:
            return steps, [], 0

        keep: list[dict] = [steps[0]]
        log: list[dict] = []
        merged = 0

        for i in range(1, len(steps)):
            prev = keep[-1]
            curr = steps[i]

            both_clicks = (
                prev.get("action", "").endswith("_click")
                and curr.get("action", "").endswith("_click")
            )

            if both_clicks:
                delta = self._time_delta_ms(prev, curr)
                close = self._position_close(
                    prev.get("position", {}), curr.get("position", {})
                )
                if close and delta is not None and delta <= 200:
                    log.append({
                        "raw_action_id": curr.get("step", i),
                        "operation": f"merged_with_{prev.get('step', i - 1)}",
                        "reason": "duplicate_click_within_200ms",
                    })
                    merged += 1
                    continue

            keep.append(curr)

        return keep, log, merged

    # -- 2. Undo detection --

    @staticmethod
    def _is_ctrl_z(step: dict) -> bool:
        """Return True if the step is a Ctrl+Z keypress."""
        if step.get("action") != "keypress":
            return False
        text = step.get("text", "").lower()
        keys = step.get("keys", [])
        # Normalised representations produced by the recorder
        if "[ctrl]z" in text or "ctrl+z" in text:
            return True
        lower_keys = [k.lower() for k in keys]
        if "[ctrl]" in lower_keys and "z" in lower_keys:
            return True
        return False

    @staticmethod
    def _is_esc(step: dict) -> bool:
        """Return True if the step is an Escape keypress."""
        if step.get("action") != "keypress":
            return False
        text = step.get("text", "").lower()
        keys = step.get("keys", [])
        if "[esc]" in text or "escape" in text or "[escape]" in text:
            return True
        lower_keys = [k.lower() for k in keys]
        if "[esc]" in lower_keys or "escape" in lower_keys or "[escape]" in lower_keys:
            return True
        return False

    def _detect_undos(self, steps: list[dict]) -> tuple[list[dict], list[dict], int]:
        """Detect [action] -> Ctrl+Z or [action] -> Esc -> [correction] and discard the undone action.

        Strategy:
        - [action X] then Ctrl+Z  -> remove both X and the Ctrl+Z
        - [action X] then Esc     -> remove X and the Esc (keep whatever follows as the correction)
        """
        if len(steps) < 2:
            return steps, [], 0

        removed_indices: set[int] = set()
        log: list[dict] = []

        i = 0
        while i < len(steps) - 1:
            curr = steps[i]
            nxt = steps[i + 1]

            if self._is_ctrl_z(nxt):
                # Remove the action that was undone (curr) AND the Ctrl+Z itself
                removed_indices.add(i)
                removed_indices.add(i + 1)
                log.append({
                    "raw_action_id": curr.get("step", i),
                    "operation": "removed",
                    "reason": f"undone_by_action_{nxt.get('step', i + 1)}_ctrl_z",
                })
                log.append({
                    "raw_action_id": nxt.get("step", i + 1),
                    "operation": "removed",
                    "reason": "undo_keystroke",
                })
                i += 2
                continue

            if self._is_esc(nxt):
                # Remove the original action (curr) and the Esc; keep correction that follows
                removed_indices.add(i)
                removed_indices.add(i + 1)
                log.append({
                    "raw_action_id": curr.get("step", i),
                    "operation": "removed",
                    "reason": f"undone_by_action_{nxt.get('step', i + 1)}_esc",
                })
                log.append({
                    "raw_action_id": nxt.get("step", i + 1),
                    "operation": "removed",
                    "reason": "escape_keystroke",
                })
                i += 2
                continue

            i += 1

        kept = [s for idx, s in enumerate(steps) if idx not in removed_indices]
        return kept, log, len(removed_indices)

    # -- 3. Idle removal --

    def _remove_idles(self, steps: list[dict]) -> tuple[list[dict], list[dict], int]:
        """Convert pauses > 10 seconds into WAIT_MANUAL_REVIEW markers or remove them.

        A marker step is inserted *between* the two actions that surround the
        idle gap.  No real action is removed -- but the marker counts towards
        the removed tally because the idle "dead time" is eliminated.
        """
        if len(steps) < 2:
            return steps, [], 0

        result: list[dict] = [steps[0]]
        log: list[dict] = []
        markers_inserted = 0

        for i in range(1, len(steps)):
            prev = steps[i - 1]
            curr = steps[i]
            delta = self._time_delta_ms(prev, curr)

            if delta is not None and delta > 10_000:
                marker = {
                    "step": None,
                    "action": "WAIT_MANUAL_REVIEW",
                    "description": (
                        f"Idle pause of {delta / 1000:.1f}s detected between "
                        f"step {prev.get('step', '?')} and {curr.get('step', '?')}"
                    ),
                    "timestamp": curr.get("timestamp", ""),
                    "idle_ms": delta,
                }
                result.append(marker)
                log.append({
                    "raw_action_id": [prev.get("step", "?"), curr.get("step", "?")],
                    "operation": "idle_marker_inserted",
                    "reason": f"idle_pause_{delta / 1000:.1f}s",
                })
                markers_inserted += 1

            result.append(curr)

        return result, log, markers_inserted

    # -- 4. Semantic grouping --

    def _semantic_group(self, steps: list[dict]) -> tuple[list[dict], list[dict], int]:
        """Group sequences into higher-level semantic actions.

        Recognised patterns (in priority order):
        - triple-click + Ctrl+C               -> copy_text(selector)
        - click on input + keystrokes + Tab/Enter -> fill_field(selector, value)
        - click on dropdown + click on item    -> select_option(dropdown, item)
        - click on checkbox with state change   -> set_checkbox(selector, state)
        """
        result: list[dict] = []
        log: list[dict] = []
        grouped = 0
        i = 0

        while i < len(steps):
            # --- triple-click + Ctrl+C -> copy_text ---
            consumed, entry, log_entry = self._try_copy_text(steps, i)
            if consumed:
                result.append(entry)
                log.append(log_entry)
                grouped += 1
                i += consumed
                continue

            # --- click input + keystrokes + Tab/Enter -> fill_field ---
            consumed, entry, log_entry = self._try_fill_field(steps, i)
            if consumed:
                result.append(entry)
                log.append(log_entry)
                grouped += 1
                i += consumed
                continue

            # --- click dropdown + click item -> select_option ---
            consumed, entry, log_entry = self._try_select_option(steps, i)
            if consumed:
                result.append(entry)
                log.append(log_entry)
                grouped += 1
                i += consumed
                continue

            # --- checkbox click with state change -> set_checkbox ---
            consumed, entry, log_entry = self._try_set_checkbox(steps, i)
            if consumed:
                result.append(entry)
                log.append(log_entry)
                grouped += 1
                i += consumed
                continue

            # No pattern matched -- keep as-is
            result.append(steps[i])
            i += 1

        return result, log, grouped

    # semantic helpers

    @staticmethod
    def _is_click(step: dict) -> bool:
        return step.get("action", "").endswith("_click")

    @staticmethod
    def _is_keypress(step: dict) -> bool:
        return step.get("action") == "keypress"

    @staticmethod
    def _text_has_ctrl_c(step: dict) -> bool:
        if step.get("action") != "keypress":
            return False
        text = step.get("text", "").lower()
        keys = step.get("keys", [])
        if "[ctrl]c" in text or "ctrl+c" in text:
            return True
        lower_keys = [k.lower() for k in keys]
        return "[ctrl]" in lower_keys and "c" in lower_keys

    @staticmethod
    def _is_tab_or_enter(step: dict) -> bool:
        """Return True if a keypress step contains Tab or Enter."""
        if step.get("action") != "keypress":
            return False
        text = step.get("text", "").lower()
        keys = step.get("keys", [])
        for token in ("[tab]", "[enter]", "tab", "enter", "\t", "\n"):
            if token in text:
                return True
        lower_keys = [k.lower() for k in keys]
        for token in ("[tab]", "[enter]", "tab", "enter"):
            if token in lower_keys:
                return True
        return False

    def _try_copy_text(self, steps: list[dict], i: int):
        """triple-click + Ctrl+C -> copy_text(selector).

        We consider up to 3 consecutive clicks at the same position followed by
        a Ctrl+C keypress.
        """
        if i + 1 >= len(steps):
            return 0, None, None

        # Collect consecutive clicks at roughly the same position
        click_count = 0
        j = i
        while j < len(steps) and self._is_click(steps[j]):
            if click_count == 0:
                first_pos = steps[j].get("position", {})
            else:
                if not self._position_close(first_pos, steps[j].get("position", {}), tolerance=5):
                    break
            click_count += 1
            j += 1

        if click_count < 3 or j >= len(steps):
            return 0, None, None

        if not self._text_has_ctrl_c(steps[j]):
            return 0, None, None

        consumed = j - i + 1  # clicks + the Ctrl+C step
        step_ids = [steps[k].get("step") for k in range(i, i + consumed)]
        element = steps[i].get("element", {})
        selector = element.get("automation_id") or element.get("name", "unknown")

        entry = {
            "action": "copy_text",
            "description": f"copy_text({selector})",
            "selector": selector,
            "element": element,
            "source_steps": step_ids,
        }
        log_entry = {
            "raw_action_id": step_ids,
            "operation": "grouped",
            "result": f"copy_text({selector})",
        }
        return consumed, entry, log_entry

    def _try_fill_field(self, steps: list[dict], i: int):
        """click on input + keystrokes [+ Tab/Enter] -> fill_field(selector, value)."""
        if i + 1 >= len(steps):
            return 0, None, None

        step = steps[i]
        if not self._is_click(step):
            return 0, None, None

        element = step.get("element", {})
        ctrl_type = element.get("control_type", "").lower()
        # Heuristic: inputs, edits, text boxes, or generic "edit" control types
        input_types = ("edit", "text", "input", "editar", "combobox", "searchbox", "document")
        is_input = any(t in ctrl_type for t in input_types)
        # Also consider by class name
        class_name = element.get("class_name", "").lower()
        is_input = is_input or any(t in class_name for t in ("edit", "text", "input"))

        if not is_input:
            return 0, None, None

        # Collect consecutive keypress steps
        j = i + 1
        typed_parts: list[str] = []
        while j < len(steps) and self._is_keypress(steps[j]):
            typed_parts.append(steps[j].get("text", ""))
            j += 1

        if not typed_parts:
            return 0, None, None

        # Optionally consume a trailing Tab/Enter
        if j < len(steps) and self._is_tab_or_enter(steps[j]):
            j += 1

        consumed = j - i
        step_ids = [steps[k].get("step") for k in range(i, i + consumed)]
        field_name = element.get("automation_id") or element.get("name", "unknown")
        value = "".join(typed_parts)

        entry = {
            "action": "fill_field",
            "description": f"fill_field({field_name}, '{value[:50]}')",
            "selector": field_name,
            "value": value,
            "element": element,
            "source_steps": step_ids,
        }
        log_entry = {
            "raw_action_id": step_ids,
            "operation": "grouped",
            "result": f"fill_field({field_name}, '{value[:50]}')",
        }
        return consumed, entry, log_entry

    def _try_select_option(self, steps: list[dict], i: int):
        """click on dropdown/combobox + click on item -> select_option(dropdown, item)."""
        if i + 1 >= len(steps):
            return 0, None, None

        step = steps[i]
        nxt = steps[i + 1]

        if not (self._is_click(step) and self._is_click(nxt)):
            return 0, None, None

        elem_a = step.get("element", {})
        elem_b = nxt.get("element", {})
        ctrl_a = elem_a.get("control_type", "")
        ctrl_b = elem_b.get("control_type", "")

        dropdown_types = ("ComboBox", "DropDown", "SplitButton", "MenuBar", "Menu")
        item_types = ("ListItem", "MenuItem", "TreeItem", "ComboBoxItem")

        is_dropdown_then_item = ctrl_a in dropdown_types and ctrl_b in item_types
        is_menu_sequence = ctrl_a in ("MenuItem",) and ctrl_b in ("MenuItem",)

        if not (is_dropdown_then_item or is_menu_sequence):
            return 0, None, None

        dropdown_name = elem_a.get("automation_id") or elem_a.get("name", "unknown")
        item_name = elem_b.get("name", "unknown")
        step_ids = [step.get("step"), nxt.get("step")]

        entry = {
            "action": "select_option",
            "description": f"select_option({dropdown_name}, '{item_name}')",
            "selector": dropdown_name,
            "item": item_name,
            "element_dropdown": elem_a,
            "element_item": elem_b,
            "source_steps": step_ids,
        }
        log_entry = {
            "raw_action_id": step_ids,
            "operation": "grouped",
            "result": f"select_option({dropdown_name}, '{item_name}')",
        }
        return 2, entry, log_entry

    def _try_set_checkbox(self, steps: list[dict], i: int):
        """Click on checkbox element -> set_checkbox(selector, state)."""
        step = steps[i]
        if not self._is_click(step):
            return 0, None, None

        element = step.get("element", {})
        ctrl_type = element.get("control_type", "")

        if ctrl_type not in ("CheckBox", "RadioButton"):
            return 0, None, None

        selector = element.get("automation_id") or element.get("name", "unknown")
        # We cannot know the resulting state from metadata alone; mark as "toggled"
        description = step.get("description", "")
        # Heuristic: if the description mentions "check" or "uncheck"
        if "uncheck" in description.lower():
            state = False
        elif "check" in description.lower():
            state = True
        else:
            state = "toggled"

        step_id = step.get("step")
        entry = {
            "action": "set_checkbox",
            "description": f"set_checkbox({selector}, {state})",
            "selector": selector,
            "state": state,
            "element": element,
            "source_steps": [step_id],
        }
        log_entry = {
            "raw_action_id": [step_id],
            "operation": "grouped",
            "result": f"set_checkbox({selector}, {state})",
        }
        return 1, entry, log_entry

    # -- 5. Ghost window removal --

    def _remove_ghost_windows(self, steps: list[dict]) -> tuple[list[dict], list[dict], int]:
        """Remove steps whose window had focus for < 500ms with no real interaction.

        A "ghost window" is a window title that appears in the sequence, is
        focused for less than 500ms total, and only contains non-interactive
        steps (no clicks, no typed text, no WAIT markers).
        """
        if len(steps) < 2:
            return steps, [], 0

        # Build per-window spans: track the first and last timestamp, and
        # whether any interactive action happened.
        window_info: dict[str, dict] = {}  # title -> {first_ts, last_ts, interactive, indices}

        for idx, step in enumerate(steps):
            title = step.get("window", {}).get("title", "")
            if not title:
                continue

            if title not in window_info:
                window_info[title] = {
                    "first_ts": step.get("timestamp", ""),
                    "last_ts": step.get("timestamp", ""),
                    "interactive": False,
                    "indices": [],
                }

            info = window_info[title]
            info["last_ts"] = step.get("timestamp", "")
            info["indices"].append(idx)

            action = step.get("action", "")
            if action.endswith("_click") or action == "keypress" or action == "scroll":
                info["interactive"] = True

        # Identify ghost windows
        ghost_titles: set[str] = set()
        for title, info in window_info.items():
            if info["interactive"]:
                continue
            ts_first = self._parse_timestamp(info["first_ts"])
            ts_last = self._parse_timestamp(info["last_ts"])
            if ts_first is None or ts_last is None:
                continue
            focus_ms = abs((ts_last - ts_first).total_seconds() * 1000)
            if focus_ms < 500:
                ghost_titles.add(title)

        if not ghost_titles:
            return steps, [], 0

        # Collect indices to remove
        remove_indices: set[int] = set()
        for title in ghost_titles:
            remove_indices.update(window_info[title]["indices"])

        log: list[dict] = []
        for idx in sorted(remove_indices):
            step = steps[idx]
            log.append({
                "raw_action_id": step.get("step", idx),
                "operation": "removed",
                "reason": f"ghost_window_{step.get('window', {}).get('title', '?')}",
            })

        kept = [s for idx, s in enumerate(steps) if idx not in remove_indices]
        return kept, log, len(remove_indices)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _step_signature(step: dict) -> str:
        """Create a comparable signature for a step."""
        action = step.get("action", "")
        element = step.get("element", {})
        name = element.get("name", "")
        ctrl_type = element.get("control_type", "")
        window = step.get("window", {}).get("title", "")
        return f"{action}|{ctrl_type}|{name}|{window}"

"""Pattern detection - identifies loops, groups related steps, and finds repetitive actions."""

import json
import os
from collections import Counter


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

    @staticmethod
    def _step_signature(step: dict) -> str:
        """Create a comparable signature for a step."""
        action = step.get("action", "")
        element = step.get("element", {})
        name = element.get("name", "")
        ctrl_type = element.get("control_type", "")
        window = step.get("window", {}).get("title", "")
        return f"{action}|{ctrl_type}|{name}|{window}"

"""Session management - creates and organizes recording sessions."""

import os
import json
import uuid
from datetime import datetime


class Session:
    def __init__(self, output_dir="recordings"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.name = f"session_{timestamp}"
        self.path = os.path.join(output_dir, self.name)
        os.makedirs(self.path, exist_ok=True)
        self.step_count = 0
        self.steps = []

    def next_step(self):
        self.step_count += 1
        return self.step_count

    def add_step(self, step_data):
        self.steps.append(step_data)
        self._save_summary()

    def _save_summary(self):
        summary = {
            "session": self.name,
            "total_steps": self.step_count,
            "steps": self.steps,
        }
        path = os.path.join(self.path, "session_summary.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

    def step_path(self, step_num, suffix):
        return os.path.join(self.path, f"{step_num:03d}_{suffix}")

    # ── Scope-aware persistence ──────────────────────────────────

    def save_raw_events(self, events):
        """Save ALL events (in and out of scope) to ``recording.raw.jsonl``.

        Each event is written as a single JSON line.
        """
        path = os.path.join(self.path, "recording.raw.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for evt in events:
                f.write(json.dumps(evt, ensure_ascii=False, default=str) + "\n")

    def save_scoped_ir(self, scope, events, dependencies=None):
        """Save schema_version 2 IR containing only in-scope events.

        Parameters
        ----------
        scope : WorkflowScope or None
            The workflow scope object.  When ``None``, ``declared_scope``
            is written as an empty list.
        events : list[dict]
            Already-filtered in-scope events.
        dependencies : list | None
            Detected cross-app dependencies.
        """
        declared = list(scope.declared_apps) if scope else []
        workflow_id = str(uuid.uuid4())

        ir = {
            "schema_version": 2,
            "workflow_id": workflow_id,
            "declared_scope": declared,
            "detected_dependencies": dependencies or [],
            "events": events,
        }

        path = os.path.join(self.path, "recording.ir.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ir, f, indent=2, ensure_ascii=False, default=str)

    def export_ir_v2(self, scope, all_events, dependencies=None):
        """Filter events to in-scope, add ``has_time_gap`` flags, and save IR.

        A *time gap* is flagged when consecutive in-scope events are more
        than 1 second apart (indicating the user switched away and came
        back).

        Parameters
        ----------
        scope : WorkflowScope or None
        all_events : list[dict]
            Full event list (both in-scope and out-of-scope).
        dependencies : list | None
        """
        scoped = [e for e in all_events if e.get("in_scope", True)]

        # Annotate time gaps
        for i, evt in enumerate(scoped):
            if i == 0:
                evt["has_time_gap"] = False
                continue
            prev_ts = scoped[i - 1].get("timestamp", "")
            curr_ts = evt.get("timestamp", "")
            try:
                prev_dt = datetime.fromisoformat(prev_ts)
                curr_dt = datetime.fromisoformat(curr_ts)
                gap_seconds = (curr_dt - prev_dt).total_seconds()
                evt["has_time_gap"] = gap_seconds > 1.0
            except (ValueError, TypeError):
                evt["has_time_gap"] = False

        self.save_scoped_ir(scope, scoped, dependencies)

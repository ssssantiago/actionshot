"""Session management - creates and organizes recording sessions."""

import os
import json
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

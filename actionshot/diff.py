"""Session diff - compare two recorded sessions and highlight differences."""

import json
import os


class SessionDiff:
    """Compare two ActionShot sessions step by step."""

    def __init__(self, session_a: str, session_b: str):
        self.path_a = session_a
        self.path_b = session_b
        self.steps_a = self._load_steps(session_a)
        self.steps_b = self._load_steps(session_b)

    @staticmethod
    def _load_steps(session_path: str) -> list[dict]:
        summary_path = os.path.join(session_path, "session_summary.json")
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)

        steps = []
        for step_info in summary["steps"]:
            step_num = step_info["step"]
            meta_path = os.path.join(session_path, f"{step_num:03d}_metadata.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    steps.append(json.load(f))
        return steps

    def compare(self, output_path: str = None) -> dict:
        """Compare sessions and return a diff report."""
        result = {
            "session_a": self.path_a,
            "session_b": self.path_b,
            "steps_a": len(self.steps_a),
            "steps_b": len(self.steps_b),
            "matches": [],
            "only_in_a": [],
            "only_in_b": [],
            "differences": [],
        }

        sigs_a = [self._signature(s) for s in self.steps_a]
        sigs_b = [self._signature(s) for s in self.steps_b]

        # LCS-based alignment
        lcs = self._lcs(sigs_a, sigs_b)

        i, j, k = 0, 0, 0
        while k < len(lcs):
            target = lcs[k]

            # Advance A to next match
            while i < len(sigs_a) and sigs_a[i] != target:
                result["only_in_a"].append(self._step_summary(self.steps_a[i], "A"))
                i += 1

            # Advance B to next match
            while j < len(sigs_b) and sigs_b[j] != target:
                result["only_in_b"].append(self._step_summary(self.steps_b[j], "B"))
                j += 1

            if i < len(sigs_a) and j < len(sigs_b):
                match_info = {
                    "step_a": self.steps_a[i].get("step"),
                    "step_b": self.steps_b[j].get("step"),
                    "action": self.steps_a[i].get("action"),
                    "description": self.steps_a[i].get("description"),
                }

                # Check for positional differences
                pos_a = self.steps_a[i].get("position", {})
                pos_b = self.steps_b[j].get("position", {})
                if pos_a and pos_b:
                    dx = abs(pos_a.get("x", 0) - pos_b.get("x", 0))
                    dy = abs(pos_a.get("y", 0) - pos_b.get("y", 0))
                    if dx > 5 or dy > 5:
                        match_info["position_drift"] = {"dx": dx, "dy": dy}

                result["matches"].append(match_info)
                i += 1
                j += 1

            k += 1

        # Remaining unmatched steps
        while i < len(sigs_a):
            result["only_in_a"].append(self._step_summary(self.steps_a[i], "A"))
            i += 1
        while j < len(sigs_b):
            result["only_in_b"].append(self._step_summary(self.steps_b[j], "B"))
            j += 1

        result["summary"] = {
            "matched": len(result["matches"]),
            "only_a": len(result["only_in_a"]),
            "only_b": len(result["only_in_b"]),
            "similarity": (
                len(result["matches"]) * 2 /
                max(len(self.steps_a) + len(self.steps_b), 1)
            ),
        }

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"  Diff saved: {output_path}")

        return result

    def print_diff(self):
        """Print a human-readable diff to console."""
        result = self.compare()

        print(f"\n  Session A: {self.path_a} ({result['steps_a']} steps)")
        print(f"  Session B: {self.path_b} ({result['steps_b']} steps)")
        print(f"  Similarity: {result['summary']['similarity']:.0%}")
        print()

        if result["matches"]:
            print(f"  Matched steps: {len(result['matches'])}")
            for m in result["matches"]:
                drift = m.get("position_drift", {})
                drift_str = f" [drift: dx={drift['dx']}, dy={drift['dy']}]" if drift else ""
                print(f"    A:{m['step_a']:03d} = B:{m['step_b']:03d}  {m['description']}{drift_str}")

        if result["only_in_a"]:
            print(f"\n  Only in A: {len(result['only_in_a'])}")
            for s in result["only_in_a"]:
                print(f"    A:{s['step']:03d}  {s['description']}")

        if result["only_in_b"]:
            print(f"\n  Only in B: {len(result['only_in_b'])}")
            for s in result["only_in_b"]:
                print(f"    B:{s['step']:03d}  {s['description']}")

        print()

    @staticmethod
    def _signature(step: dict) -> str:
        action = step.get("action", "")
        element = step.get("element", {})
        name = element.get("name", "")
        ctrl_type = element.get("control_type", "")
        return f"{action}|{ctrl_type}|{name}"

    @staticmethod
    def _step_summary(step: dict, label: str) -> dict:
        return {
            "session": label,
            "step": step.get("step", 0),
            "action": step.get("action", ""),
            "description": step.get("description", ""),
        }

    @staticmethod
    def _lcs(a: list, b: list) -> list:
        """Longest Common Subsequence."""
        m, n = len(a), len(b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if a[i - 1] == b[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

        # Backtrack
        result = []
        i, j = m, n
        while i > 0 and j > 0:
            if a[i - 1] == b[j - 1]:
                result.append(a[i - 1])
                i -= 1
                j -= 1
            elif dp[i - 1][j] > dp[i][j - 1]:
                i -= 1
            else:
                j -= 1

        return list(reversed(result))

"""Benchmark suite for measuring RPA generation quality.

Loads benchmark cases from a directory structure, generates scripts from IR,
and measures quality metrics like parse success, edit distance, selector
fallback rate, generation time, and token count.

Each benchmark case is a folder containing:
  - ``ir.json``              -- the IR to generate code from
  - ``expected_script.py``   -- reference script (optional, for edit distance)
  - ``config.json``          -- metadata (difficulty, app_type, has_branches, has_loops)
"""

import ast
import difflib
import json
import os
import re
import time
from typing import Any


# ---------------------------------------------------------------------------
# Difficulty levels
# ---------------------------------------------------------------------------

DIFFICULTY_LEVELS = {
    "trivial": "Simple form fill, 3-5 steps",
    "medium": "Multi-step with navigation, 10-15 steps",
    "hard": "Conditional branches, loops, 20+ steps",
    "adversarial": "Popups, frame switches, unstable selectors",
}


# ---------------------------------------------------------------------------
# BenchmarkCase factory
# ---------------------------------------------------------------------------

class BenchmarkCase:
    """Factory for creating benchmark cases from various sources."""

    @staticmethod
    def create_from_session(session_path: str, difficulty: str = "medium") -> str:
        """Create a benchmark case from a real recorded session.

        Compiles the session into IR, copies it into a new benchmark case
        directory, and writes a ``config.json``.

        Parameters
        ----------
        session_path : str
            Path to the recorded session directory (must contain
            ``session_summary.json``).
        difficulty : str
            One of the DIFFICULTY_LEVELS keys.

        Returns
        -------
        str
            Path to the newly created benchmark case directory.
        """
        from actionshot.ir_compiler import IRCompiler

        if difficulty not in DIFFICULTY_LEVELS:
            raise ValueError(
                f"Invalid difficulty {difficulty!r}. "
                f"Choose from: {', '.join(DIFFICULTY_LEVELS)}"
            )

        compiler = IRCompiler(session_path)
        ir = compiler.compile()

        # Derive case name from session
        session_name = os.path.basename(session_path.rstrip("/\\"))
        case_name = re.sub(r"[^a-zA-Z0-9_]", "_", session_name).strip("_")
        case_dir = os.path.join("benchmarks", case_name)
        os.makedirs(case_dir, exist_ok=True)

        # Write IR
        ir_path = os.path.join(case_dir, "ir.json")
        with open(ir_path, "w", encoding="utf-8") as f:
            json.dump(ir, f, indent=2, ensure_ascii=False)

        # Detect features
        has_branches = any(
            s.get("op") == "if_condition" for s in ir.get("steps", [])
        )
        has_loops = any(
            s.get("op") == "loop" for s in ir.get("steps", [])
        )

        # Infer app type from open_app steps
        app_types = [
            s.get("target", "")
            for s in ir.get("steps", [])
            if s.get("op") == "open_app"
        ]
        app_type = app_types[0] if app_types else "unknown"

        config = {
            "name": case_name,
            "difficulty": difficulty,
            "app_type": app_type,
            "has_branches": has_branches,
            "has_loops": has_loops,
            "step_count": len(ir.get("steps", [])),
            "source_session": session_path,
        }

        config_path = os.path.join(case_dir, "config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        return case_dir


# ---------------------------------------------------------------------------
# Quality metric helpers
# ---------------------------------------------------------------------------

def _check_one_shot_success(script: str) -> bool:
    """Return True if *script* parses as valid Python with no obvious errors."""
    if not script or not script.strip():
        return False
    try:
        ast.parse(script)
    except SyntaxError:
        return False

    # Check for common generation artifacts
    bad_patterns = [
        "TODO",
        "FIXME",
        "NotImplementedError",
        "pass  #",
    ]
    for pat in bad_patterns:
        if pat in script:
            return False

    return True


def _compute_edit_distance(generated: str, expected: str) -> int:
    """Return the number of differing lines between two scripts."""
    gen_lines = generated.splitlines(keepends=True)
    exp_lines = expected.splitlines(keepends=True)
    diff = list(difflib.unified_diff(exp_lines, gen_lines, n=0))
    # Count only added/removed lines (those starting with + or - but not +++ or ---)
    changed = sum(
        1 for line in diff
        if (line.startswith("+") or line.startswith("-"))
        and not line.startswith("+++")
        and not line.startswith("---")
    )
    return changed


def _compute_selector_fallback_rate(script: str) -> float:
    """Estimate the percentage of selectors using fallback coordinates.

    Scans for ``rpakit.Selector(coords=...)`` vs. other selector types.
    """
    coord_pattern = re.compile(r"rpakit\.Selector\(\s*coords\s*=")
    all_selector_pattern = re.compile(r"rpakit\.Selector\(")

    all_count = len(all_selector_pattern.findall(script))
    coord_count = len(coord_pattern.findall(script))

    if all_count == 0:
        return 0.0
    return coord_count / all_count


# ---------------------------------------------------------------------------
# BenchmarkSuite
# ---------------------------------------------------------------------------

class BenchmarkSuite:
    """Load and run benchmark cases to measure RPA generation quality."""

    def __init__(self, suite_dir: str = "benchmarks/"):
        self.suite_dir = suite_dir
        self.cases: dict[str, dict] = {}
        self._load_cases()

    # -- loading --

    def _load_cases(self) -> None:
        """Discover and load all benchmark cases from *suite_dir*."""
        if not os.path.isdir(self.suite_dir):
            return

        for entry in sorted(os.listdir(self.suite_dir)):
            case_dir = os.path.join(self.suite_dir, entry)
            ir_path = os.path.join(case_dir, "ir.json")
            if not os.path.isfile(ir_path):
                continue

            with open(ir_path, "r", encoding="utf-8") as f:
                ir = json.load(f)

            config: dict[str, Any] = {}
            config_path = os.path.join(case_dir, "config.json")
            if os.path.isfile(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

            expected_script: str | None = None
            expected_path = os.path.join(case_dir, "expected_script.py")
            if os.path.isfile(expected_path):
                with open(expected_path, "r", encoding="utf-8") as f:
                    expected_script = f.read()

            self.cases[entry] = {
                "dir": case_dir,
                "ir": ir,
                "config": config,
                "expected_script": expected_script,
            }

    # -- generation --

    def _generate_script(self, ir: dict) -> tuple[str, float, int]:
        """Generate a script from IR via the Claude API.

        Returns (script_text, generation_time_ms, token_count).
        If the anthropic SDK is not available, falls back to a template-based
        stub so the benchmark can still exercise metric computation.
        """
        try:
            from actionshot.prompt_template import generate_api_payload
            import anthropic

            client = anthropic.Anthropic()
            payload = generate_api_payload(ir)

            start = time.perf_counter()
            message = client.messages.create(**payload)
            elapsed_ms = (time.perf_counter() - start) * 1000

            script = message.content[0].text
            # Strip markdown fences
            if script.startswith("```python"):
                script = script[len("```python"):].strip()
            if script.startswith("```"):
                script = script[3:].strip()
            if script.endswith("```"):
                script = script[:-3].strip()

            token_count = message.usage.input_tokens + message.usage.output_tokens
            return script, elapsed_ms, token_count

        except Exception:
            # Fallback: return a minimal stub so metrics still run
            start = time.perf_counter()
            lines = ['import rpakit', '', 'def run():']
            for step in ir.get("steps", []):
                op = step.get("op", "custom_step")
                sel = step.get("selector", {})
                primary = sel.get("primary", {})
                fallback = sel.get("fallback", {})

                if op == "click":
                    if primary.get("value"):
                        lines.append(
                            f'    rpakit.click(rpakit.Selector(automation_id="{primary["value"]}"))'
                        )
                    elif fallback.get("x") is not None:
                        lines.append(
                            f'    rpakit.click(rpakit.Selector(coords=({fallback["x"]}, {fallback["y"]})))'
                        )
                elif op == "fill_field":
                    val = step.get("value", "")
                    if primary.get("value"):
                        lines.append(
                            f'    rpakit.fill(rpakit.Selector(automation_id="{primary["value"]}"), "{val}")'
                        )
                    elif fallback.get("x") is not None:
                        lines.append(
                            f'    rpakit.fill(rpakit.Selector(coords=({fallback["x"]}, {fallback["y"]})), "{val}")'
                        )
                elif op == "open_app":
                    target = step.get("target", "App")
                    lines.append(f'    app = rpakit.connect(title="{target}")')
                elif op == "if_condition":
                    lines.append(f'    # Conditional: {step.get("condition", "")}')
                elif op == "loop":
                    iters = step.get("iterations", 1)
                    lines.append(f'    for _i in range({iters}):')
                    lines.append(f'        pass  # loop body')
                else:
                    lines.append(f'    # {op}: {step.get("description", "")}')

            lines.append('')
            lines.append('if __name__ == "__main__":')
            lines.append('    run()')

            elapsed_ms = (time.perf_counter() - start) * 1000
            script = "\n".join(lines)
            return script, elapsed_ms, 0

    # -- single case --

    def run_benchmark(self, case_name: str) -> dict[str, Any]:
        """Run a single benchmark case and return its metrics.

        Parameters
        ----------
        case_name : str
            Name of the case directory (e.g. ``"simple_form_fill"``).

        Returns
        -------
        dict
            Keys: ``case_name``, ``one_shot_success``, ``edit_distance``,
            ``selector_fallback_rate``, ``generation_time_ms``,
            ``token_count``, ``difficulty``, ``config``.
        """
        if case_name not in self.cases:
            raise KeyError(f"Benchmark case {case_name!r} not found in {self.suite_dir}")

        case = self.cases[case_name]
        ir = case["ir"]
        config = case["config"]
        expected = case["expected_script"]

        script, gen_time, tokens = self._generate_script(ir)

        result: dict[str, Any] = {
            "case_name": case_name,
            "difficulty": config.get("difficulty", "unknown"),
            "one_shot_success": _check_one_shot_success(script),
            "edit_distance": (
                _compute_edit_distance(script, expected) if expected else None
            ),
            "selector_fallback_rate": _compute_selector_fallback_rate(script),
            "generation_time_ms": round(gen_time, 2),
            "token_count": tokens,
            "config": config,
            "generated_script": script,
        }

        # Save the generated script alongside the case
        out_path = os.path.join(case["dir"], "generated_script.py")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(script)

        return result

    # -- run all --

    def run_all(self) -> dict[str, Any]:
        """Run every loaded benchmark case and return an aggregate report.

        Returns
        -------
        dict
            Keys: ``cases`` (list of per-case results), ``summary`` (aggregates).
        """
        case_results = []
        for name in self.cases:
            try:
                result = self.run_benchmark(name)
                case_results.append(result)
            except Exception as exc:
                case_results.append({
                    "case_name": name,
                    "error": str(exc),
                })

        # Aggregate
        successful = [r for r in case_results if r.get("one_shot_success")]
        total = len(case_results)
        errors = [r for r in case_results if "error" in r]

        edit_distances = [
            r["edit_distance"]
            for r in case_results
            if r.get("edit_distance") is not None
        ]

        fallback_rates = [
            r["selector_fallback_rate"]
            for r in case_results
            if "selector_fallback_rate" in r
        ]

        gen_times = [
            r["generation_time_ms"]
            for r in case_results
            if "generation_time_ms" in r
        ]

        token_counts = [
            r["token_count"]
            for r in case_results
            if r.get("token_count")
        ]

        summary: dict[str, Any] = {
            "total_cases": total,
            "one_shot_success_rate": len(successful) / total if total else 0.0,
            "error_count": len(errors),
            "avg_edit_distance": (
                sum(edit_distances) / len(edit_distances) if edit_distances else None
            ),
            "avg_selector_fallback_rate": (
                sum(fallback_rates) / len(fallback_rates) if fallback_rates else 0.0
            ),
            "avg_generation_time_ms": (
                round(sum(gen_times) / len(gen_times), 2) if gen_times else 0.0
            ),
            "avg_token_count": (
                round(sum(token_counts) / len(token_counts)) if token_counts else 0
            ),
        }

        # Per-difficulty breakdown
        by_difficulty: dict[str, list] = {}
        for r in case_results:
            diff = r.get("difficulty", "unknown")
            by_difficulty.setdefault(diff, []).append(r)

        difficulty_summary: dict[str, dict] = {}
        for diff, cases in by_difficulty.items():
            ok = [c for c in cases if c.get("one_shot_success")]
            difficulty_summary[diff] = {
                "count": len(cases),
                "success_rate": len(ok) / len(cases) if cases else 0.0,
            }

        summary["by_difficulty"] = difficulty_summary

        return {
            "cases": case_results,
            "summary": summary,
        }

    # -- compare --

    @staticmethod
    def compare(report_a: dict, report_b: dict) -> dict[str, Any]:
        """Compare two benchmark reports and detect regressions.

        Parameters
        ----------
        report_a : dict
            The baseline report (from ``run_all()``).
        report_b : dict
            The new report to compare against the baseline.

        Returns
        -------
        dict
            Per-metric deltas and a list of regressions.
        """
        sa = report_a.get("summary", {})
        sb = report_b.get("summary", {})

        def _delta(key: str, higher_is_better: bool = True):
            va = sa.get(key)
            vb = sb.get(key)
            if va is None or vb is None:
                return {"baseline": va, "new": vb, "delta": None, "regression": False}
            delta = vb - va
            regression = (delta < 0) if higher_is_better else (delta > 0)
            return {
                "baseline": va,
                "new": vb,
                "delta": round(delta, 4) if isinstance(delta, float) else delta,
                "regression": regression,
            }

        deltas = {
            "one_shot_success_rate": _delta("one_shot_success_rate", higher_is_better=True),
            "avg_edit_distance": _delta("avg_edit_distance", higher_is_better=False),
            "avg_selector_fallback_rate": _delta("avg_selector_fallback_rate", higher_is_better=False),
            "avg_generation_time_ms": _delta("avg_generation_time_ms", higher_is_better=False),
            "avg_token_count": _delta("avg_token_count", higher_is_better=False),
        }

        regressions = [
            metric for metric, info in deltas.items() if info.get("regression")
        ]

        # Per-case comparison
        cases_a = {c["case_name"]: c for c in report_a.get("cases", []) if "case_name" in c}
        cases_b = {c["case_name"]: c for c in report_b.get("cases", []) if "case_name" in c}

        per_case: list[dict] = []
        for name in sorted(set(cases_a) | set(cases_b)):
            ca = cases_a.get(name, {})
            cb = cases_b.get(name, {})
            entry: dict[str, Any] = {"case_name": name}

            if ca.get("one_shot_success") and not cb.get("one_shot_success"):
                entry["regression"] = "one_shot_success lost"
            elif not ca.get("one_shot_success") and cb.get("one_shot_success"):
                entry["improvement"] = "one_shot_success gained"

            ed_a = ca.get("edit_distance")
            ed_b = cb.get("edit_distance")
            if ed_a is not None and ed_b is not None:
                entry["edit_distance_delta"] = ed_b - ed_a

            per_case.append(entry)

        return {
            "deltas": deltas,
            "regressions": regressions,
            "per_case": per_case,
            "has_regressions": len(regressions) > 0,
        }

    # -- I/O --

    @staticmethod
    def save_report(report: dict, path: str) -> None:
        """Save a benchmark report as JSON."""
        # Strip generated_script from saved reports to keep them small
        clean = json.loads(json.dumps(report))
        for case in clean.get("cases", []):
            case.pop("generated_script", None)

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=2, ensure_ascii=False)

    @staticmethod
    def print_report(report: dict) -> None:
        """Pretty-print a benchmark report to the console."""
        summary = report.get("summary", {})
        cases = report.get("cases", [])

        print("=" * 70)
        print("  ActionShot Benchmark Report")
        print("=" * 70)
        print()

        print(f"  Total cases:              {summary.get('total_cases', 0)}")
        print(f"  One-shot success rate:    {summary.get('one_shot_success_rate', 0):.1%}")
        print(f"  Errors:                   {summary.get('error_count', 0)}")
        print()

        avg_ed = summary.get("avg_edit_distance")
        if avg_ed is not None:
            print(f"  Avg edit distance:        {avg_ed:.1f} lines")
        print(f"  Avg fallback rate:        {summary.get('avg_selector_fallback_rate', 0):.1%}")
        print(f"  Avg generation time:      {summary.get('avg_generation_time_ms', 0):.0f} ms")
        print(f"  Avg token count:          {summary.get('avg_token_count', 0)}")
        print()

        # Per-difficulty
        by_diff = summary.get("by_difficulty", {})
        if by_diff:
            print("  By difficulty:")
            for diff, info in sorted(by_diff.items()):
                print(
                    f"    {diff:15s}  {info['count']} cases, "
                    f"{info['success_rate']:.0%} success"
                )
            print()

        # Per-case table
        print("  " + "-" * 66)
        print(f"  {'Case':<30s} {'Success':>8s} {'Edit':>6s} {'Fallback':>9s} {'Time':>8s}")
        print("  " + "-" * 66)

        for case in cases:
            if "error" in case:
                print(f"  {case['case_name']:<30s} {'ERROR':>8s}")
                continue

            name = case.get("case_name", "?")[:30]
            ok = "yes" if case.get("one_shot_success") else "no"
            ed = case.get("edit_distance")
            ed_str = f"{ed}" if ed is not None else "-"
            fb = case.get("selector_fallback_rate", 0)
            t = case.get("generation_time_ms", 0)
            print(f"  {name:<30s} {ok:>8s} {ed_str:>6s} {fb:>8.0%} {t:>7.0f}ms")

        print("  " + "-" * 66)
        print()

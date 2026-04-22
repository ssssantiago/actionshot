"""Rich terminal UI for ActionShot status, sessions, and metrics.

Uses only stdlib -- no curses or third-party dependencies.  Works on
Windows Terminal, CMD (with ANSI support), and any Unix terminal.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# ANSI colour helpers (with graceful fallback)
# ---------------------------------------------------------------------------

def _supports_color() -> bool:
    """Return True when the terminal likely supports ANSI escape codes."""
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("FORCE_COLOR"):
        return True
    if sys.platform == "win32":
        # Windows 10+ with VT processing or Windows Terminal
        return os.getenv("WT_SESSION") is not None or os.getenv("TERM_PROGRAM") is not None
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_COLOR = _supports_color()


def _ansi(code: str) -> str:
    return code if _COLOR else ""


# Foreground colours
RED = _ansi("\033[91m")
GREEN = _ansi("\033[92m")
YELLOW = _ansi("\033[93m")
BLUE = _ansi("\033[94m")
MAGENTA = _ansi("\033[95m")
CYAN = _ansi("\033[96m")
ORANGE = _ansi("\033[38;5;208m")
GRAY = _ansi("\033[90m")
WHITE = _ansi("\033[97m")
BOLD = _ansi("\033[1m")
DIM = _ansi("\033[2m")
RESET = _ansi("\033[0m")

# Action-type colour map
ACTION_COLORS: dict[str, str] = {
    "click": RED,
    "double_click": RED,
    "right_click": RED,
    "scroll": BLUE,
    "key": YELLOW,
    "type": YELLOW,
    "hotkey": YELLOW,
    "drag": ORANGE,
    "move": CYAN,
    "wait": GRAY,
}


def _action_color(action_type: str) -> str:
    """Return the ANSI colour prefix for a given action type."""
    return ACTION_COLORS.get(action_type, WHITE)


# ---------------------------------------------------------------------------
# Box-drawing helpers
# ---------------------------------------------------------------------------

BOX_TL = "\u2554"  # top-left double
BOX_TR = "\u2557"  # top-right double
BOX_BL = "\u255a"  # bottom-left double
BOX_BR = "\u255d"  # bottom-right double
BOX_H = "\u2550"   # horizontal double
BOX_V = "\u2551"   # vertical double
BOX_SH = "\u2500"  # single horizontal
BOX_SV = "\u2502"  # single vertical
BOX_STL = "\u250c" # single top-left
BOX_STR = "\u2510" # single top-right
BOX_SBL = "\u2514" # single bottom-left
BOX_SBR = "\u2518" # single bottom-right


def _box(title: str, lines: list[str], width: int = 60) -> str:
    """Render *lines* inside a double-line box with a *title*."""
    inner = width - 2
    parts: list[str] = []

    # Title bar
    title_text = f" {title} "
    pad = inner - len(title_text)
    parts.append(f"{BOX_TL}{BOX_H}{BOLD}{title_text}{RESET}{BOX_H * pad}{BOX_TR}")

    for line in lines:
        visible_len = len(_strip_ansi(line))
        padding = max(0, inner - visible_len)
        parts.append(f"{BOX_V} {line}{' ' * padding}{BOX_V}")

    parts.append(f"{BOX_BL}{BOX_H * inner}{BOX_H}{BOX_BR}")
    return "\n".join(parts)


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences to compute visible length."""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)


def _bar(value: float, max_value: float, width: int = 30) -> str:
    """Render a Unicode block bar chart segment."""
    blocks = " \u258f\u258e\u258d\u258c\u258b\u258a\u2589\u2588"
    if max_value <= 0:
        return " " * width
    ratio = min(value / max_value, 1.0)
    full_blocks = int(ratio * width)
    remainder = (ratio * width) - full_blocks
    idx = int(remainder * 8)
    bar_str = "\u2588" * full_blocks
    if idx > 0 and full_blocks < width:
        bar_str += blocks[idx]
        full_blocks += 1
    bar_str += " " * (width - full_blocks)
    return bar_str


def _table(headers: list[str], rows: list[list[str]], col_widths: list[int] | None = None) -> str:
    """Render a simple table with single-line box-drawing borders."""
    if col_widths is None:
        col_widths = []
        for i, h in enumerate(headers):
            max_w = len(h)
            for row in rows:
                if i < len(row):
                    max_w = max(max_w, len(_strip_ansi(row[i])))
            col_widths.append(max_w)

    def _row_line(cells: list[str]) -> str:
        parts = []
        for i, cell in enumerate(cells):
            w = col_widths[i] if i < len(col_widths) else 12
            vis = len(_strip_ansi(cell))
            pad = max(0, w - vis)
            parts.append(f" {cell}{' ' * pad} ")
        return f"{BOX_SV}{''.join(f'{BOX_SV}'.join([]) if False else ''}" + f"{BOX_SV}".join(parts) + f"{BOX_SV}"

    sep_cells = [BOX_SH * (w + 2) for w in col_widths]
    top = f"{BOX_STL}{''.join(BOX_SH + s for s in sep_cells[1:])}" if False else ""
    top = BOX_STL + ("\u252c".join(sep_cells)) + BOX_STR
    mid = BOX_SBL.replace(BOX_SBL, "\u251c") + ("\u253c".join(sep_cells)) + BOX_STR.replace(BOX_STR, "\u2524")
    bottom = BOX_SBL + ("\u2534".join(sep_cells)) + BOX_SBR

    result = [top]
    # Header
    result.append(_row_line(headers))
    result.append(mid)
    for row in rows:
        # Pad row to match headers length
        padded = list(row) + [""] * (len(headers) - len(row))
        result.append(_row_line(padded))
    result.append(bottom)
    return "\n".join(result)


# ---------------------------------------------------------------------------
# TerminalDashboard
# ---------------------------------------------------------------------------

class TerminalDashboard:
    """Pretty terminal output for ActionShot status."""

    def __init__(self, recordings_dir: str = "recordings") -> None:
        self.recordings_dir = recordings_dir

    # -- helpers ----------------------------------------------------------

    def _count_sessions(self) -> int:
        """Count session directories in the recordings folder."""
        if not os.path.isdir(self.recordings_dir):
            return 0
        return sum(
            1 for d in os.listdir(self.recordings_dir)
            if os.path.isdir(os.path.join(self.recordings_dir, d))
            and d.startswith("session_")
        )

    def _latest_session(self) -> str | None:
        """Return the name of the most recent session, or None."""
        if not os.path.isdir(self.recordings_dir):
            return None
        sessions = sorted(
            (d for d in os.listdir(self.recordings_dir)
             if os.path.isdir(os.path.join(self.recordings_dir, d))
             and d.startswith("session_")),
            reverse=True,
        )
        return sessions[0] if sessions else None

    def _load_session_summary(self, session_path: str) -> dict | None:
        """Load session_summary.json from a session directory."""
        summary_file = os.path.join(session_path, "session_summary.json")
        if not os.path.isfile(summary_file):
            return None
        with open(summary_file, "r", encoding="utf-8") as f:
            return json.load(f)

    # -- public API -------------------------------------------------------

    def show_status(self) -> None:
        """Print a formatted status overview."""
        from actionshot.telemetry import DashboardData

        session_count = self._count_sessions()
        latest = self._latest_session()

        # Try to pull telemetry summary
        try:
            dash = DashboardData()
            summary = dash.summary()
            active_workflows = summary.get("total_workflows", 0)
            avg_success = summary.get("avg_success_rate", 0.0)
            active_today = summary.get("active_today", 0)
        except Exception:
            active_workflows = 0
            avg_success = 0.0
            active_today = 0

        # Colour the success rate
        if avg_success >= 90:
            rate_color = GREEN
        elif avg_success >= 70:
            rate_color = YELLOW
        else:
            rate_color = RED

        lines = [
            f"{BOLD}Recordings:{RESET}       {CYAN}{session_count}{RESET} sessions",
            f"{BOLD}Last recording:{RESET}    {latest or GRAY + 'none' + RESET}",
            f"{BOLD}Workflows:{RESET}         {CYAN}{active_workflows}{RESET} tracked",
            f"{BOLD}Active today:{RESET}      {CYAN}{active_today}{RESET}",
            f"{BOLD}Avg success rate:{RESET}  {rate_color}{avg_success:.1f}%{RESET}",
        ]

        print()
        print(_box("ActionShot Status", lines, width=52))
        print()

    def show_session(self, session_path: str) -> None:
        """Print formatted session details in terminal."""
        summary = self._load_session_summary(session_path)
        if summary is None:
            print(f"{RED}Error:{RESET} No session_summary.json found in {session_path}")
            return

        session_name = summary.get("session", os.path.basename(session_path))
        steps = summary.get("steps", [])
        total = summary.get("total_steps", len(steps))

        # Header
        print()
        print(f"  {BOLD}{CYAN}Session:{RESET} {session_name}")
        print(f"  {BOLD}Steps:{RESET}   {total}")
        print()

        if not steps:
            print(f"  {GRAY}(no steps recorded){RESET}")
            return

        # Step table
        headers = ["#", "Action", "Target", "Timestamp"]
        rows: list[list[str]] = []
        for i, step in enumerate(steps, 1):
            action = step.get("action", step.get("type", "?"))
            color = _action_color(action)
            target = step.get("window_title", step.get("target", ""))
            if len(target) > 30:
                target = target[:27] + "..."
            ts = step.get("timestamp", "")
            if len(ts) > 19:
                ts = ts[:19]
            rows.append([
                f"{GRAY}{i:>3}{RESET}",
                f"{color}{action:<14}{RESET}",
                target,
                f"{DIM}{ts}{RESET}",
            ])

        print(_table(headers, rows))
        print()

        # ASCII timeline
        print(f"  {BOLD}Timeline:{RESET}")
        print()
        timeline_width = min(len(steps), 60)
        bar_chars: list[str] = []
        for step in steps[:60]:
            action = step.get("action", step.get("type", "?"))
            color = _action_color(action)
            bar_chars.append(f"{color}\u2588{RESET}")
        print(f"  {''.join(bar_chars)}")

        # Legend
        seen: set[str] = set()
        legend_parts: list[str] = []
        for step in steps:
            action = step.get("action", step.get("type", "?"))
            if action not in seen:
                seen.add(action)
                color = _action_color(action)
                legend_parts.append(f"{color}\u2588{RESET} {action}")
        print(f"  {GRAY}{'  '.join(legend_parts)}{RESET}")
        print()

    def show_metrics(self, workflow_id: str | None = None) -> None:
        """Print telemetry metrics as formatted tables and bar charts."""
        from actionshot.telemetry import DashboardData

        dash = DashboardData()

        if workflow_id:
            self._print_workflow_metrics(dash, workflow_id)
        else:
            self._print_all_metrics(dash)

    def _print_all_metrics(self, dash: Any) -> None:
        """Print summary metrics for all workflows."""
        try:
            workflows = dash._tracker.get_all_workflows()
        except Exception:
            workflows = []

        if not workflows:
            print(f"\n  {GRAY}No workflow metrics found.{RESET}")
            print(f"  {GRAY}Run some workflows to generate telemetry data.{RESET}\n")
            return

        print()
        headers = ["Workflow", "Runs", "Success", "Avg (ms)", "P95 (ms)"]
        rows: list[list[str]] = []

        max_runs = max((w["total_executions"] for w in workflows), default=1)

        for w in workflows:
            wf_id = w["workflow_id"]
            if len(wf_id) > 25:
                wf_id = wf_id[:22] + "..."
            runs = w["total_executions"]
            rate = w["success_rate"]

            if rate >= 90:
                rate_str = f"{GREEN}{rate:.1f}%{RESET}"
            elif rate >= 70:
                rate_str = f"{YELLOW}{rate:.1f}%{RESET}"
            else:
                rate_str = f"{RED}{rate:.1f}%{RESET}"

            rows.append([
                f"{BOLD}{wf_id}{RESET}",
                str(runs),
                rate_str,
                f"{w['avg_duration_ms']:.0f}",
                f"{w['p95_duration_ms']:.0f}",
            ])

        print(_table(headers, rows))
        print()

        # Bar chart of execution counts
        print(f"  {BOLD}Executions per workflow:{RESET}")
        print()
        for w in workflows:
            wf_id = w["workflow_id"]
            if len(wf_id) > 20:
                wf_id = wf_id[:17] + "..."
            runs = w["total_executions"]
            bar = _bar(runs, max_runs, width=25)
            print(f"  {wf_id:<20s} {CYAN}{bar}{RESET} {runs}")
        print()

    def _print_workflow_metrics(self, dash: Any, workflow_id: str) -> None:
        """Print detailed metrics for a single workflow."""
        details = dash.workflow_details(workflow_id)

        rate = details.get("success_rate", 0.0)
        if rate >= 90:
            rate_color = GREEN
        elif rate >= 70:
            rate_color = YELLOW
        else:
            rate_color = RED

        lines = [
            f"{BOLD}Workflow:{RESET}          {CYAN}{workflow_id}{RESET}",
            f"{BOLD}Total executions:{RESET}  {details.get('total_executions', 0)}",
            f"{BOLD}Successes:{RESET}         {GREEN}{details.get('success_count', 0)}{RESET}",
            f"{BOLD}Failures:{RESET}          {RED}{details.get('failure_count', 0)}{RESET}",
            f"{BOLD}Success rate:{RESET}      {rate_color}{rate:.1f}%{RESET}",
            f"{BOLD}Avg duration:{RESET}      {details.get('avg_duration_ms', 0):.0f} ms",
            f"{BOLD}P95 duration:{RESET}      {details.get('p95_duration_ms', 0):.0f} ms",
            f"{BOLD}Fallback rate:{RESET}     {details.get('selector_fallback_rate', 0):.1f}%",
            f"{BOLD}Healing iters:{RESET}     {details.get('healing_iterations', 0):.1f}",
        ]

        last = details.get("last_execution")
        if last:
            status = last.get("status", "?")
            ts = last.get("timestamp", "?")
            status_color = GREEN if status == "success" else RED
            lines.append(f"{BOLD}Last run:{RESET}          {status_color}{status}{RESET} at {DIM}{ts}{RESET}")

        print()
        print(_box(f"Workflow: {workflow_id}", lines, width=62))
        print()

        # Recent failures
        failures = details.get("recent_failures", [])
        if failures:
            print(f"  {BOLD}{RED}Recent failures:{RESET}")
            for f_entry in failures[-5:]:
                ts = f_entry.get("timestamp", "?")
                err = f_entry.get("error", f_entry.get("status", "?"))
                if isinstance(err, str) and len(err) > 50:
                    err = err[:47] + "..."
                print(f"    {DIM}{ts}{RESET}  {RED}{err}{RESET}")
            print()

    def show_benchmark(self, report: dict) -> None:
        """Print benchmark results as a formatted table."""
        cases = report.get("results", report.get("cases", []))
        if not cases:
            print(f"\n  {GRAY}No benchmark results to display.{RESET}\n")
            return

        print()
        headers = ["Case", "Difficulty", "Parse", "Edit Dist", "Time (s)"]
        rows: list[list[str]] = []

        for case in cases:
            name = case.get("name", case.get("case_id", "?"))
            if len(name) > 25:
                name = name[:22] + "..."
            difficulty = case.get("difficulty", "?")
            parsed = case.get("parses", case.get("parse_success", False))
            parse_str = f"{GREEN}PASS{RESET}" if parsed else f"{RED}FAIL{RESET}"
            edit_dist = case.get("edit_distance", "?")
            gen_time = case.get("generation_time", case.get("time_s", 0))

            rows.append([name, difficulty, parse_str, str(edit_dist), f"{gen_time:.2f}"])

        print(_table(headers, rows))
        print()

    def live_recording(self, recorder: Any) -> None:
        """Show live recording status with updating step count.

        Updates in-place using carriage return.  Blocks until the
        recorder finishes (its ``running`` attribute becomes False).
        """
        print()
        print(f"  {BOLD}{RED}\u25cf RECORDING{RESET}  Press ESC or Ctrl+C to stop.")
        print()

        try:
            while getattr(recorder, "running", False):
                step_count = getattr(recorder, "step_count", 0)
                if hasattr(recorder, "session") and recorder.session:
                    step_count = recorder.session.step_count
                elapsed = getattr(recorder, "elapsed", 0)
                sys.stdout.write(
                    f"\r  {CYAN}Steps:{RESET} {step_count:<6}  "
                    f"{CYAN}Elapsed:{RESET} {elapsed:.0f}s   "
                )
                sys.stdout.flush()
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

        print()
        print(f"\n  {GREEN}\u25a0 Recording stopped.{RESET}\n")

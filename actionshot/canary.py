"""Canary deployment for new RPA workflows.

Implements a gradual rollout strategy so that newly generated scripts
are validated in production before full adoption:

    Phase 0 (Week 1)  -- dry-run only, manual review of logs
    Phase 1 (Week 2)  -- 10 % real execution, 90 % dry-run in parallel
    Phase 2 (Week 3+) -- 100 % real execution if metrics are stable

Canary state is persisted in ``~/.actionshot/canary.json``.
"""

import json
import os
import random
import time
from datetime import datetime, timedelta
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PHASES = [
    {
        "phase": 0,
        "name": "dry_run_only",
        "description": "Dry-run only, manual review of logs",
        "real_exec_pct": 0.0,
        "min_days": 7,
    },
    {
        "phase": 1,
        "name": "partial_rollout",
        "description": "10% real execution, 90% dry-run in parallel",
        "real_exec_pct": 0.10,
        "min_days": 7,
    },
    {
        "phase": 2,
        "name": "full_rollout",
        "description": "100% real execution if metrics stable",
        "real_exec_pct": 1.0,
        "min_days": None,  # terminal phase
    },
]

# Thresholds for automatic advancement
_ADVANCE_MIN_RUNS = 5
_ADVANCE_MIN_SUCCESS_RATE = 0.90
_ADVANCE_MAX_AVG_DURATION_MS = 120_000  # 2 minutes


# ---------------------------------------------------------------------------
# CanaryDeployment
# ---------------------------------------------------------------------------

class CanaryDeployment:
    """Gradual rollout for new RPA workflows."""

    CANARY_FILE = os.path.expanduser("~/.actionshot/canary.json")

    def __init__(self, canary_file: str | None = None):
        if canary_file is not None:
            self.CANARY_FILE = canary_file
        self._data: dict[str, Any] = self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        """Load canary state from disk."""
        if os.path.isfile(self.CANARY_FILE):
            with open(self.CANARY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"workflows": {}}

    def _save(self) -> None:
        """Persist canary state to disk."""
        os.makedirs(os.path.dirname(self.CANARY_FILE), exist_ok=True)
        with open(self.CANARY_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    # -- public API ---------------------------------------------------------

    def register(self, workflow_id: str, script_path: str) -> None:
        """Register a new workflow for canary deployment.

        If the workflow is already registered, this is a no-op.

        Parameters
        ----------
        workflow_id : str
            Unique identifier for the workflow.
        script_path : str
            Filesystem path to the generated script.
        """
        workflows = self._data.setdefault("workflows", {})
        if workflow_id in workflows:
            return

        now = datetime.utcnow().isoformat()
        workflows[workflow_id] = {
            "script_path": script_path,
            "phase": 0,
            "phase_started": now,
            "registered_at": now,
            "metrics": {
                "total_runs": 0,
                "real_runs": 0,
                "dry_runs": 0,
                "successes": 0,
                "failures": 0,
                "total_duration_ms": 0.0,
                "phase_runs": 0,
                "phase_successes": 0,
                "phase_failures": 0,
                "phase_total_duration_ms": 0.0,
            },
        }
        self._save()

    def get_phase(self, workflow_id: str) -> dict:
        """Return current phase, start date, and metrics.

        Parameters
        ----------
        workflow_id : str
            The workflow to query.

        Returns
        -------
        dict
            Keys: ``phase``, ``phase_name``, ``phase_description``,
            ``phase_started``, ``registered_at``, ``metrics``,
            ``real_exec_pct``.

        Raises
        ------
        KeyError
            If the workflow is not registered.
        """
        wf = self._get_workflow(workflow_id)
        phase_idx = wf["phase"]
        phase_def = _PHASES[phase_idx]
        return {
            "phase": phase_idx,
            "phase_name": phase_def["name"],
            "phase_description": phase_def["description"],
            "phase_started": wf["phase_started"],
            "registered_at": wf["registered_at"],
            "real_exec_pct": phase_def["real_exec_pct"],
            "metrics": dict(wf["metrics"]),
        }

    def should_execute_real(self, workflow_id: str) -> bool:
        """Decide whether this execution should be real or dry-run.

        Based on the current phase and random sampling against the
        phase's ``real_exec_pct``.

        Parameters
        ----------
        workflow_id : str
            The workflow to query.

        Returns
        -------
        bool
            ``True`` for real execution, ``False`` for dry-run.
        """
        wf = self._get_workflow(workflow_id)
        phase_def = _PHASES[wf["phase"]]
        pct = phase_def["real_exec_pct"]
        if pct >= 1.0:
            return True
        if pct <= 0.0:
            return False
        return random.random() < pct

    def record_execution(
        self,
        workflow_id: str,
        *,
        real: bool,
        success: bool,
        duration_ms: float,
    ) -> None:
        """Record the outcome of a single execution.

        Parameters
        ----------
        workflow_id : str
            The workflow that ran.
        real : bool
            Whether this was a real execution (vs. dry-run).
        success : bool
            Whether the execution succeeded.
        duration_ms : float
            Wall-clock duration in milliseconds.
        """
        wf = self._get_workflow(workflow_id)
        m = wf["metrics"]
        m["total_runs"] += 1
        m["phase_runs"] += 1
        m["total_duration_ms"] += duration_ms
        m["phase_total_duration_ms"] += duration_ms

        if real:
            m["real_runs"] += 1
        else:
            m["dry_runs"] += 1

        if success:
            m["successes"] += 1
            m["phase_successes"] += 1
        else:
            m["failures"] += 1
            m["phase_failures"] += 1

        self._save()

    def advance_phase(self, workflow_id: str) -> bool:
        """Check metrics and advance to the next phase if stable.

        Advancement criteria:
        - At least ``_ADVANCE_MIN_RUNS`` runs in the current phase
        - Success rate >= ``_ADVANCE_MIN_SUCCESS_RATE``
        - Average duration <= ``_ADVANCE_MAX_AVG_DURATION_MS``
        - Minimum time in phase has elapsed (``min_days``)

        Parameters
        ----------
        workflow_id : str
            The workflow to advance.

        Returns
        -------
        bool
            ``True`` if the phase was advanced, ``False`` otherwise.
        """
        wf = self._get_workflow(workflow_id)
        current = wf["phase"]

        # Already at terminal phase
        if current >= len(_PHASES) - 1:
            return False

        phase_def = _PHASES[current]
        m = wf["metrics"]

        # Check minimum runs
        if m["phase_runs"] < _ADVANCE_MIN_RUNS:
            return False

        # Check success rate
        success_rate = m["phase_successes"] / m["phase_runs"]
        if success_rate < _ADVANCE_MIN_SUCCESS_RATE:
            return False

        # Check average duration
        avg_duration = m["phase_total_duration_ms"] / m["phase_runs"]
        if avg_duration > _ADVANCE_MAX_AVG_DURATION_MS:
            return False

        # Check minimum days in phase
        min_days = phase_def.get("min_days")
        if min_days is not None:
            started = datetime.fromisoformat(wf["phase_started"])
            if datetime.utcnow() - started < timedelta(days=min_days):
                return False

        # Advance
        self._set_phase(wf, current + 1)
        self._save()
        return True

    def force_phase(self, workflow_id: str, phase: int) -> None:
        """Manually set the phase (for overrides).

        Parameters
        ----------
        workflow_id : str
            The workflow to modify.
        phase : int
            Target phase number (0, 1, or 2).

        Raises
        ------
        ValueError
            If *phase* is out of range.
        """
        if phase < 0 or phase >= len(_PHASES):
            raise ValueError(
                f"Phase must be between 0 and {len(_PHASES) - 1}, got {phase}"
            )
        wf = self._get_workflow(workflow_id)
        self._set_phase(wf, phase)
        self._save()

    def get_metrics(self, workflow_id: str) -> dict:
        """Return metrics for the workflow in the current phase.

        Parameters
        ----------
        workflow_id : str
            The workflow to query.

        Returns
        -------
        dict
            Keys: ``success_rate``, ``avg_duration_ms``,
            ``total_runs``, ``phase_runs``, ``failures``.
        """
        wf = self._get_workflow(workflow_id)
        m = wf["metrics"]
        phase_runs = m["phase_runs"]
        return {
            "success_rate": (
                m["phase_successes"] / phase_runs if phase_runs > 0 else 0.0
            ),
            "avg_duration_ms": (
                m["phase_total_duration_ms"] / phase_runs if phase_runs > 0 else 0.0
            ),
            "total_runs": m["total_runs"],
            "phase_runs": phase_runs,
            "failures": m["phase_failures"],
        }

    def list_all(self) -> list[dict]:
        """List all workflows with their canary status.

        Returns
        -------
        list[dict]
            Each entry has ``workflow_id``, ``phase``, ``phase_name``,
            ``registered_at``, ``phase_started``, ``metrics``.
        """
        result = []
        for wf_id, wf in self._data.get("workflows", {}).items():
            phase_idx = wf["phase"]
            phase_def = _PHASES[phase_idx]
            result.append({
                "workflow_id": wf_id,
                "phase": phase_idx,
                "phase_name": phase_def["name"],
                "script_path": wf.get("script_path", ""),
                "registered_at": wf["registered_at"],
                "phase_started": wf["phase_started"],
                "metrics": dict(wf["metrics"]),
            })
        return result

    # -- internal helpers ---------------------------------------------------

    def _get_workflow(self, workflow_id: str) -> dict:
        """Return workflow dict or raise KeyError."""
        workflows = self._data.get("workflows", {})
        if workflow_id not in workflows:
            raise KeyError(
                f"Workflow {workflow_id!r} is not registered for canary deployment"
            )
        return workflows[workflow_id]

    @staticmethod
    def _set_phase(wf: dict, phase: int) -> None:
        """Set phase and reset phase-level metrics."""
        wf["phase"] = phase
        wf["phase_started"] = datetime.utcnow().isoformat()
        wf["metrics"]["phase_runs"] = 0
        wf["metrics"]["phase_successes"] = 0
        wf["metrics"]["phase_failures"] = 0
        wf["metrics"]["phase_total_duration_ms"] = 0.0

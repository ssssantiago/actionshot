"""Multi-recording support - record the same workflow multiple times to infer variables.

Users record the same workflow 3+ times with different data.  The system then
diffs the recordings to determine which typed values are constants (same every
time) and which are variables (change between runs).
"""

import json
import os
import re
from datetime import datetime
from typing import Any

from .recorder import Recorder
from .diff import SessionDiff


# ---------------------------------------------------------------------------
# Format detectors — Brazilian document / data patterns
# ---------------------------------------------------------------------------

def detect_cpf(value: str) -> tuple[bool, str]:
    """Detect Brazilian CPF (###.###.###-## or 11 digits)."""
    v = value.strip()
    if re.match(r"^\d{3}[\.\-]?\d{3}[\.\-]?\d{3}[\.\-]?\d{2}$", v):
        return True, "cpf"
    return False, ""


def detect_cnpj(value: str) -> tuple[bool, str]:
    """Detect Brazilian CNPJ (##.###.###/####-## or 14 digits)."""
    v = value.strip()
    if re.match(r"^\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}$", v):
        return True, "cnpj"
    return False, ""


def detect_email(value: str) -> tuple[bool, str]:
    """Detect email addresses."""
    v = value.strip()
    if re.match(r"^[^@\s]+@[^@\s]+\.\w+$", v):
        return True, "email"
    return False, ""


def detect_date(value: str) -> tuple[bool, str]:
    """Detect date patterns (dd/mm/yyyy, yyyy-mm-dd, etc.)."""
    v = value.strip()
    if re.match(r"^\d{2}/\d{2}/\d{4}$", v):
        return True, "data"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
        return True, "data"
    if re.match(r"^\d{2}\.\d{2}\.\d{4}$", v):
        return True, "data"
    return False, ""


def detect_processo(value: str) -> tuple[bool, str]:
    """Detect Brazilian legal process number (NNNNNNN-NN.NNNN.N.NN.NNNN)."""
    v = value.strip()
    if re.match(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$", v):
        return True, "numero_processo"
    # Looser pattern: long digit sequences with dots/dashes typical of process numbers
    if re.match(r"^\d{5,7}[-.]?\d{2}[-.]?\d{4}[-.]?\d[-.]?\d{2}[-.]?\d{4}$", v):
        return True, "numero_processo"
    return False, ""


def detect_phone(value: str) -> tuple[bool, str]:
    """Detect phone numbers (Brazilian and general)."""
    v = value.strip()
    # Brazilian: (##) #####-#### or (##) ####-####
    if re.match(r"^\(?\d{2}\)?\s?\d{4,5}-?\d{4}$", v):
        return True, "telefone"
    # General international
    if re.match(r"^\+?\d[\d\s\-]{7,14}$", v):
        return True, "telefone"
    return False, ""


_FORMAT_DETECTORS = [
    detect_cpf,
    detect_cnpj,
    detect_processo,
    detect_email,
    detect_date,
    detect_phone,
]


def _detect_format(value: str) -> str | None:
    """Run all format detectors; return the first matching variable name or None."""
    for detector in _FORMAT_DETECTORS:
        matched, name = detector(value)
        if matched:
            return name
    return None


def _slugify(text: str) -> str:
    """Turn a human string into a safe variable name."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    slug = slug.strip("_")
    return slug[:40] or "value"


# ---------------------------------------------------------------------------
# MultiRecordingSession — orchestrate N recordings of the same workflow
# ---------------------------------------------------------------------------

class MultiRecordingSession:
    """Manage multiple recordings of the same workflow.

    Creates a parent folder structure::

        recordings/multi_{workflow_name}_{timestamp}/
            recording_1/
            recording_2/
            recording_3/
    """

    def __init__(self, workflow_name: str, num_recordings: int = 3,
                 output_dir: str = "recordings"):
        self.workflow_name = workflow_name
        self.num_recordings = num_recordings
        self.output_dir = output_dir

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.parent_dir = os.path.join(
            output_dir, f"multi_{workflow_name}_{timestamp}"
        )
        os.makedirs(self.parent_dir, exist_ok=True)

        self._current_index = 0  # 0 = not started yet
        self._completed_paths: list[str] = []
        self._current_recorder: Recorder | None = None

    # -- properties --

    @property
    def current_index(self) -> int:
        """1-based index of the recording we are currently on (0 if not started)."""
        return self._current_index

    @property
    def is_complete(self) -> bool:
        """True when all N recordings have been completed."""
        return len(self._completed_paths) >= self.num_recordings

    # -- public API --

    def start_next(self) -> Recorder:
        """Start recording the next session.

        Returns the ``Recorder`` instance so the caller can interact with it
        (e.g. to call ``stop()``).

        Raises ``RuntimeError`` if all sessions have already been recorded or
        if a session is currently in progress.
        """
        if self.is_complete:
            raise RuntimeError(
                f"All {self.num_recordings} recordings are already complete."
            )
        if self._current_recorder is not None and self._current_recorder.running:
            raise RuntimeError(
                "A recording is already in progress. Call stop_current() first."
            )

        self._current_index += 1
        session_dir = os.path.join(self.parent_dir, f"recording_{self._current_index}")
        os.makedirs(session_dir, exist_ok=True)

        self._current_recorder = Recorder(output_dir=session_dir)

        print(f"\n  === Multi-Recording {self._current_index}/{self.num_recordings} ===")
        print(f"  Workflow: {self.workflow_name}")
        print(f"  Output:   {session_dir}\n")

        return self._current_recorder

    def stop_current(self) -> str | None:
        """Stop the current recording and return its session path.

        Returns ``None`` if no recording is in progress.
        """
        if self._current_recorder is None:
            return None

        self._current_recorder.stop()

        # The Recorder creates a Session whose path lives inside our session_dir.
        session_path = self._current_recorder.session.path if self._current_recorder.session else None
        if session_path:
            self._completed_paths.append(session_path)

        self._current_recorder = None

        remaining = self.num_recordings - len(self._completed_paths)
        if remaining > 0:
            print(f"  {remaining} recording(s) remaining.\n")
        else:
            print(f"  All {self.num_recordings} recordings complete!\n")

        return session_path

    def get_all_session_paths(self) -> list[str]:
        """Return a list of completed session paths."""
        return list(self._completed_paths)


# ---------------------------------------------------------------------------
# MultiRecordingDiff — align and diff N recordings to infer variables
# ---------------------------------------------------------------------------

class MultiRecordingDiff:
    """Align steps across multiple recordings of the same workflow and infer
    which values are variables vs constants.
    """

    def __init__(self, session_paths: list[str]):
        if len(session_paths) < 2:
            raise ValueError("At least 2 session paths are required for diffing.")
        self.session_paths = session_paths
        self._sessions_steps: list[list[dict]] = []
        self._aligned: list[list[dict | None]] | None = None

        # Load all sessions
        for path in session_paths:
            self._sessions_steps.append(SessionDiff._load_steps(path))

    # -- alignment --

    def align_sessions(self) -> list[list[dict | None]]:
        """Align steps across all sessions using pairwise LCS.

        Returns a list of "rows", where each row has one entry per session
        (the step dict, or ``None`` if that session has no step at that
        aligned position).
        """
        num_sessions = len(self._sessions_steps)
        if num_sessions == 0:
            self._aligned = []
            return self._aligned

        # Build signatures for each session
        all_sigs = [
            [SessionDiff._signature(s) for s in steps]
            for steps in self._sessions_steps
        ]

        # Incremental alignment: start with session 0, then fold in each
        # subsequent session via pairwise LCS.
        # We maintain a list of "aligned rows", each row is a list[index | None]
        # of length = number of sessions processed so far.

        # Start with session 0 as the base
        aligned_indices: list[list[int | None]] = [
            [i] for i in range(len(all_sigs[0]))
        ]

        for s_idx in range(1, num_sessions):
            # Build the "signature of each aligned row" from session 0's
            # perspective (use the first non-None session in each row)
            base_sigs = []
            for row in aligned_indices:
                sig = None
                for prev_s in range(s_idx):
                    idx = row[prev_s] if prev_s < len(row) else None
                    if idx is not None:
                        sig = all_sigs[prev_s][idx]
                        break
                base_sigs.append(sig)

            new_sigs = all_sigs[s_idx]

            # LCS between base_sigs (filtered to non-None) and new_sigs
            # We need the index mapping, so do it manually.
            base_items = [(i, sig) for i, sig in enumerate(base_sigs) if sig is not None]
            base_vals = [sig for _, sig in base_items]
            base_orig_indices = [i for i, _ in base_items]

            lcs_seq = SessionDiff._lcs(base_vals, new_sigs)

            # Walk through both sequences and build the merged alignment
            new_aligned: list[list[int | None]] = []
            bi, ni, li = 0, 0, 0

            while li < len(lcs_seq):
                target = lcs_seq[li]

                # Advance base to match
                while bi < len(base_items) and base_vals[bi] != target:
                    orig_row_idx = base_orig_indices[bi]
                    row = list(aligned_indices[orig_row_idx])
                    row.append(None)  # new session has no match here
                    new_aligned.append(row)
                    bi += 1

                # Advance new session to match
                while ni < len(new_sigs) and new_sigs[ni] != target:
                    row = [None] * s_idx + [ni]
                    new_aligned.append(row)
                    ni += 1

                # Matched
                if bi < len(base_items) and ni < len(new_sigs):
                    orig_row_idx = base_orig_indices[bi]
                    row = list(aligned_indices[orig_row_idx])
                    row.append(ni)
                    new_aligned.append(row)
                    bi += 1
                    ni += 1

                li += 1

            # Remaining unmatched base rows
            while bi < len(base_items):
                orig_row_idx = base_orig_indices[bi]
                row = list(aligned_indices[orig_row_idx])
                row.append(None)
                new_aligned.append(row)
                bi += 1

            # Also include base rows that were already None (no sig)
            # and were skipped by the base_items filter
            included_base_rows = set(base_orig_indices[:bi])
            # Actually we need to interleave properly. For simplicity,
            # append any base rows not yet included.
            for orig_i, row in enumerate(aligned_indices):
                if orig_i not in {base_orig_indices[x] for x in range(len(base_items))}:
                    extended = list(row) + [None]
                    new_aligned.append(extended)
                elif orig_i not in included_base_rows:
                    extended = list(row) + [None]
                    new_aligned.append(extended)

            # Remaining unmatched new-session steps
            while ni < len(new_sigs):
                row = [None] * s_idx + [ni]
                new_aligned.append(row)
                ni += 1

            aligned_indices = new_aligned

        # Convert index-based alignment to step-dict-based alignment
        self._aligned = []
        for row in aligned_indices:
            step_row: list[dict | None] = []
            for s_idx, idx in enumerate(row):
                if idx is not None and idx < len(self._sessions_steps[s_idx]):
                    step_row.append(self._sessions_steps[s_idx][idx])
                else:
                    step_row.append(None)
            self._aligned.append(step_row)

        return self._aligned

    # -- variable inference --

    def infer_variables(self) -> list[dict]:
        """For each aligned position, classify values as constant, variable,
        or structural divergence.

        Returns a list of dicts, one per aligned row::

            {
                "position": int,
                "classification": "constant" | "variable" | "structural_divergence",
                "action": str,
                "selector_signature": str,
                "values": [str, ...],             # one per session
                "variable_name": str | None,       # if classification == "variable"
                "examples": [str, ...],            # if variable
            }
        """
        if self._aligned is None:
            self.align_sessions()

        results: list[dict] = []
        var_counter = 0
        used_names: set[str] = set()

        for pos, row in enumerate(self._aligned):
            present = [s for s in row if s is not None]
            absent_count = sum(1 for s in row if s is None)

            if not present:
                continue

            # Check structural alignment: are all present steps the same action/selector?
            sigs = [SessionDiff._signature(s) for s in present]
            unique_sigs = set(sigs)

            entry: dict[str, Any] = {
                "position": pos,
                "action": present[0].get("action", ""),
            }

            if absent_count > 0 or len(unique_sigs) > 1:
                # Structural divergence — steps don't align
                entry["classification"] = "structural_divergence"
                entry["selector_signature"] = "; ".join(unique_sigs)
                entry["values"] = [
                    s.get("text", s.get("description", "")) if s else "<missing>"
                    for s in row
                ]
                entry["variable_name"] = None
                results.append(entry)
                continue

            entry["selector_signature"] = sigs[0]

            # Extract typed values (keypress text) for comparison
            values = []
            for s in present:
                text = s.get("text", "")
                if not text:
                    # For clicks, use element name as the "value"
                    elem = s.get("element") or {}
                    text = elem.get("name", "")
                values.append(text)

            entry["values"] = values
            unique_values = set(values)

            if len(unique_values) <= 1:
                # Same value everywhere — constant
                entry["classification"] = "constant"
                entry["variable_name"] = None
            else:
                # Different values — this is a variable
                entry["classification"] = "variable"
                entry["examples"] = list(unique_values)

                # Try to infer a good variable name
                var_name = self._infer_variable_name(present[0], values)
                if var_name in used_names:
                    var_counter += 1
                    var_name = f"{var_name}_{var_counter}"
                used_names.add(var_name)
                entry["variable_name"] = var_name

            results.append(entry)

        return results

    def _infer_variable_name(self, step: dict, values: list[str]) -> str:
        """Infer a variable name from UIA label, format detection, or fallback."""
        # 1. Try UIA field label
        element = step.get("element") or {}
        label = element.get("name", "").strip()
        if label and len(label) < 40:
            return _slugify(label)

        # 2. Try format detection on the first non-empty value
        for v in values:
            if v.strip():
                fmt_name = _detect_format(v)
                if fmt_name:
                    return fmt_name

        # 3. Fallback: generic name
        return "input"

    # -- branch detection --

    def detect_branches(self) -> list[dict]:
        """Detect conditional branches where sessions structurally diverge.

        Returns a list of branch points::

            {
                "position": int,
                "divergent_sessions": [int, ...],  # 0-based session indices
                "steps_per_session": [{...}, ...],
                "suggested_condition": str,
            }
        """
        if self._aligned is None:
            self.align_sessions()

        branches: list[dict] = []

        for pos, row in enumerate(self._aligned):
            present_indices = [i for i, s in enumerate(row) if s is not None]
            absent_indices = [i for i, s in enumerate(row) if s is None]

            if not absent_indices or not present_indices:
                continue

            # This is a divergence point — some sessions have steps, others don't
            steps_info = []
            for i, s in enumerate(row):
                if s is not None:
                    steps_info.append({
                        "session_index": i,
                        "action": s.get("action", ""),
                        "description": s.get("description", ""),
                    })

            # Try to suggest what variable might determine this branch
            # by looking at variable values in preceding aligned positions
            suggested = self._suggest_branch_condition(pos)

            branches.append({
                "position": pos,
                "divergent_sessions": absent_indices,
                "present_sessions": present_indices,
                "steps_per_session": steps_info,
                "suggested_condition": suggested,
            })

        return branches

    def _suggest_branch_condition(self, branch_pos: int) -> str:
        """Look at preceding variable positions to suggest what might drive
        a conditional branch."""
        if self._aligned is None:
            return "unknown"

        # Look backwards for the nearest variable
        for pos in range(branch_pos - 1, -1, -1):
            row = self._aligned[pos]
            present = [s for s in row if s is not None]
            if len(present) < 2:
                continue
            values = []
            for s in present:
                text = s.get("text", "")
                if not text:
                    elem = s.get("element") or {}
                    text = elem.get("name", "")
                values.append(text)
            if len(set(values)) > 1:
                element = present[0].get("element") or {}
                label = element.get("name", f"step_{pos}")
                return f"Possibly depends on '{label}' (values differ at position {pos})"

        return "Review needed: could not determine branch condition automatically"

    # -- enriched IR generation --

    def generate_enriched_ir(self) -> dict:
        """Produce an IR with ``$variable_name`` placeholders and ``inputs``
        populated from inferred variables.

        The output follows the same schema as ``IRCompiler.compile()``.
        """
        if self._aligned is None:
            self.align_sessions()

        variable_info = self.infer_variables()
        branches = self.detect_branches()

        # Build a lookup: position -> variable info
        var_by_pos: dict[int, dict] = {}
        for vi in variable_info:
            if vi["classification"] == "variable":
                var_by_pos[vi["position"]] = vi

        branch_positions = {b["position"] for b in branches}

        # Build IR steps from the first complete session as the template,
        # substituting variables where detected
        ir_steps: list[dict] = []
        inputs: list[dict] = []
        seen_vars: set[str] = set()
        step_id = 0

        for pos, row in enumerate(self._aligned):
            # Use the first non-None step as the template
            template = None
            for s in row:
                if s is not None:
                    template = s
                    break
            if template is None:
                continue

            step_id += 1
            action = template.get("action", "")

            # Build selector
            element = template.get("element") or {}
            selector = {
                "label": element.get("name", ""),
                "control_type": element.get("control_type", ""),
            }
            if element.get("automation_id"):
                selector["automation_id"] = element["automation_id"]
            if template.get("position"):
                selector["fallback_position"] = template["position"]

            # Determine the value / operation
            if pos in branch_positions:
                # Structural divergence — emit an if_condition placeholder
                branch = next(b for b in branches if b["position"] == pos)
                ir_steps.append({
                    "id": step_id,
                    "op": "if_condition",
                    "condition": branch["suggested_condition"],
                    "then": {
                        "action": action,
                        "selector": selector,
                        "description": template.get("description", ""),
                    },
                    "note": "structural_divergence: review and complete manually",
                })
                continue

            if pos in var_by_pos:
                vi = var_by_pos[pos]
                var_name = vi["variable_name"]
                placeholder = f"${var_name}"

                # Register input
                if var_name not in seen_vars:
                    seen_vars.add(var_name)
                    examples = vi.get("examples", vi.get("values", []))
                    inputs.append({
                        "name": var_name,
                        "type": "string",
                        "examples": examples,
                    })

                # Determine op type
                if action == "keypress" or template.get("text"):
                    ir_steps.append({
                        "id": step_id,
                        "op": "fill_field",
                        "selector": selector,
                        "value": placeholder,
                    })
                elif action.endswith("_click"):
                    ir_steps.append({
                        "id": step_id,
                        "op": "click",
                        "selector": selector,
                        "note": f"Value varies: {placeholder}",
                    })
                else:
                    ir_steps.append({
                        "id": step_id,
                        "op": "custom_step",
                        "raw_action": action,
                        "selector": selector,
                        "value": placeholder,
                    })
            else:
                # Constant step — emit as-is
                if action == "keypress":
                    ir_steps.append({
                        "id": step_id,
                        "op": "fill_field",
                        "selector": selector,
                        "value": template.get("text", ""),
                    })
                elif action.endswith("_click"):
                    ir_steps.append({
                        "id": step_id,
                        "op": "click",
                        "selector": selector,
                    })
                elif action == "scroll":
                    ir_steps.append({
                        "id": step_id,
                        "op": "scroll",
                        "direction": template.get("direction", "down"),
                        "amount": template.get("scroll_dy", 0),
                        "selector": selector,
                    })
                elif "drag_start" in template:
                    ds = template["drag_start"]
                    de = template["drag_end"]
                    ir_steps.append({
                        "id": step_id,
                        "op": "drag",
                        "from": {"x": ds["x"], "y": ds["y"]},
                        "to": {"x": de["x"], "y": de["y"]},
                    })
                else:
                    ir_steps.append({
                        "id": step_id,
                        "op": "custom_step",
                        "raw_action": action,
                        "selector": selector,
                        "description": template.get("description", ""),
                    })

        workflow_id = _slugify(self.session_paths[0].split(os.sep)[-2]
                               if len(self.session_paths[0].split(os.sep)) >= 2
                               else "workflow")

        ir: dict[str, Any] = {
            "workflow_id": workflow_id,
            "description": (
                f"Multi-recording enriched IR from {len(self.session_paths)} sessions"
            ),
            "inputs": inputs,
            "outputs": [{"name": "result", "type": "string"}],
            "steps": ir_steps,
            "branches": branches,
            "assertions": [],
            "metadata": {
                "source_sessions": self.session_paths,
                "num_sessions": len(self.session_paths),
                "total_variables": len(inputs),
                "total_branches": len(branches),
            },
        }

        return ir

    def generate_enriched_ir_and_save(self, output_path: str) -> str:
        """Generate the enriched IR and write it to disk."""
        ir = self.generate_enriched_ir()
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(ir, f, indent=2, ensure_ascii=False)
        print(f"  Enriched IR saved: {output_path}")
        print(f"  Steps: {len(ir['steps'])}  |  Variables: {len(ir['inputs'])}  |  Branches: {len(ir['branches'])}")
        return output_path

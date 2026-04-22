"""Audit & Governance - audit trail, retention policy, and approval workflow.

Designed for LGPD compliance at Oliveira & Antunes.  Every significant
action is recorded as a JSONL audit entry so the firm can demonstrate
who did what, when, and with what data.

Audit logs are **never** deleted.
"""

import csv
import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# ======================================================================
# AuditLog
# ======================================================================

class AuditLog:
    """Records who did what, when, with what data.

    Entries are stored as JSONL files, one per day, under
    ``~/.actionshot/audit/``.  Audit logs are never deleted.
    """

    AUDIT_DIR = os.path.join(os.path.expanduser("~"), ".actionshot", "audit")

    def __init__(self, audit_dir: Optional[str] = None):
        self.audit_dir = audit_dir or self.AUDIT_DIR
        os.makedirs(self.audit_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _today_file(self) -> str:
        """Return the path to today's JSONL audit file."""
        filename = datetime.now().strftime("%Y-%m-%d") + ".jsonl"
        return os.path.join(self.audit_dir, filename)

    def _write_entry(self, entry: dict) -> None:
        """Append a single JSON line to today's audit file."""
        entry["timestamp"] = datetime.now().isoformat()
        path = self._today_file()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Public logging methods
    # ------------------------------------------------------------------

    def log_recording(self, user: str, session_path: str, workflow_name: str) -> None:
        """Log that a user started a recording."""
        self._write_entry({
            "event": "recording_started",
            "user": user,
            "session_path": session_path,
            "workflow_name": workflow_name,
        })

    def log_external_send(
        self,
        user: str,
        session_path: str,
        destination: str,
        was_redacted: bool,
    ) -> None:
        """Log that data was sent externally (e.g., to Claude API)."""
        self._write_entry({
            "event": "external_send",
            "user": user,
            "session_path": session_path,
            "destination": destination,
            "was_redacted": was_redacted,
        })

    def log_rpa_execution(
        self,
        user: str,
        workflow_id: str,
        inputs_hash: str,
        success: bool,
    ) -> None:
        """Log an RPA execution (inputs are hashed, not stored)."""
        self._write_entry({
            "event": "rpa_execution",
            "user": user,
            "workflow_id": workflow_id,
            "inputs_hash": inputs_hash,
            "success": success,
        })

    def log_approval(self, approver: str, workflow_id: str, status: str) -> None:
        """Log workflow approval/rejection."""
        self._write_entry({
            "event": "approval_decision",
            "approver": approver,
            "workflow_id": workflow_id,
            "status": status,
        })

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_audit_trail(
        self,
        workflow_id: Optional[str] = None,
        user: Optional[str] = None,
        days: int = 30,
    ) -> list[dict]:
        """Query audit logs with filters.

        Scans JSONL files from the last *days* days and returns matching
        entries.
        """
        cutoff = datetime.now() - timedelta(days=days)
        results: list[dict] = []

        for filename in sorted(os.listdir(self.audit_dir)):
            if not filename.endswith(".jsonl"):
                continue
            # Quick date filter based on filename
            date_str = filename.replace(".jsonl", "")
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue
            if file_date < cutoff.replace(hour=0, minute=0, second=0, microsecond=0):
                continue

            filepath = os.path.join(self.audit_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Apply filters
                    if workflow_id and entry.get("workflow_id") != workflow_id:
                        continue
                    if user and entry.get("user") != user and entry.get("approver") != user:
                        continue

                    results.append(entry)

        return results

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_report(self, path: str, days: int = 90) -> None:
        """Export audit report as CSV for compliance review."""
        entries = self.get_audit_trail(days=days)
        if not entries:
            print(f"No audit entries found for the last {days} days.")
            return

        # Collect all possible field names across entries
        fieldnames: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            for key in entry:
                if key not in seen:
                    fieldnames.append(key)
                    seen.add(key)

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(entries)

        print(f"Exported {len(entries)} entries to {path}")


# ======================================================================
# RetentionPolicy
# ======================================================================

class RetentionPolicy:
    """Automatically delete old recordings per LGPD compliance.

    - Raw recordings (screenshots, metadata): 30 days
    - IR and scripts: 365 days
    - Audit logs: never deleted
    """

    RAW_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp",
        ".mp4", ".avi", ".mkv",
    }
    IR_EXTENSIONS = {".json", ".py"}

    def __init__(
        self,
        raw_retention_days: int = 30,
        ir_retention_days: int = 365,
    ):
        self.raw_retention_days = raw_retention_days
        self.ir_retention_days = ir_retention_days

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _scan(self, recordings_dir: str) -> tuple[list[str], list[str]]:
        """Return (files_to_delete, kept_files) based on retention rules."""
        to_delete: list[str] = []
        kept: list[str] = []
        now = time.time()

        recordings_path = Path(recordings_dir)
        if not recordings_path.exists():
            return to_delete, kept

        for filepath in recordings_path.rglob("*"):
            if not filepath.is_file():
                continue

            age_days = (now - filepath.stat().st_mtime) / 86400
            ext = filepath.suffix.lower()

            if ext in self.RAW_EXTENSIONS and age_days > self.raw_retention_days:
                to_delete.append(str(filepath))
            elif ext in self.IR_EXTENSIONS and age_days > self.ir_retention_days:
                to_delete.append(str(filepath))
            else:
                kept.append(str(filepath))

        return to_delete, kept

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def enforce(self, recordings_dir: str = "recordings") -> int:
        """Scan and delete recordings older than retention period.

        Returns the number of files deleted.
        """
        to_delete, _ = self._scan(recordings_dir)
        count = 0
        for filepath in to_delete:
            try:
                os.remove(filepath)
                count += 1
            except OSError as exc:
                print(f"Warning: could not delete {filepath}: {exc}")
        if count:
            print(f"Retention policy: deleted {count} expired file(s).")
        else:
            print("Retention policy: no files to delete.")
        return count

    def dry_run(self, recordings_dir: str = "recordings") -> list[str]:
        """Show what would be deleted without actually deleting."""
        to_delete, _ = self._scan(recordings_dir)
        if to_delete:
            print(f"Dry run: {len(to_delete)} file(s) would be deleted:")
            for fp in to_delete:
                print(f"  - {fp}")
        else:
            print("Dry run: no files would be deleted.")
        return to_delete


# ======================================================================
# ApprovalWorkflow
# ======================================================================

class ApprovalWorkflow:
    """Simple approval gate before RPA goes to production."""

    APPROVALS_FILE = os.path.join(
        os.path.expanduser("~"), ".actionshot", "approvals.json"
    )

    def __init__(self, approvals_file: Optional[str] = None):
        self.approvals_file = approvals_file or self.APPROVALS_FILE
        os.makedirs(os.path.dirname(self.approvals_file), exist_ok=True)
        self._approvals = self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        if os.path.exists(self.approvals_file):
            with open(self.approvals_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save(self) -> None:
        with open(self.approvals_file, "w", encoding="utf-8") as f:
            json.dump(self._approvals, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def request_approval(
        self,
        workflow_id: str,
        requester: str,
        description: str,
    ) -> None:
        """Create an approval request."""
        self._approvals[workflow_id] = {
            "status": "pending",
            "requester": requester,
            "description": description,
            "requested_at": datetime.now().isoformat(),
            "decided_at": None,
            "decided_by": None,
            "reject_reason": None,
        }
        self._save()
        print(f"Approval requested for workflow '{workflow_id}'.")

    def approve(self, workflow_id: str, approver: str) -> None:
        """Approve a workflow for production use."""
        if workflow_id not in self._approvals:
            print(f"Error: workflow '{workflow_id}' not found.")
            return
        self._approvals[workflow_id]["status"] = "approved"
        self._approvals[workflow_id]["decided_at"] = datetime.now().isoformat()
        self._approvals[workflow_id]["decided_by"] = approver
        self._save()

        # Also write to audit log
        audit = AuditLog()
        audit.log_approval(approver, workflow_id, "approved")
        print(f"Workflow '{workflow_id}' approved by {approver}.")

    def reject(self, workflow_id: str, approver: str, reason: str) -> None:
        """Reject a workflow."""
        if workflow_id not in self._approvals:
            print(f"Error: workflow '{workflow_id}' not found.")
            return
        self._approvals[workflow_id]["status"] = "rejected"
        self._approvals[workflow_id]["decided_at"] = datetime.now().isoformat()
        self._approvals[workflow_id]["decided_by"] = approver
        self._approvals[workflow_id]["reject_reason"] = reason
        self._save()

        audit = AuditLog()
        audit.log_approval(approver, workflow_id, "rejected")
        print(f"Workflow '{workflow_id}' rejected by {approver}. Reason: {reason}")

    def is_approved(self, workflow_id: str) -> bool:
        """Check if workflow is approved."""
        entry = self._approvals.get(workflow_id)
        return entry is not None and entry.get("status") == "approved"

    def list_pending(self) -> list[dict]:
        """List workflows awaiting approval."""
        pending: list[dict] = []
        for wf_id, info in self._approvals.items():
            if info.get("status") == "pending":
                pending.append({"workflow_id": wf_id, **info})
        return pending


# ======================================================================
# Utility: hash inputs for audit logging
# ======================================================================

def hash_inputs(inputs: dict) -> str:
    """Return a SHA-256 hex digest of the inputs dict.

    Used by ``AuditLog.log_rpa_execution`` so that the actual input
    values are never stored -- only a hash for traceability.
    """
    raw = json.dumps(inputs, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

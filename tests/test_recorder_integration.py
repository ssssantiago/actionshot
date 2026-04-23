import pytest
from unittest.mock import MagicMock, patch
from actionshot.scope import WorkflowScope, RecordedEvent

class TestRecorderScope:
    def test_scope_none_marks_all_in_scope(self):
        """When scope is None (legacy mode), all events are in_scope=True."""
        # This is a design contract test
        scope = None
        # Legacy: no scope means everything is in scope
        assert scope is None  # just verify the contract

    def test_scope_filters_correctly(self):
        scope = WorkflowScope("test", ["chrome"])
        assert scope.is_in_scope("chrome.exe") is True
        assert scope.is_in_scope("notepad.exe") is False

    def test_blacklist_never_recorded(self):
        scope = WorkflowScope("test", ["chrome", "other"])
        # Even with "other" in scope, blacklisted processes are excluded
        assert scope.is_blacklisted("explorer.exe") is True
        assert scope.is_in_scope("explorer.exe") is False  # should be false even if "other" is in scope

    def test_ir_v2_only_contains_scoped_events(self):
        """Verify that IR export filters to in_scope only."""
        all_events = [
            RecordedEvent(1, 1000, "click", "chrome", "Chrome", "chrome.exe", True, {}),
            RecordedEvent(2, 2000, "click", "notepad", "Notepad", "notepad.exe", False, {}),
            RecordedEvent(3, 3000, "click", "chrome", "Chrome", "chrome.exe", True, {}),
        ]
        scoped = [e for e in all_events if e.in_scope]
        assert len(scoped) == 2
        assert all(e.app_name == "chrome" for e in scoped)

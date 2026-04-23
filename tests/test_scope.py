import pytest
from actionshot.scope import WorkflowScope, RecordedEvent, PROCESS_BLACKLIST

class TestWorkflowScope:
    def test_chrome_in_scope(self):
        scope = WorkflowScope("test", ["chrome"])
        assert scope.is_in_scope("chrome.exe") is True
        assert scope.is_in_scope("msedge.exe") is True  # edge counts as chrome

    def test_excel_in_scope(self):
        scope = WorkflowScope("test", ["excel"])
        assert scope.is_in_scope("EXCEL.EXE") is True
        assert scope.is_in_scope("excel.exe") is True

    def test_out_of_scope(self):
        scope = WorkflowScope("test", ["chrome"])
        assert scope.is_in_scope("notepad.exe") is False
        assert scope.is_in_scope("EXCEL.EXE") is False

    def test_blacklist(self):
        scope = WorkflowScope("test", ["chrome"])
        assert scope.is_blacklisted("explorer.exe") is True
        assert scope.is_blacklisted("ShellExperienceHost.exe") is True
        assert scope.is_blacklisted("SearchUI.exe") is True
        assert scope.is_blacklisted("chrome.exe") is False
        assert scope.is_blacklisted("notepad.exe") is False

    def test_normalize_app_name(self):
        scope = WorkflowScope("test", ["chrome"])
        assert scope.normalize_app_name("chrome.exe") == "chrome"
        assert scope.normalize_app_name("msedge.exe") == "chrome"
        assert scope.normalize_app_name("EXCEL.EXE") == "excel"
        assert scope.normalize_app_name("notepad.exe") == "other"

    def test_empty_scope_accepts_nothing(self):
        scope = WorkflowScope("test", [])
        assert scope.is_in_scope("chrome.exe") is False

    def test_other_scope_accepts_everything_non_blacklisted(self):
        scope = WorkflowScope("test", ["other"])
        assert scope.is_in_scope("notepad.exe") is True
        assert scope.is_in_scope("myapp.exe") is True

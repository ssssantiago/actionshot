from __future__ import annotations

from dataclasses import dataclass, field


# Blacklisted processes — NEVER recorded, even as in_scope=false
PROCESS_BLACKLIST = frozenset({
    "explorer.exe",
    "ShellExperienceHost.exe",
    "SearchUI.exe",
    "SearchApp.exe",
    "StartMenuExperienceHost.exe",
    "TextInputHost.exe",
    "LockApp.exe",
    "WindowsTerminal.exe",
})

# Known app process names
APP_PROCESS_MAP: dict[str, set[str]] = {
    "chrome": {"chrome.exe", "msedge.exe", "brave.exe"},
    "excel": {"EXCEL.EXE", "excel.exe"},
    "word": {"WINWORD.EXE", "winword.exe"},
    "outlook": {"OUTLOOK.EXE", "outlook.exe"},
}


@dataclass
class RecordedEvent:
    id: int
    timestamp_ms: float
    event_type: str       # "click", "fill", "keypress", "scroll", "drag"
    app_name: str         # normalized: "chrome", "excel", "word", "outlook", "other"
    window_title: str
    process_name: str     # raw: "chrome.exe", "excel.exe", etc
    in_scope: bool        # app_name in declared_scope
    selector: dict        # full hierarchy
    value: str | None = None
    metadata: dict = field(default_factory=dict)
    has_time_gap: bool = False


@dataclass
class WorkflowScope:
    """Declared scope for a recording session."""
    workflow_name: str
    declared_apps: list[str]        # ["chrome", "excel"]
    chrome_url: str | None = None   # initial URL for Chrome
    file_path: str | None = None    # initial file for Excel/Word

    def is_in_scope(self, process_name: str) -> bool:
        """Check if a process is in the declared scope.

        Blacklisted processes are NEVER in scope, even if "other" is declared.
        """
        if self.is_blacklisted(process_name):
            return False
        normalized = self.normalize_app_name(process_name)
        return normalized in self.declared_apps

    def is_blacklisted(self, process_name: str) -> bool:
        """Check if a process is blacklisted."""
        return process_name in PROCESS_BLACKLIST

    def normalize_app_name(self, process_name: str) -> str:
        """Map process name to normalized app name.

        Returns ``"chrome"``, ``"excel"``, ``"word"``, ``"outlook"``,
        or ``"other"`` when the process is not recognized.
        """
        for app_name, process_names in APP_PROCESS_MAP.items():
            if process_name in process_names:
                return app_name
        return "other"

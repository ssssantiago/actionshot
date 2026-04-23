from __future__ import annotations

from dataclasses import dataclass

from actionshot.scope import RecordedEvent


@dataclass
class AppDependencyEdge:
    from_app: str
    to_app: str
    edge_type: str           # "clipboard", "drag", "inferred_typing"
    source_event_id: int
    target_event_id: int
    evidence: str            # human-readable


class DependencyDetector:
    """Detect cross-app data dependencies from a sequence of recorded events."""

    def __init__(self, events: list[RecordedEvent]):
        self.events = events

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_all(self) -> list[AppDependencyEdge]:
        """Run all detection rules and return edges."""
        edges: list[AppDependencyEdge] = []
        edges.extend(self._detect_clipboard())
        edges.extend(self._detect_drag())
        edges.extend(self._detect_inferred_typing())
        return edges

    # ------------------------------------------------------------------
    # Clipboard: Ctrl+C in app A -> Ctrl+V in app B
    # ------------------------------------------------------------------

    def _detect_clipboard(self) -> list[AppDependencyEdge]:
        """Ctrl+C in app A followed by Ctrl+V in app B (no other Ctrl+C between)."""
        edges: list[AppDependencyEdge] = []

        last_copy_event: RecordedEvent | None = None

        for event in self.events:
            if event.event_type != "keypress":
                continue

            if self._is_ctrl_c(event):
                last_copy_event = event
            elif self._is_ctrl_v(event) and last_copy_event is not None:
                if event.app_name != last_copy_event.app_name:
                    edges.append(AppDependencyEdge(
                        from_app=last_copy_event.app_name,
                        to_app=event.app_name,
                        edge_type="clipboard",
                        source_event_id=last_copy_event.id,
                        target_event_id=event.id,
                        evidence=(
                            f"Ctrl+C in {last_copy_event.app_name} "
                            f"(event {last_copy_event.id}) -> "
                            f"Ctrl+V in {event.app_name} "
                            f"(event {event.id})"
                        ),
                    ))

        return edges

    # ------------------------------------------------------------------
    # Drag: drag started in app A, ended in app B
    # ------------------------------------------------------------------

    def _detect_drag(self) -> list[AppDependencyEdge]:
        """Drag events where start and end apps differ."""
        edges: list[AppDependencyEdge] = []

        for event in self.events:
            if event.event_type != "drag":
                continue

            drag_start_app = event.metadata.get("drag_start_app")
            drag_end_app = event.metadata.get("drag_end_app")

            if drag_start_app and drag_end_app and drag_start_app != drag_end_app:
                edges.append(AppDependencyEdge(
                    from_app=drag_start_app,
                    to_app=drag_end_app,
                    edge_type="drag",
                    source_event_id=event.id,
                    target_event_id=event.id,
                    evidence=(
                        f"Drag from {drag_start_app} to {drag_end_app} "
                        f"(event {event.id})"
                    ),
                ))

        return edges

    # ------------------------------------------------------------------
    # Inferred typing: text read in app A appears typed in app B
    # ------------------------------------------------------------------

    def _detect_inferred_typing(self) -> list[AppDependencyEdge]:
        """Text read in app A appears typed in app B (substring >= 5 chars)."""
        edges: list[AppDependencyEdge] = []

        read_events: list[RecordedEvent] = []
        for event in self.events:
            if self._is_read_event(event):
                read_events.append(event)
                continue

            # For each keypress with a typed value, check prior reads
            typed_text = event.value or event.metadata.get("text", "")
            if event.event_type == "keypress" and typed_text:
                for read_ev in read_events:
                    if read_ev.app_name == event.app_name:
                        continue
                    if not read_ev.value:
                        continue
                    match = self._find_common_substring(read_ev.value, typed_text, min_len=5)
                    if match:
                        edges.append(AppDependencyEdge(
                            from_app=read_ev.app_name,
                            to_app=event.app_name,
                            edge_type="inferred_typing",
                            source_event_id=read_ev.id,
                            target_event_id=event.id,
                            evidence=(
                                f"Substring '{match}' lida em {read_ev.app_name} "
                                f"e digitada em {event.app_name}"
                            ),
                        ))
                        # One edge per (read_event, type_event) pair is enough
                        break

        return edges

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_ctrl_c(event: RecordedEvent) -> bool:
        """Return True if the event represents a Ctrl+C keypress."""
        value = (event.value or "").lower()
        if "ctrl+c" in value:
            return True
        metadata_keys = event.metadata.get("keys", [])
        has_ctrl = any("ctrl" in str(k).lower() for k in metadata_keys)
        has_c = any(str(k).lower() == "c" for k in metadata_keys)
        return has_ctrl and has_c

    @staticmethod
    def _is_ctrl_v(event: RecordedEvent) -> bool:
        """Return True if the event represents a Ctrl+V keypress."""
        value = (event.value or "").lower()
        if "ctrl+v" in value:
            return True
        metadata_keys = event.metadata.get("keys", [])
        has_ctrl = any("ctrl" in str(k).lower() for k in metadata_keys)
        has_v = any(str(k).lower() == "v" for k in metadata_keys)
        return has_ctrl and has_v

    @staticmethod
    def _is_read_event(event: RecordedEvent) -> bool:
        """Return True if the event represents a read/extract action."""
        et = event.event_type.lower()
        action = event.metadata.get("action", "").lower()
        combined = et + " " + action
        return "extract" in combined or "read" in combined

    @staticmethod
    def _find_common_substring(source: str, target: str, min_len: int = 5) -> str | None:
        """Return the longest common substring of at least *min_len* chars, or None."""
        if len(source) < min_len or len(target) < min_len:
            return None
        best = None
        for length in range(min_len, min(len(source), len(target)) + 1):
            for i in range(len(source) - length + 1):
                sub = source[i:i + length]
                if sub in target:
                    best = sub
        return best

    @staticmethod
    def _has_common_substring(source: str, target: str, min_len: int = 5) -> bool:
        return DependencyDetector._find_common_substring(source, target, min_len) is not None

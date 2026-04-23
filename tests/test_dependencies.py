import pytest
from actionshot.scope import RecordedEvent
from actionshot.dependencies import DependencyDetector

def _make_event(id, event_type, app, process, value=None, keys=None, text=None, **kw):
    return RecordedEvent(
        id=id, timestamp_ms=id * 1000.0, event_type=event_type,
        app_name=app, window_title=f"{app} window", process_name=process,
        in_scope=True, selector={}, value=value,
        metadata={"keys": keys or [], "text": text or "", **kw},
    )

class TestClipboardDetection:
    def test_ctrl_c_then_ctrl_v_different_apps(self):
        events = [
            _make_event(1, "keypress", "excel", "excel.exe", keys=["[ctrl_l]", "c"]),
            _make_event(2, "keypress", "chrome", "chrome.exe", keys=["[ctrl_l]", "v"]),
        ]
        edges = DependencyDetector(events).detect_all()
        assert len(edges) == 1
        assert edges[0].from_app == "excel"
        assert edges[0].to_app == "chrome"
        assert edges[0].edge_type == "clipboard"

    def test_ctrl_c_then_ctrl_v_same_app_no_edge(self):
        events = [
            _make_event(1, "keypress", "chrome", "chrome.exe", keys=["[ctrl_l]", "c"]),
            _make_event(2, "keypress", "chrome", "chrome.exe", keys=["[ctrl_l]", "v"]),
        ]
        edges = DependencyDetector(events).detect_all()
        assert len(edges) == 0

    def test_second_ctrl_c_resets_source(self):
        events = [
            _make_event(1, "keypress", "excel", "excel.exe", keys=["[ctrl_l]", "c"]),
            _make_event(2, "keypress", "word", "winword.exe", keys=["[ctrl_l]", "c"]),
            _make_event(3, "keypress", "chrome", "chrome.exe", keys=["[ctrl_l]", "v"]),
        ]
        edges = DependencyDetector(events).detect_all()
        assert len(edges) == 1
        assert edges[0].from_app == "word"  # second Ctrl+C overrides first

class TestDragDetection:
    def test_drag_between_apps(self):
        events = [
            _make_event(1, "drag", "excel", "excel.exe",
                       drag_start_app="excel", drag_end_app="chrome"),
        ]
        # DependencyDetector should handle drag events with metadata
        edges = DependencyDetector(events).detect_all()
        drag_edges = [e for e in edges if e.edge_type == "drag"]
        assert len(drag_edges) == 1

class TestInferredTyping:
    def test_match_with_5_char_substring(self):
        events = [
            _make_event(1, "extract_text", "excel", "excel.exe", value="Joao da Silva Santos"),
            _make_event(2, "keypress", "chrome", "chrome.exe", text="Joao da Silva"),
        ]
        edges = DependencyDetector(events).detect_all()
        typing_edges = [e for e in edges if e.edge_type == "inferred_typing"]
        assert len(typing_edges) == 1
        assert "Joao da" in typing_edges[0].evidence or "Silva" in typing_edges[0].evidence

    def test_no_match_with_4_char_substring(self):
        events = [
            _make_event(1, "extract_text", "excel", "excel.exe", value="ABCD"),
            _make_event(2, "keypress", "chrome", "chrome.exe", text="ABCD"),
        ]
        edges = DependencyDetector(events).detect_all()
        typing_edges = [e for e in edges if e.edge_type == "inferred_typing"]
        assert len(typing_edges) == 0  # 4 chars, threshold is 5

    def test_no_edge_within_same_app(self):
        events = [
            _make_event(1, "extract_text", "chrome", "chrome.exe", value="Hello World Testing"),
            _make_event(2, "keypress", "chrome", "chrome.exe", text="Hello World"),
        ]
        edges = DependencyDetector(events).detect_all()
        typing_edges = [e for e in edges if e.edge_type == "inferred_typing"]
        assert len(typing_edges) == 0

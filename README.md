# ActionShot

Record desktop interactions — clicks, keystrokes, scrolls, drags — with annotated screenshots and rich metadata. Feed the recordings to an AI and let it automate the workflow.

## How it works

```
[Record] → [Screenshots + Metadata] → [AI Reads Folder] → [Automated Script]
```

1. **Start recording** — ActionShot watches every mouse click, scroll, drag, and keystroke
2. **Each interaction saves:**
   - Annotated screenshot (red circle on click, arrows on scroll/drag, coordinates labeled)
   - JSON metadata (window title, process, UI element name/type via accessibility tree, coordinates)
3. **Stop recording** — organized session folder ready for AI consumption
4. **Feed to AI** — generate a markdown prompt or API payload, and get a full automation script

## Install

```bash
pip install -r requirements.txt
```

**Requirements:** Python 3.10+, Windows

## Usage

### GUI

```bash
python main.py
```

Opens the graphical interface with buttons for record, replay, generate script, and AI export.

### CLI

**Record a session:**

```bash
python main.py record -o recordings
# Press ESC to stop
```

**Replay a session:**

```bash
python main.py replay recordings/session_20260417_143022
python main.py replay recordings/session_20260417_143022 --speed 2.0
python main.py replay recordings/session_20260417_143022 --dry-run
```

**Generate a standalone Python script:**

```bash
python main.py generate recordings/session_20260417_143022
python main.py generate recordings/session_20260417_143022 -o my_automation.py
```

**Generate AI prompt (markdown):**

```bash
python main.py ai recordings/session_20260417_143022
```

**Export for AI API (JSON payload with optional screenshots):**

```bash
python main.py ai recordings/session_20260417_143022 --export-api
python main.py ai recordings/session_20260417_143022 --export-api --screenshots
```

## Session output

```
recordings/session_20260417_143022/
├── 001_left_click.png          # Screenshot with red circle + coordinates
├── 001_metadata.json           # Element: "Submit" (Button), Window: "Chrome", pos: (540, 320)
├── 002_keypress.png            # Screenshot with typed text overlay
├── 002_metadata.json           # Keys: ["h","e","l","l","o"], text: "hello"
├── 003_scroll.png              # Screenshot with scroll arrow + coordinates
├── 003_metadata.json           # Scroll dy=-3, direction: "down", pos: (800, 400)
├── 004_drag_left.png           # Screenshot with drag path: start(green) → end(red)
├── 004_metadata.json           # drag_start: (100,200), drag_end: (400,500)
├── session_summary.json        # Full session overview with all steps
├── ai_prompt.md                # (generated) Markdown prompt for AI
└── replay_script.py            # (generated) Standalone automation script
```

## Metadata per step

Each `*_metadata.json` includes:

```json
{
  "step": 1,
  "timestamp": "2026-04-17T14:30:22.123456",
  "action": "left_click",
  "position": { "x": 540, "y": 320 },
  "description": "Clicked Button 'Submit' in 'My App - Chrome'",
  "window": {
    "title": "My App - Chrome",
    "class": "Chrome_WidgetWin_1",
    "process": "chrome.exe"
  },
  "element": {
    "name": "Submit",
    "control_type": "Button",
    "automation_id": "submitBtn",
    "class_name": "ButtonClass"
  },
  "screenshot": "001_left_click.png"
}
```

## What gets captured

| Interaction | Screenshot annotation | Metadata |
|---|---|---|
| Mouse click (left/right/middle) | Red circle + crosshair + `(x, y)` label | Position, window, process, UI element (name, type, automation ID) |
| Keyboard input | Yellow text overlay with typed content | Individual keys + combined text |
| Scroll | Blue arrow (up/down) + `(x, y)` label | Position, dx/dy delta, direction |
| Drag & drop | Green start dot → orange line → red end dot + coords | Start/end positions, window |

## Architecture

```
actionshot/
├── recorder.py    # Event listener (pynput) — orchestrates all capture
├── capture.py     # Screenshot + Pillow annotations (circle, arrow, drag path)
├── metadata.py    # Windows accessibility tree (UI element names, types, IDs)
├── session.py     # Session folder management + summary generation
├── replay.py      # Replay engine (pyautogui) — reproduces recorded sessions
├── generator.py   # Script generator — converts sessions to standalone .py files
├── ai_agent.py    # AI integration — generates prompts and API payloads
└── gui.py         # Tkinter GUI
```

## License

MIT

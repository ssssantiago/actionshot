# ActionShot

Record desktop interactions — clicks, keystrokes, scrolls, drags — with annotated screenshots, OCR text extraction, and rich metadata. Feed the recordings to an AI and let it automate the workflow.

## How it works

```
[Record] → [Screenshots + Metadata + OCR + Video] → [AI Reads] → [Automated Script]
```

1. **Start recording** — watches every mouse click, scroll, drag, and keystroke
2. **Each interaction saves:**
   - Annotated screenshot with coordinates (red circle, arrows, drag paths)
   - JSON metadata (window title, process, UI element via accessibility tree, monitor info)
   - OCR text around the interaction point
   - Optional MP4 video of the full session
3. **Feed to AI** — send directly to Claude API, generate prompts, or export to n8n/Zapier

## Install

```bash
pip install -r requirements.txt
```

**Optional:** Install [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) for text extraction.

**Requirements:** Python 3.10+, Windows

### Install as package

```bash
pip install -e .               # core only
pip install -e ".[all]"        # all features (video, OCR, AI, tray)
pip install -e ".[video,ocr]"  # specific extras
```

### Build standalone executable

```bash
pip install pyinstaller
pyinstaller actionshot.spec
```

## Usage

### GUI

```bash
python main.py
```

### System Tray

```bash
python main.py tray
```

Runs minimized — right-click the tray icon to start/stop recording.

### CLI

```bash
# Record (ESC to stop, Win+Shift+R to toggle, Win+Shift+P to pause)
python main.py record
python main.py record --video              # also record MP4
python main.py record --video --fps 30     # higher quality video
python main.py record --no-ocr             # disable OCR

# Replay
python main.py replay <session>
python main.py replay <session> --speed 2.0
python main.py replay <session> --dry-run

# Generate standalone script
python main.py generate <session>
python main.py generate <session> -o my_script.py

# AI prompt (markdown)
python main.py ai <session>

# Send directly to Claude API
python main.py claude <session>                      # generate automation script
python main.py claude <session> --analyze            # get workflow analysis
python main.py claude <session> --no-screenshots     # text-only (cheaper)

# Pattern detection
python main.py analyze <session>

# Compare two sessions
python main.py diff <session_a> <session_b>
python main.py diff <session_a> <session_b> --json

# Export to workflow tools
python main.py export <session> -f n8n
python main.py export <session> -f zapier
python main.py export <session> -f both

# Schedule automations
python main.py schedule add "Daily report" script.py --cron "09:00"
python main.py schedule add "Every 30min" script.py --interval 30
python main.py schedule list
python main.py schedule remove 1
python main.py schedule run    # start daemon
```

## Features

### Recording

| Feature | Description |
|---|---|
| Mouse clicks | Left, right, middle — with coordinates, element name, window |
| Keyboard | Grouped keystrokes with text display |
| Scroll | Up/down with delta and position |
| Drag & drop | Start/end coordinates with visual path |
| Video capture | Optional MP4 recording of the full screen |
| OCR | Extracts visible text around each interaction |
| Multi-monitor | Identifies which monitor was clicked |
| Global hotkeys | Win+Shift+R toggle, Win+Shift+P pause, ESC stop |

### Analysis

| Feature | Description |
|---|---|
| Loop detection | Finds repeated action sequences |
| Step grouping | Groups related actions (click + type = fill field) |
| Frequent targets | Most clicked elements |
| Session diff | Compare two recordings side by side |

### Automation

| Feature | Description |
|---|---|
| Script generator | Standalone .py with pyautogui commands |
| Claude API | Sends session directly to Claude, gets back robust script |
| AI prompt | Markdown document ready for any AI |
| Replay engine | Reproduces sessions with speed control |
| Scheduler | Run scripts on cron or interval |
| n8n export | Workflow JSON importable into n8n |
| Zapier export | Workflow JSON for Zapier integration |

### Deployment

| Feature | Description |
|---|---|
| GUI | Tkinter interface for all features |
| System tray | Minimize to tray, right-click to control |
| PyPI package | `pip install actionshot` (with optional extras) |
| Standalone exe | PyInstaller spec included |

## Session output

```
recordings/session_20260417_143022/
├── 001_left_click.png          # Annotated screenshot with coordinates
├── 001_metadata.json           # Full metadata + OCR + monitor info
├── 002_keypress.png
├── 002_metadata.json
├── 003_scroll.png
├── 003_metadata.json
├── 004_drag_left.png
├── 004_metadata.json
├── recording.mp4               # Full session video (if --video)
├── session_summary.json        # Session overview
├── analysis.json               # Pattern analysis (after analyze)
├── ai_prompt.md                # AI prompt (after ai command)
├── ai_generated_script.py      # Claude-generated script (after claude command)
├── replay_script.py            # Generated replay script
├── workflow_n8n.json           # n8n workflow (after export)
└── workflow_zapier.json        # Zapier workflow (after export)
```

## Architecture

```
actionshot/
├── recorder.py     # Event listener — orchestrates capture with video/OCR/monitors
├── capture.py      # Screenshot annotations (circles, arrows, drag paths, coordinates)
├── metadata.py     # Windows accessibility tree (element names, types, automation IDs)
├── ocr.py          # Tesseract OCR — text extraction from screenshots
├── monitor.py      # Multi-monitor detection and identification
├── video.py        # MP4 screen recording via OpenCV
├── hotkeys.py      # Global hotkeys (Win+Shift+R/P/S)
├── session.py      # Session folder management
├── replay.py       # Replay engine (pyautogui)
├── generator.py    # Python script generator
├── ai_agent.py     # AI prompt and API payload generator
├── claude_api.py   # Direct Claude API integration
├── patterns.py     # Loop detection, step grouping, frequency analysis
├── diff.py         # Session comparison (LCS-based alignment)
├── scheduler.py    # Cron/interval task scheduler
├── export.py       # n8n and Zapier workflow exporters
├── tray.py         # System tray application
└── gui.py          # Tkinter graphical interface
```

## License

MIT

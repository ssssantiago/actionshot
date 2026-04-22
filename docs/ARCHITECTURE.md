# ActionShot Architecture

## Overview

ActionShot is a desktop RPA tool that records user interactions, compiles them into a declarative Intermediate Representation (IR), and generates production-grade Python automation scripts using Claude AI.

## Pipeline

```
Recording  -->  Session  -->  IR Compiler  -->  Prompt Builder  -->  Claude API  -->  Script
  (user)       (raw data)    (semantic IR)     (few-shot + IR)      (code gen)     (.py file)
```

### 1. Recording (`recorder.py`, `capture.py`, `metadata.py`)

The Recorder listens to mouse and keyboard events via pynput. For each interaction it:
- Takes a screenshot (`capture.py`)
- Extracts window/element metadata via UIA (`metadata.py`)
- Optionally runs OCR on the click region (`ocr.py`)
- Writes a numbered `NNN_metadata.json` + screenshot to the session directory

Output: a session directory with `session_summary.json` and per-step metadata/screenshots.

### 2. Session management (`session.py`)

Manages the session directory lifecycle: creation, naming, step numbering, and summary file.

### 3. Pattern detection (`patterns.py`)

Analyzes raw recordings to find:
- Repeated step sequences (loops)
- Related step groups
- Noise/duplicate actions to filter

### 4. IR Compilation (`ir_compiler.py`)

Transforms raw metadata steps into a high-level IR:
- **Semantic grouping**: click + keypress becomes `fill_field`, combobox interactions become `select_option`
- **Variable detection**: data-like values (emails, CPFs, dates) become `$variables`
- **Loop injection**: wraps repeated sequences in `loop` operations
- **Assertion generation**: automatically adds validation checks after submit clicks, field fills, and text extractions

The IR is a JSON structure with: `workflow_id`, `inputs`, `outputs`, `steps`, `assertions`.

### 5. Prompt generation (`prompt_template.py`)

Builds a structured prompt for Claude containing:
- System rules (rpakit-only, selector hierarchy, error handling)
- SDK reference documentation
- Few-shot examples selected by similarity from `examples/`
- Assertion validation instructions
- The target IR to convert

### 6. Code generation (`claude_api.py`, `ai_agent.py`)

Sends the prompt to Claude's Messages API and receives a complete Python script. The `ai_agent.py` module orchestrates multi-turn conversations if needed.

### 7. Script execution (`replay.py`, `rpakit.py`)

- `rpakit.py` is the internal SDK that generated scripts import. It wraps pywinauto for UIA automation, with selector resolution, retries, logging, and screenshot-on-failure.
- `replay.py` handles raw coordinate-based replay for simpler cases.

### 8. Self-healing (`self_healing.py`)

When a workflow fails at runtime:
1. Captures a failure package (screenshot, UIA tree, error details)
2. Matches against known failure patterns
3. Applies automatic fixes or generates an AI fix prompt

### 9. Supporting modules

- `config.py` - Configuration management
- `gui.py` / `tray.py` - System tray UI
- `hotkeys.py` - Global hotkey registration
- `monitor.py` - Multi-monitor coordinate handling
- `video.py` - Optional video recording
- `redact.py` - PII redaction in recordings
- `telemetry.py` - Usage telemetry
- `scheduler.py` - Workflow scheduling
- `export.py` - Export recordings to various formats
- `diff.py` - Diff comparison between sessions
- `smart_wait.py` - Intelligent wait strategies

## Key design decisions

1. **Selector hierarchy** (primary/secondary/tertiary/fallback) ensures scripts survive UI changes.
2. **IR as intermediate layer** decouples recording from code generation -- you can edit the IR manually.
3. **Few-shot examples** are stored as validated pairs in `examples/` and selected by similarity, not hardcoded.
4. **Assertions in the IR** provide runtime validation that the automation is working correctly.

# Handoff Guide

For Daniel and the team. This document explains what each module does and how to maintain the system.

## Module map

| Module | Purpose | Key classes/functions |
|--------|---------|----------------------|
| `main.py` | CLI entry point | `cmd_record`, `cmd_generate`, `cmd_replay` |
| `recorder.py` | Captures mouse/keyboard events | `Recorder` |
| `capture.py` | Screenshots and annotation | `take_screenshot`, `annotate_click` |
| `metadata.py` | UIA window/element inspection | `get_window_info` |
| `ocr.py` | OCR text extraction near clicks | `extract_text_around` |
| `session.py` | Session directory management | `Session` |
| `patterns.py` | Loop/pattern detection in recordings | `PatternDetector` |
| `ir_compiler.py` | Raw steps to IR conversion + assertions | `IRCompiler`, `_generate_assertions` |
| `prompt_template.py` | Builds prompts for Claude with few-shot | `generate_prompt`, `generate_api_payload` |
| `claude_api.py` | Claude Messages API integration | - |
| `ai_agent.py` | Multi-turn AI conversation orchestration | - |
| `generator.py` | Legacy script generation (pre-IR) | `ScriptGenerator` |
| `rpakit.py` | SDK that generated scripts import | `UI`, `wait`, `Selector` |
| `replay.py` | Coordinate-based replay | `Replayer` |
| `self_healing.py` | Failure capture and automatic repair | `FailureCapture`, `SelfHealingLoop` |
| `config.py` | Configuration loading | `load_config` |
| `gui.py` / `tray.py` | System tray interface | - |
| `hotkeys.py` | Global hotkeys | - |
| `monitor.py` | Multi-monitor support | `MonitorInfo` |
| `video.py` | Video recording | `VideoRecorder` |
| `redact.py` | PII redaction | - |
| `telemetry.py` | Usage metrics | - |
| `scheduler.py` | Workflow scheduling | - |
| `export.py` | Session export | - |
| `diff.py` | Session comparison | - |
| `smart_wait.py` | Intelligent wait strategies | - |

## Data flow

```
User records  -->  session directory  -->  IRCompiler  -->  prompt_template  -->  Claude  -->  .py script
                   (metadata + screenshots)  (ir.json)      (prompt text)       (API)       (rpakit-based)
```

## Where things live

- **Recordings**: `recordings/<session_name>/` -- raw metadata + screenshots
- **IR output**: `recordings/<session_name>/workflow_ir.json`
- **Generated scripts**: `recordings/<session_name>/replay_script.py`
- **Few-shot examples**: `examples/NN_name/ir.json` + `script.py`
- **Failure packages**: `failures/<workflow_id>/<timestamp>/`
- **Config**: `actionshot.toml` or passed via CLI

## Common maintenance tasks

### Adding support for a new application

No code changes needed. Record the workflow, compile the IR, and generate the script. If the app uses non-standard controls, you may need to add a new operation (see `docs/ADDING_OPERATIONS.md`).

### Updating few-shot examples

Add or update examples in `examples/`. See `docs/ADDING_FEWSHOT.md`. The prompt builder loads them dynamically -- no code changes needed.

### When generated scripts break

1. Check `docs/DEBUGGING.md` for the debugging workflow.
2. If the IR is wrong, re-record or manually edit the IR JSON.
3. If the IR is right but the script is wrong, update the few-shot examples or the SDK reference in `prompt_template.py`.
4. If the app changed, the self-healing system should detect it. If it does not, add the failure pattern to `self_healing.py`.

### Upgrading Claude model

Update the `model` field in `prompt_template.py` (`generate_api_payload` function) and `claude_api.py`. Test with the benchmark suite in `benchmarks/`.

## Dependencies

- `pywinauto` - UIA automation backend
- `pynput` - Mouse/keyboard event capture
- `Pillow` - Screenshot capture
- `pytesseract` (optional) - OCR
- `anthropic` - Claude API client
- `openpyxl` - Spreadsheet reading in generated scripts

## Running tests

```bash
python -m pytest benchmarks/
```

## Contact

Questions about the system architecture: Guilherme Santiago
Questions about specific workflows: check the recording session and IR for context

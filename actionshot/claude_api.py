"""Claude API integration - sends sessions directly to Claude for automation script generation."""

import json
import os
import base64

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


class ClaudeAutomator:
    """Send recorded sessions to Claude API and get automation scripts back."""

    MODEL = "claude-sonnet-4-6-20250514"

    def __init__(self, session_path: str, api_key: str = None):
        if not HAS_ANTHROPIC:
            raise ImportError(
                "anthropic package not installed. Run: pip install anthropic"
            )

        self.session_path = session_path
        self.client = anthropic.Anthropic(api_key=api_key)  # uses ANTHROPIC_API_KEY env var if None
        self.steps = []
        self._load_session()

    def _load_session(self):
        summary_path = os.path.join(self.session_path, "session_summary.json")
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)

        for step_info in summary["steps"]:
            step_num = step_info["step"]
            meta_path = os.path.join(self.session_path, f"{step_num:03d}_metadata.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.steps.append(json.load(f))

    def generate_script(self, include_screenshots: bool = True, max_screenshots: int = 20) -> str:
        """Send session to Claude and get back a Python automation script."""
        content = self._build_content(include_screenshots, max_screenshots)

        print(f"  Sending {len(self.steps)} steps to Claude API...")

        message = self.client.messages.create(
            model=self.MODEL,
            max_tokens=8192,
            system=(
                "You are an expert at desktop automation with Python. "
                "You receive recordings of user desktop interactions (clicks, keypresses, scrolls, drags) "
                "with metadata about UI elements, window titles, and coordinates. "
                "Generate a clean, robust Python script using pyautogui and pywinauto that reproduces "
                "the workflow. Prefer element names and automation IDs over raw coordinates. "
                "Add waits, error handling, and clear comments. "
                "Return ONLY the Python script, no explanations."
            ),
            messages=[{"role": "user", "content": content}],
        )

        script = message.content[0].text

        # Clean up markdown code blocks if present
        if script.startswith("```python"):
            script = script[len("```python"):].strip()
        if script.startswith("```"):
            script = script[3:].strip()
        if script.endswith("```"):
            script = script[:-3].strip()

        output_path = os.path.join(self.session_path, "ai_generated_script.py")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(script)

        print(f"  AI-generated script saved: {output_path}")
        print(f"  Tokens used: {message.usage.input_tokens} in / {message.usage.output_tokens} out")

        return output_path

    def analyze_workflow(self) -> str:
        """Ask Claude to analyze the workflow and provide insights."""
        content = self._build_content(include_screenshots=False)
        content.append({
            "type": "text",
            "text": (
                "\nAnalyze this workflow and provide:\n"
                "1. What the user is doing (high-level goal)\n"
                "2. Any repetitive patterns or loops\n"
                "3. Potential improvements or shortcuts\n"
                "4. Risks or failure points in automation\n"
                "5. Suggested approach for robust automation"
            ),
        })

        print(f"  Analyzing workflow with Claude API...")

        message = self.client.messages.create(
            model=self.MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": content}],
        )

        analysis = message.content[0].text
        output_path = os.path.join(self.session_path, "ai_analysis.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(analysis)

        print(f"  Analysis saved: {output_path}")
        return analysis

    def _build_content(self, include_screenshots: bool = False, max_screenshots: int = 20) -> list[dict]:
        content = []

        content.append({
            "type": "text",
            "text": f"Desktop interaction recording with {len(self.steps)} steps:\n",
        })

        screenshot_count = 0

        for step in self.steps:
            step_text = f"\n--- Step {step.get('step', '?')} ---\n"
            step_text += f"Action: {step.get('action', '')}\n"
            step_text += f"Description: {step.get('description', '')}\n"

            if "position" in step:
                pos = step["position"]
                step_text += f"Position: ({pos.get('x', '?')}, {pos.get('y', '?')})\n"

            window = step.get("window", {})
            if window.get("title"):
                step_text += f"Window: {window['title']}\n"
                step_text += f"Process: {window.get('process', '?')}\n"

            element = step.get("element", {})
            if element:
                step_text += f"Element: {element.get('name', '?')} ({element.get('control_type', '?')})\n"
                if element.get("automation_id"):
                    step_text += f"Automation ID: {element['automation_id']}\n"

            if "drag_start" in step:
                ds, de = step["drag_start"], step["drag_end"]
                step_text += f"Drag: ({ds['x']},{ds['y']}) -> ({de['x']},{de['y']})\n"

            if step.get("scroll_dy"):
                step_text += f"Scroll: dy={step['scroll_dy']} ({step.get('direction', '?')})\n"

            if step.get("text"):
                step_text += f"Typed: {step['text']}\n"

            if step.get("ocr_text"):
                step_text += f"Visible text (OCR): {step['ocr_text'][:200]}\n"

            if step.get("ocr_nearby"):
                step_text += f"Nearby text (OCR): {step['ocr_nearby'][:200]}\n"

            content.append({"type": "text", "text": step_text})

            # Include screenshot
            if include_screenshots and screenshot_count < max_screenshots:
                img_path = os.path.join(self.session_path, step.get("screenshot", ""))
                if os.path.exists(img_path):
                    with open(img_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    })
                    screenshot_count += 1

        return content

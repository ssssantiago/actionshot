"""AI Agent - interprets recorded sessions and generates intelligent automation."""

import json
import os
import base64


class AIAgent:
    """Prepares session data for AI interpretation and generates automation prompts."""

    def __init__(self, session_path: str):
        self.session_path = session_path
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

    def generate_ai_prompt(self, output_path: str = None) -> str:
        """Generate a detailed prompt that an AI can use to understand and automate the flow."""
        if output_path is None:
            output_path = os.path.join(self.session_path, "ai_prompt.md")

        lines = [
            "# ActionShot - AI Automation Prompt",
            "",
            "## Session Overview",
            "",
            f"This session contains **{len(self.steps)} steps** recorded from a desktop interaction.",
            "Your goal is to understand what the user was doing and generate a robust automation script.",
            "",
            "## Recorded Steps",
            "",
        ]

        for step in self.steps:
            step_num = step.get("step", 0)
            action = step.get("action", "")
            desc = step.get("description", "")
            timestamp = step.get("timestamp", "")

            lines.append(f"### Step {step_num}: {desc}")
            lines.append("")
            lines.append(f"- **Action:** `{action}`")
            lines.append(f"- **Time:** `{timestamp}`")

            # Position info
            if "position" in step:
                pos = step["position"]
                lines.append(f"- **Position:** x={pos.get('x', '?')}, y={pos.get('y', '?')}")

            # Window info
            window = step.get("window", {})
            if window:
                lines.append(f"- **Window:** `{window.get('title', 'unknown')}`")
                lines.append(f"- **Process:** `{window.get('process', 'unknown')}`")

            # Element info
            element = step.get("element", {})
            if element:
                lines.append(f"- **Element Name:** `{element.get('name', 'unknown')}`")
                lines.append(f"- **Element Type:** `{element.get('control_type', 'unknown')}`")
                if element.get("automation_id"):
                    lines.append(f"- **Automation ID:** `{element['automation_id']}`")

            # Keyboard specific
            if action == "keypress":
                lines.append(f"- **Keys:** `{step.get('text', '')}`")

            # Scroll specific
            if action == "scroll":
                lines.append(f"- **Scroll Delta:** dx={step.get('scroll_dx', 0)}, dy={step.get('scroll_dy', 0)}")

            # Drag specific
            if "drag_start" in step:
                ds = step["drag_start"]
                de = step["drag_end"]
                lines.append(f"- **Drag:** ({ds['x']},{ds['y']}) → ({de['x']},{de['y']})")

            # Screenshot reference
            if "screenshot" in step:
                lines.append(f"- **Screenshot:** `{step['screenshot']}`")

            lines.append("")

        # Add instructions for the AI
        lines.extend([
            "## Instructions for AI",
            "",
            "Based on the steps above and the accompanying screenshots:",
            "",
            "1. **Identify the workflow**: What is the user trying to accomplish?",
            "2. **Find patterns**: Are there repetitive actions that could be looped?",
            "3. **Use semantic selectors**: Prefer element names and automation IDs over coordinates.",
            "4. **Handle variations**: Account for window position changes, loading times, etc.",
            "5. **Add error handling**: Check if elements exist before clicking.",
            "6. **Generate a Python script** using `pyautogui` and `pywinauto` that:",
            "   - Reproduces the exact workflow",
            "   - Uses element names when available (more robust than coordinates)",
            "   - Falls back to coordinates only when necessary",
            "   - Includes waits for UI elements to appear",
            "   - Has clear comments explaining each step",
            "",
            "## Coordinate Map (All Clicks)",
            "",
            "| Step | Action | X | Y | Element | Window |",
            "|------|--------|---|---|---------|--------|",
        ])

        for step in self.steps:
            if "position" in step:
                pos = step["position"]
                element = step.get("element", {})
                window = step.get("window", {})
                lines.append(
                    f"| {step.get('step', '?')} "
                    f"| {step.get('action', '?')} "
                    f"| {pos.get('x', '?')} "
                    f"| {pos.get('y', '?')} "
                    f"| {element.get('name', '-')} "
                    f"| {window.get('title', '-')[:40]} |"
                )

        lines.append("")

        content = "\n".join(lines)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"  AI prompt generated: {output_path}")
        return output_path

    def export_for_api(self, include_screenshots: bool = False) -> list[dict]:
        """Export session as structured messages ready for an AI API call."""
        messages = []

        system_msg = (
            "You are an automation expert. Analyze the following desktop interaction recording "
            "and generate a robust Python automation script. Use pyautogui for mouse/keyboard "
            "and pywinauto for element-based interactions. Prefer semantic selectors over coordinates."
        )

        content_parts = []

        for step in self.steps:
            step_text = (
                f"Step {step.get('step', '?')}: {step.get('description', '')}\n"
                f"Action: {step.get('action', '')}\n"
            )

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

            if step.get("keys"):
                step_text += f"Keys: {step.get('text', '')}\n"

            content_parts.append({"type": "text", "text": step_text})

            # Optionally include screenshots as base64
            if include_screenshots and "screenshot" in step:
                img_path = os.path.join(self.session_path, step["screenshot"])
                if os.path.exists(img_path):
                    with open(img_path, "rb") as img_f:
                        b64 = base64.b64encode(img_f.read()).decode()
                    content_parts.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    })

        messages.append({"role": "system", "content": system_msg})
        messages.append({"role": "user", "content": content_parts})

        export_path = os.path.join(self.session_path, "ai_api_payload.json")
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(messages, f, indent=2, ensure_ascii=False)

        print(f"  API payload exported: {export_path}")
        return messages

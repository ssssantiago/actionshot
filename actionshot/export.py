"""Export sessions to n8n and Zapier workflow formats."""

import json
import os
from datetime import datetime


class WorkflowExporter:
    """Convert ActionShot sessions into n8n or Zapier workflow definitions."""

    def __init__(self, session_path: str):
        self.session_path = session_path
        self.steps = []
        self._load()

    def _load(self):
        summary_path = os.path.join(self.session_path, "session_summary.json")
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)

        for step_info in summary["steps"]:
            step_num = step_info["step"]
            meta_path = os.path.join(self.session_path, f"{step_num:03d}_metadata.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.steps.append(json.load(f))

    def export_n8n(self, output_path: str = None) -> str:
        """Export as n8n workflow JSON."""
        if output_path is None:
            output_path = os.path.join(self.session_path, "workflow_n8n.json")

        nodes = []
        connections = {}

        # Start trigger
        nodes.append({
            "id": "trigger",
            "name": "Manual Trigger",
            "type": "n8n-nodes-base.manualTrigger",
            "position": [250, 300],
            "parameters": {},
        })

        prev_node_id = "trigger"
        x_pos = 500

        for i, step in enumerate(self.steps):
            node_id = f"step_{i + 1}"
            action = step.get("action", "")
            desc = step.get("description", "")

            if action.endswith("_click"):
                pos = step.get("position", {})
                element = step.get("element", {})
                node = {
                    "id": node_id,
                    "name": f"Step {i + 1}: {desc[:40]}",
                    "type": "n8n-nodes-base.executeCommand",
                    "position": [x_pos, 300],
                    "parameters": {
                        "command": self._gen_pyautogui_command(step),
                    },
                    "notes": json.dumps({
                        "action": action,
                        "element": element,
                        "position": pos,
                        "window": step.get("window", {}),
                    }),
                }
            elif action == "keypress":
                text = step.get("text", "")
                node = {
                    "id": node_id,
                    "name": f"Step {i + 1}: Type '{text[:20]}'",
                    "type": "n8n-nodes-base.executeCommand",
                    "position": [x_pos, 300],
                    "parameters": {
                        "command": f'python -c "import pyautogui; pyautogui.typewrite(\'{text}\', interval=0.03)"',
                    },
                }
            elif action == "scroll":
                dy = step.get("scroll_dy", 0)
                pos = step.get("position", {})
                node = {
                    "id": node_id,
                    "name": f"Step {i + 1}: Scroll {step.get('direction', '')}",
                    "type": "n8n-nodes-base.executeCommand",
                    "position": [x_pos, 300],
                    "parameters": {
                        "command": f'python -c "import pyautogui; pyautogui.scroll({dy}, x={pos.get("x", 0)}, y={pos.get("y", 0)})"',
                    },
                }
            else:
                node = {
                    "id": node_id,
                    "name": f"Step {i + 1}: {desc[:40]}",
                    "type": "n8n-nodes-base.noOp",
                    "position": [x_pos, 300],
                    "parameters": {},
                }

            nodes.append(node)
            connections[prev_node_id] = {"main": [[{"node": node_id, "type": "main", "index": 0}]]}
            prev_node_id = node_id
            x_pos += 250

        workflow = {
            "name": f"ActionShot - {os.path.basename(self.session_path)}",
            "nodes": nodes,
            "connections": connections,
            "settings": {},
            "meta": {
                "generator": "ActionShot",
                "session": self.session_path,
                "exported": datetime.now().isoformat(),
            },
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(workflow, f, indent=2, ensure_ascii=False)

        print(f"  n8n workflow exported: {output_path}")
        return output_path

    def export_zapier(self, output_path: str = None) -> str:
        """Export as Zapier-compatible workflow definition."""
        if output_path is None:
            output_path = os.path.join(self.session_path, "workflow_zapier.json")

        zap = {
            "name": f"ActionShot - {os.path.basename(self.session_path)}",
            "trigger": {
                "type": "schedule",
                "config": {"interval": "manual"},
            },
            "actions": [],
            "meta": {
                "generator": "ActionShot",
                "session": self.session_path,
                "exported": datetime.now().isoformat(),
            },
        }

        for i, step in enumerate(self.steps):
            action = step.get("action", "")
            desc = step.get("description", "")

            zap_action = {
                "step": i + 1,
                "type": "code",
                "name": desc[:60],
                "language": "python",
                "code": self._gen_pyautogui_command(step),
                "metadata": {
                    "action": action,
                    "position": step.get("position"),
                    "window": step.get("window", {}),
                    "element": step.get("element", {}),
                },
            }
            zap["actions"].append(zap_action)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(zap, f, indent=2, ensure_ascii=False)

        print(f"  Zapier workflow exported: {output_path}")
        return output_path

    def _gen_pyautogui_command(self, step: dict) -> str:
        action = step.get("action", "")
        pos = step.get("position", {})
        x, y = pos.get("x", 0), pos.get("y", 0)

        if action.endswith("_click"):
            button = "left"
            if "right" in action:
                button = "right"
            elif "middle" in action:
                button = "middle"
            return f'python -c "import pyautogui; pyautogui.click({x}, {y}, button=\'{button}\')"'

        elif action == "keypress":
            text = step.get("text", "").replace("'", "\\'")
            return f'python -c "import pyautogui; pyautogui.typewrite(\'{text}\', interval=0.03)"'

        elif action == "scroll":
            dy = step.get("scroll_dy", 0)
            return f'python -c "import pyautogui; pyautogui.scroll({dy}, x={x}, y={y})"'

        elif action.startswith("drag"):
            ds = step.get("drag_start", {})
            de = step.get("drag_end", {})
            return (
                f'python -c "import pyautogui; '
                f"pyautogui.moveTo({ds.get('x', 0)}, {ds.get('y', 0)}); "
                f"pyautogui.drag({de.get('x', 0) - ds.get('x', 0)}, {de.get('y', 0) - ds.get('y', 0)}, duration=0.5)\""
            )

        return f'python -c "pass  # {step.get("description", "")}"'

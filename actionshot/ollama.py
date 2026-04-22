"""Ollama Client - local-only AI mode for sensitive workflows.

Uses a locally-running Ollama instance to generate RPA scripts so that
no data ever leaves the machine.  This is critical for law-firm workflows
that handle client-privileged information.

Only stdlib ``urllib`` is used -- no extra dependencies.
"""

import json
import urllib.request
import urllib.error
from typing import Optional

from actionshot.prompt_template import generate_prompt


class OllamaClient:
    """Generate RPA scripts using local Ollama models instead of Claude API."""

    def __init__(
        self,
        model: str = "codellama:13b",
        host: str = "http://localhost:11434",
    ):
        self.model = model
        self.host = host.rstrip("/")

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Check if Ollama is running locally."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post(self, endpoint: str, payload: dict, stream: bool = True) -> str:
        """Send a POST request to Ollama and return the full response text.

        When *stream* is True the response is read incrementally (one JSON
        object per line) and the ``response`` fragments are concatenated.
        This avoids buffering very large completions in memory on the
        server side.
        """
        url = f"{self.host}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                if not stream:
                    body = json.loads(resp.read().decode("utf-8"))
                    return body.get("response", "")

                # Streaming: each line is a JSON object with a "response" key
                chunks: list[str] = []
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        chunks.append(obj.get("response", ""))
                        if obj.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
                return "".join(chunks)

        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"Ollama returned HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(
                f"Cannot reach Ollama at {self.host}. Is it running? ({exc.reason})"
            ) from exc
        except OSError as exc:
            raise ConnectionError(
                f"Connection error talking to Ollama: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_script(self, ir: dict, prompt: Optional[str] = None) -> str:
        """Send IR + prompt to local model, get script back.

        Uses the same prompt template from ``prompt_template.py`` so the
        output quality is comparable to Claude API output.
        """
        if prompt is None:
            prompt = generate_prompt(ir)

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.2,
                "num_predict": 4096,
            },
        }
        return self._post("/api/generate", payload)

    def analyze_workflow(self, ir: dict) -> str:
        """Get workflow analysis from local model."""
        ir_json = json.dumps(ir, indent=2, ensure_ascii=False)
        prompt = (
            "You are an expert RPA analyst.  Analyze the following workflow IR "
            "and provide:\n"
            "1. A plain-language summary of what the workflow does.\n"
            "2. Potential failure points or fragile selectors.\n"
            "3. Suggestions for improvement (variables, waits, error handling).\n\n"
            f"```json\n{ir_json}\n```\n"
        )
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.3,
                "num_predict": 2048,
            },
        }
        return self._post("/api/generate", payload)

    def suggest_fix(self, failure_package: dict, ir: dict) -> str:
        """Ask local model for a fix suggestion.

        Parameters
        ----------
        failure_package : dict
            Contains at minimum ``error``, ``step_id``, and optionally
            ``screenshot_b64`` and ``selector``.
        ir : dict
            The full workflow IR for context.
        """
        ir_json = json.dumps(ir, indent=2, ensure_ascii=False)
        failure_json = json.dumps(failure_package, indent=2, ensure_ascii=False)
        prompt = (
            "You are an expert RPA debugger.  A workflow step failed during "
            "execution.  Given the failure details and the full workflow IR, "
            "suggest a concrete fix.\n\n"
            "## Failure Details\n"
            f"```json\n{failure_json}\n```\n\n"
            "## Workflow IR\n"
            f"```json\n{ir_json}\n```\n\n"
            "Provide:\n"
            "1. Root cause analysis.\n"
            "2. A corrected version of the failing step.\n"
            "3. Any additional waits or fallback selectors to add.\n"
        )
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.2,
                "num_predict": 2048,
            },
        }
        return self._post("/api/generate", payload)

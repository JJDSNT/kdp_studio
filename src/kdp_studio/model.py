"""The model behind the assistant, behind an adapter.

- `claude-cli` (the default): the Claude Code CLI with the author's own login.
  `claude -p` runs one turn headless, with no tools, no settings and no session
  kept, and answers in a JSON shape we give it. No key is stored by KDP Studio.
- `claude-api`: the Claude API through the official SDK, for use beyond one
  person's machine (`ANTHROPIC_API_KEY`).

Either way the graph decides what to do with the answer; the model only answers.
Pattern measured in Cine Toaster (its ADR 0017).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Protocol

from .errors import ToolUnavailableError


class ModelUnavailable(ToolUnavailableError):
    code = "model_unavailable"


class Model(Protocol):
    name: str

    def available(self) -> str: ...

    def ask(self, system: str, prompt: str, schema: dict[str, Any], *, web: bool = False,
            images: tuple = ()) -> dict[str, Any]:
        """Answer in the schema's shape. With `web`, the model may search and open pages; `images`
        are pictures (paths) it is shown with the prompt -- shown, never a file it may open itself."""
        ...


def _picture(path) -> dict[str, Any]:
    import base64
    import mimetypes
    from pathlib import Path

    kind = mimetypes.guess_type(str(path))[0] or "image/png"
    return {"type": "image", "source": {"type": "base64", "media_type": kind,
                                        "data": base64.b64encode(Path(path).read_bytes()).decode()}}


class ClaudeCli:
    name = "claude-cli"

    def __init__(self, executable: str | None = None, timeout: float = 300) -> None:
        self.executable = executable or os.environ.get("KDP_MODEL_CLI", "claude")
        self.timeout = timeout

    def available(self) -> str:
        return "" if shutil.which(self.executable) else f"{self.executable} is not on PATH (install Claude Code)"

    def ask(self, system: str, prompt: str, schema: dict[str, Any], *, web: bool = False,
            images: tuple = ()) -> dict[str, Any]:
        reason = self.available()
        if reason:
            raise ModelUnavailable(reason)
        # Only reading the web is ever granted: no file, shell or edit tool.
        tools = ["--tools", "WebSearch", "WebFetch", "--allowedTools", "WebSearch", "WebFetch"] if web \
            else ["--tools", ""]
        command = [self.executable, "-p", *tools, "--no-session-persistence", "--setting-sources", "",
                   "--system-prompt", system, "--json-schema", json.dumps(schema)]
        if images:
            # Pictures travel inside the message: the model is shown them, and is given no way to open a file.
            command += ["--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
            sent = json.dumps({"type": "user", "message": {"role": "user", "content": [
                {"type": "text", "text": prompt}, *[_picture(path) for path in images]]}}) + "\n"
        else:
            command += ["--output-format", "json"]
            sent = prompt
        try:
            completed = subprocess.run(command, input=sent, capture_output=True, text=True,
                                       timeout=self.timeout * (3 if web or images else 1))
        except subprocess.TimeoutExpired as error:
            raise ModelUnavailable(f"The model took longer than {self.timeout:.0f} s") from error
        if completed.returncode:
            raise ModelUnavailable(f"The model CLI failed: {completed.stderr.strip()[:300]}")
        if images:
            events = []
            for line in completed.stdout.splitlines():
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
            answer = next((e for e in reversed(events) if isinstance(e, dict) and e.get("type") == "result"), None)
            if answer is None:
                raise ModelUnavailable("The model CLI gave no result")
        else:
            answer = json.loads(completed.stdout)
        if answer.get("is_error"):
            raise ModelUnavailable(str(answer.get("result") or "The model answered with an error")[:300])
        return answer.get("structured_output") or json.loads(answer.get("result") or "{}")


def _closed(schema: Any) -> Any:
    """Every object closed (`additionalProperties: false`), as structured output wants."""

    if not isinstance(schema, dict):
        return schema
    closed = {key: _closed(value) for key, value in schema.items()}
    if closed.get("type") == "object":
        closed["properties"] = {key: _closed(value) for key, value in (closed.get("properties") or {}).items()}
        closed.setdefault("additionalProperties", False)
    if "items" in closed:
        closed["items"] = _closed(closed["items"])
    return closed


class ClaudeApi:
    name = "claude-api"

    #: If the model declines a turn, the API's own fallback serves it.
    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self, model: str | None = None, effort: str | None = None, client: Any = None) -> None:
        self.model = model or os.environ.get("KDP_MODEL_ID", "claude-opus-5-5")
        # Each turn is a short editorial answer; `KDP_MODEL_EFFORT` raises it.
        self.effort = effort or os.environ.get("KDP_MODEL_EFFORT", "low")
        self.client = client

    def available(self) -> str:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return "the anthropic SDK is not installed (uv sync --extra agents)"
        return ""

    def ask(self, system: str, prompt: str, schema: dict[str, Any], *, web: bool = False,
            images: tuple = ()) -> dict[str, Any]:
        reason = self.available()
        if reason:
            raise ModelUnavailable(reason)
        import anthropic

        client = self.client or anthropic.Anthropic()
        try:
            with client.beta.messages.stream(
                model=self.model, max_tokens=64000, system=system,
                messages=[{"role": "user", "content": [{"type": "text", "text": prompt},
                                                       *[_picture(path) for path in images]]
                           if images else prompt}],
                output_config={"effort": self.effort,
                               "format": {"type": "json_schema", "schema": _closed(schema)}},
                betas=[self.FALLBACK_BETA], fallbacks="default",
                **({"tools": [{"type": "web_search_20260209", "name": "web_search"},
                              {"type": "web_fetch_20260209", "name": "web_fetch"}]} if web else {}),
            ) as stream:
                response = stream.get_final_message()
        except anthropic.AuthenticationError as error:
            raise ModelUnavailable("The Claude API rejected the credentials (ANTHROPIC_API_KEY)") from error
        except anthropic.RateLimitError as error:
            raise ModelUnavailable("The Claude API is rate limiting; try again in a moment") from error
        except anthropic.APIStatusError as error:
            raise ModelUnavailable(f"The Claude API answered {error.status_code}: {error.message}") from error
        except anthropic.APIConnectionError as error:
            raise ModelUnavailable("The Claude API is not reachable from here") from error
        if response.stop_reason == "refusal":
            raise ModelUnavailable("The model declined to answer this turn")
        text = next((block.text for block in response.content if block.type == "text"), "")
        try:
            return json.loads(text)
        except ValueError as error:
            raise ModelUnavailable("The model's answer was not the expected shape") from error


ADAPTERS = {"claude-cli": ClaudeCli, "claude-api": ClaudeApi}


def model_from_env() -> Model:
    kind = os.environ.get("KDP_MODEL", "claude-cli")
    if kind not in ADAPTERS:
        raise ModelUnavailable(f"Unknown model adapter {kind!r}; available: {', '.join(ADAPTERS)}")
    return ADAPTERS[kind]()

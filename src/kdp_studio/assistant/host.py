"""Hosting the assistant beside the control room (ADR 0002).

`kdp serve <book> --assistant` runs, on this machine, and the page talks to one
origin:

- the control room runtime (this process);
- the assistant, a LangGraph agent over AG-UI, in a thread of this process;
- the Copilot Runtime, one bundled Node file, supervised: restarted if it
  stops. `/api/copilotkit` is proxied to it.

Conversations live in memory only: disposable operational state. A restart
forgets a conversation, never the book.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1] / "web_assets" / "copilot" / "copilot-runtime.mjs"


def unavailable_reason() -> str:
    """Why the assistant cannot run here, or an empty string."""

    try:
        import ag_ui_langgraph  # noqa: F401
        import langgraph  # noqa: F401
    except ImportError:
        return "the agents extra is not installed (uv sync --extra agents)"
    if not shutil.which("node"):
        return "Node is not installed (it runs the Copilot Runtime)"
    if not BUNDLE.is_file():
        return "the Copilot Runtime is not built (cd frontend && npm install && npm run build)"
    from ..model import model_from_env

    try:
        return model_from_env().available()
    except Exception as error:  # noqa: BLE001
        return getattr(error, "message", str(error))


def agent_app(root):
    """`root` is a book's path, or the control room's Studio so both follow the open book."""

    from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint
    from fastapi import FastAPI
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    from ..server import Studio
    from .graph import build
    from ..model import model_from_env

    # The page's context arrives as AG-UI objects and is checkpointed with the
    # turn; name the type rather than rely on a default LangGraph will close.
    serde = JsonPlusSerializer(allowed_msgpack_modules=[("ag_ui._generated.models", "Context"),
                                                        ("ag_ui.core.types", "Context")])
    graph = build(model_from_env(), root if isinstance(root, Studio) else Studio(root), MemorySaver(serde=serde))
    application = FastAPI(title="KDP Studio assistant")
    add_langgraph_fastapi_endpoint(application, LangGraphAgent(name="assistant", graph=graph), "/")
    return application


class AssistantHost:
    def __init__(self, root, agent_port: int, copilot_port: int) -> None:
        self.root = root
        self.agent_port = agent_port
        self.copilot_port = copilot_port
        self._stop = threading.Event()
        self._process: subprocess.Popen | None = None
        self.last_error = ""

    @property
    def copilot_url(self) -> str:
        return f"http://127.0.0.1:{self.copilot_port}"

    def start(self) -> None:
        import uvicorn

        server = uvicorn.Server(uvicorn.Config(agent_app(self.root), host="127.0.0.1", port=self.agent_port,
                                               log_level="warning"))
        threading.Thread(target=server.run, name="assistant", daemon=True).start()
        threading.Thread(target=self._supervise, name="copilot-runtime", daemon=True).start()

    def _supervise(self) -> None:
        env = {**os.environ, "COPILOTKIT_TELEMETRY_DISABLED": "true", "DO_NOT_TRACK": "1",
               "KDP_COPILOT_PORT": str(self.copilot_port),
               "KDP_ASSISTANT_URL": f"http://127.0.0.1:{self.agent_port}/"}
        delay = 1.0
        while not self._stop.is_set():
            started = time.monotonic()
            self._process = subprocess.Popen(["node", str(BUNDLE)], env=env, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.PIPE, text=True)
            _, error = self._process.communicate()
            if self._stop.is_set():
                return
            self.last_error = (error or "").strip()[-500:]
            # One that keeps dying at once is retried more slowly.
            delay = 1.0 if time.monotonic() - started > 30 else min(delay * 2, 30.0)
            time.sleep(delay)

    def stop(self) -> None:
        self._stop.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()

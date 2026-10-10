"""The flow every agent's work goes through, as one LangGraph graph.

A manifest, or an agent's prompt, gives the direction. What happens around
the answer is not the agent's to write, and is the same for all of them:

    draft ──▶ check ──▶ land ──▶ hold ──▶ done
      ▲         │                 │ ▲
      │   fails, tries left       │ └── review ◀── "critique"
      └─────────┴──────── "redo" ─┘

- **draft**: the model answers.
- **check**: deterministic checks, by name, say whether the answer may land
  (the edits apply; no fact moved under a wording scope; the specimen builds).
  A failure goes back to the model with the reason, a bounded number of times;
  after that the work fails and nothing lands.
- **land**: the answer enters the book, or the catalogue, through commands.
- **hold**: the graph interrupts and waits for the author, who can always
  **critique** (a reviewer looks at what landed), **redo** (in their own
  words, or answering the last criticism), or close. Nothing is redone that a
  person did not ask for.

The interrupt lives alone in its node, so resuming re-runs nothing that
writes. Checkpoints are in memory: a runtime that stops forgets a held flow,
never what landed. A caller with nobody to ask (the command line, a test)
gives the answers in advance as a `script`.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Protocol, TypedDict

from ..errors import KdpStudioError, ToolUnavailableError, ValidationError

ACTIONS = ("critique", "redo", "done")


class Work(Protocol):
    """One piece of work an agent does; the flow drives it."""

    title: str
    attempts: int
    can_review: bool

    def draft(self, request: str, standing: dict[str, Any] | None, error: str) -> dict[str, Any]:
        """The model's answer: fresh, or `standing` redone as `request` asks, or fixed after `error`."""
        ...

    def check(self, draft: dict[str, Any]) -> list[str]:
        """Why this answer may not land; empty when it may."""
        ...

    def land(self, draft: dict[str, Any]) -> dict[str, Any]: ...

    def review(self, outcome: dict[str, Any]) -> dict[str, Any]:
        """A reviewer's look at what landed: at least `verdict` (accept|revise) and `instruction`."""
        ...

    def failure(self, problems: list[str], standing: dict[str, Any] | None) -> KdpStudioError: ...

    def result(self, state: dict[str, Any]) -> dict[str, Any]: ...


class State(TypedDict, total=False):
    request: str
    standing: dict
    draft: dict
    error: str
    problems: list
    attempt: int
    drawings: int
    outcome: dict
    reviews: list
    script: list
    decision: dict


def _graph(work: Work, interactive: bool, progress: Callable[[str], None]):
    try:
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import interrupt
    except ImportError as error:
        raise ToolUnavailableError("Agents run on LangGraph: uv sync --extra agents") from error

    def draft(state: State) -> dict[str, Any]:
        attempt = state.get("attempt", 0) + 1
        progress(f"{work.title}: " + ("answering again" if state.get("standing") or attempt > 1 else "working")
                 + (f" (attempt {attempt}: {state['error'][:80]})" if state.get("error") else ""))
        return {"draft": work.draft(state.get("request", ""), state.get("standing"), state.get("error", "")),
                "attempt": attempt}

    def check(state: State) -> dict[str, Any]:
        problems = work.check(state["draft"])
        return {"problems": problems, "error": "\n".join(problems)}

    def after_check(state: State) -> str:
        if not state["problems"]:
            return "land"
        return "draft" if state["attempt"] < work.attempts else "fail"

    def fail(state: State) -> dict[str, Any]:
        raise work.failure(state["problems"], state.get("standing"))

    def land(state: State) -> dict[str, Any]:
        outcome = work.land(state["draft"])
        return {"outcome": outcome, "standing": state["draft"], "attempt": 0, "error": "", "request": "",
                "drawings": state.get("drawings", 0) + 1}

    def hold(state: State) -> dict[str, Any]:
        """Wait for a person — or take the next answer of the script. Nothing else happens here."""

        script = list(state.get("script") or [])
        last = (state.get("reviews") or [None])[-1]
        if script:
            action = script.pop(0)
            # A script does not redo what its own reviewer accepted.
            if action == "redo" and (last is None or last.get("verdict") == "accept"):
                return {"decision": {"action": "done"}, "script": []}
            return {"decision": {"action": action}, "script": script}
        if not interactive:
            return {"decision": {"action": "done"}}
        answer = interrupt({"title": work.title, "can_review": work.can_review,
                            "reviewed": bool(last), "verdict": (last or {}).get("verdict", ""),
                            "message": (last or {}).get("summary") or "It landed. Critique it, redo it, or close."})
        action = answer.get("action") if isinstance(answer, dict) else ""
        return {"decision": {"action": action if action in ACTIONS else "done",
                             "instruction": str((answer or {}).get("instruction", "")) if isinstance(answer, dict)
                             else ""}}

    def after_hold(state: State) -> str:
        action = state["decision"]["action"]
        if action == "critique":
            return "review" if work.can_review else "hold"
        return "redo" if action == "redo" else END

    def review(state: State) -> dict[str, Any]:
        progress(f"{work.title}: a reviewer is looking at it")
        return {"reviews": [*(state.get("reviews") or []), work.review(state["outcome"])]}

    def redo(state: State) -> dict[str, Any]:
        last = (state.get("reviews") or [None])[-1]
        request = state["decision"].get("instruction", "").strip() or (last or {}).get("instruction", "")
        if not request:
            raise ValidationError("Say what to change, or have it critiqued first")
        return {"request": request, "attempt": 0, "error": ""}

    graph = StateGraph(State)
    for name, node in (("draft", draft), ("check", check), ("fail", fail), ("land", land), ("hold", hold),
                       ("review", review), ("redo", redo)):
        graph.add_node(name, node)
    graph.add_edge(START, "draft")
    graph.add_edge("draft", "check")
    graph.add_conditional_edges("check", after_check, {"land": "land", "draft": "draft", "fail": "fail"})
    graph.add_edge("fail", END)
    graph.add_edge("land", "hold")
    graph.add_conditional_edges("hold", after_hold, {"review": "review", "redo": "redo", "hold": "hold", END: END})
    graph.add_edge("review", "hold")
    graph.add_edge("redo", "draft")
    return graph.compile(checkpointer=MemorySaver())


class Flow:
    """One run of the graph for one piece of work, which may be waiting for its author."""

    def __init__(self, work: Work, *, interactive: bool = False, script: list[str] | None = None,
                 progress: Callable[[str], None] = lambda message: None) -> None:
        self.work, self.script = work, list(script or [])
        self.graph = _graph(work, interactive, progress)
        self.config = {"configurable": {"thread_id": uuid.uuid4().hex}, "recursion_limit": 60}
        self.waiting: dict[str, Any] | None = None

    def start(self, *, request: str = "", standing: dict[str, Any] | None = None) -> dict[str, Any]:
        initial: State = {"request": request, "script": self.script, "reviews": []}
        if standing:
            initial["standing"] = standing
        return self._after(self.graph.invoke(initial, self.config))

    def answer(self, action: str, instruction: str = "") -> dict[str, Any]:
        from langgraph.types import Command

        if self.waiting is None:
            raise ValidationError("This work is not waiting for an answer")
        if action not in ACTIONS:
            raise ValidationError(f"Unknown answer {action!r}", allowed=list(ACTIONS))
        return self._after(self.graph.invoke(Command(resume={"action": action, "instruction": instruction}),
                                             self.config))

    def _after(self, state: dict[str, Any]) -> dict[str, Any]:
        held = state.get("__interrupt__")
        self.waiting = held[0].value if held else None
        result = self.work.result(state)
        if self.waiting is not None:
            result["waiting"] = self.waiting
        return result


def hold_for_job(progress: Any, flow: Flow) -> None:
    """Keep a waiting flow where the job runner finds it when the author answers."""

    from .. import jobs

    if isinstance(progress, jobs.Progress):
        jobs.HELD[progress.job_id] = flow

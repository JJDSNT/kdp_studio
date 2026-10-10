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
writes. A job's flow is checkpointed on disk beside the job store
(`flows.sqlite`): a runtime that restarts can still be answered, because the
work is rebuilt from the job's own kind and payload and the graph resumes
from its checkpoint. Everything a result needs is in the graph's state, not
in the object that ran it. A caller with nobody to ask (the command line, a
test) gives the answers in advance as a `script`, in memory.
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


def _graph(work: Work, interactive: bool, progress: Callable[[str], None], checkpointer: Any = None):
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
    return graph.compile(checkpointer=checkpointer or MemorySaver())


class Flow:
    """One run of the graph for one piece of work, which may be waiting for its author."""

    def __init__(self, work: Work, *, interactive: bool = False, script: list[str] | None = None,
                 progress: Callable[[str], None] = lambda message: None, checkpointer: Any = None,
                 thread: str = "") -> None:
        self.work, self.script = work, list(script or [])
        self.graph = _graph(work, interactive, progress, checkpointer)
        self.config = {"configurable": {"thread_id": thread or uuid.uuid4().hex}, "recursion_limit": 60}
        self.waiting: dict[str, Any] | None = None

    def held(self) -> bool:
        """Whether a checkpoint of this thread is waiting at the hold (after a restart, say)."""

        return "hold" in (self.graph.get_state(self.config).next or ())

    def start(self, *, request: str = "", standing: dict[str, Any] | None = None) -> dict[str, Any]:
        initial: State = {"request": request, "script": self.script, "reviews": []}
        if standing:
            initial["standing"] = standing
        return self._after(self.graph.invoke(initial, self.config))

    def answer(self, action: str, instruction: str = "") -> dict[str, Any]:
        from langgraph.types import Command

        if self.waiting is None and not self.held():
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


def persistent(path) -> Any:
    """A checkpointer on disk for the flows of one book's jobs; None when the extra for it is missing."""

    try:
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(str(path), check_same_thread=False))


def again(prompt: str, request: str, standing: dict[str, Any] | None, error: str) -> str:
    """The prompt of a second answer: what stood, what to change, and why the last one could not be used."""

    import json

    if standing:
        prompt += ("\n\nYou already answered this. Your answer was:\n" + json.dumps(standing, ensure_ascii=False)
                   + f"\n\nDo it again, in full, changing what this asks and keeping the rest:\n{request}")
    if error:
        prompt += f"\n\nYour last answer could not be used. Fix it and answer again in full.\nWhy:\n{error}"
    return prompt


REVIEW_SYSTEM = (
    "You review the work of another agent of a book production tool: you are its critic, not its colleague. You "
    "are given the role it was asked to play, what it was shown, and what it answered. Judge the answer against "
    "the role: did it do the job, or a neighbouring one; is each point specific — a passage quoted, a reason — "
    "or generic advice that would fit any book; did it guess where it should have said it could not establish; "
    "did it miss what a careful reader of the same material would have seen; did it stay inside its scope. For "
    "text it wrote or changed, judge the writing as an editor would: does it serve the book's intention and "
    "voice, does it leave facts alone, does it read as written by a person of that language. Do not redo the "
    "work. `verdict` is `accept` when the author can rely on it as it is, else `revise`; each problem has a "
    "`fix` the agent can act on. Write for the author, in their language."
)

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "overall": {"type": "string"},
        "problems": {"type": "array", "items": {"type": "object", "properties": {
            "what": {"type": "string"}, "why": {"type": "string"}, "fix": {"type": "string"}},
            "required": ["what", "why", "fix"]}},
        "verdict": {"type": "string", "enum": ["accept", "revise"]},
    },
    "required": ["overall", "problems", "verdict"],
}


def review_work(model: Any, *, title: str, role: str, shown: str, answered: str,
                system: str = REVIEW_SYSTEM) -> dict[str, Any]:
    """A critic's look at what an agent answered: a verdict, and an instruction the agent can act on."""

    prompt = f"The agent: {title}. Its role: {role}\n\nWhat it was shown:\n{shown}\n\nWhat it answered:\n{answered}"
    seen = model.ask(system, prompt, REVIEW_SCHEMA)
    problems = seen.get("problems") or []
    return {"verdict": seen["verdict"], "overall": seen["overall"], "problems": problems,
            "instruction": "A reviewer read your answer. " + str(seen["overall"]) + "\nWhat to change:\n"
                           + "\n".join(f"- {p['what']} ({p['why']}) Fix: {p['fix']}" for p in problems),
            "summary": f"The reviewer says {seen['verdict']}: " + str(seen["overall"])[:300]}


class SimpleWork:
    """Work made of four functions: how the model is asked, the named checks, how the answer lands, who reviews.

    Most agents are this and nothing more; what its result needs travels in the graph's state.
    """

    def __init__(self, title: str, *, ask: Callable[[str, dict | None, str], dict[str, Any]],
                 land: Callable[[dict[str, Any]], dict[str, Any]],
                 checks: list[tuple[str, Callable[[dict[str, Any]], list[str]]]] | None = None,
                 review: Callable[[dict[str, Any]], dict[str, Any]] | None = None, attempts: int = 2) -> None:
        self.title, self.attempts, self.can_review = title, attempts, review is not None
        self._ask, self._land, self._checks, self._review = ask, land, list(checks or []), review

    def draft(self, request: str, standing: dict[str, Any] | None, error: str) -> dict[str, Any]:
        return self._ask(request, standing, error)

    def check(self, draft: dict[str, Any]) -> list[str]:
        return [f"[{name}] {problem}" for name, run in self._checks for problem in run(draft)]

    def failure(self, problems: list[str], standing: dict[str, Any] | None) -> KdpStudioError:
        return ValidationError(f"{self.title} could not give an answer that may be used, after {self.attempts} "
                               "attempt(s): " + " ".join(problems)[:600])

    def land(self, draft: dict[str, Any]) -> dict[str, Any]:
        return self._land(draft)

    def review(self, outcome: dict[str, Any]) -> dict[str, Any]:
        """The reviewer is given what landed — a record it can read — not the object that made it."""

        assert self._review is not None
        return self._review(outcome)

    def result(self, state: dict[str, Any]) -> dict[str, Any]:
        return {**(state.get("outcome") or {}), "answers": state.get("drawings", 0),
                "reviews": [{k: v.get(k) for k in ("verdict", "overall", "problems")}
                            for v in state.get("reviews") or []]}


def run_work(work: Work, *, script: list[str] | None = None, progress: Callable[[str], None] = lambda m: None,
             request: str = "", standing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Work done at once by a caller with nobody to ask: the script answers the hold."""

    return Flow(work, script=script, progress=progress).start(request=request, standing=standing)

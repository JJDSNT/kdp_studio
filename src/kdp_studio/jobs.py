"""Background jobs: agent work that takes longer than a chat turn.

A job is operational state, not book state: its record lives in
`$XDG_STATE_HOME/kdp-studio/<book id>/jobs.json`, and deleting it loses the
job history, never the book. What a job *produces* is always a book record --
a candidate version, a report -- written through the same commands as
everything else, so the book can be understood without the job store.

Jobs run in threads of the runtime that started them. On restart, a job that
was running is marked `interrupted`; its work was never half-written into the
book, because results are committed only when complete.
"""

from __future__ import annotations

import json
import os
import threading
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable

from .book import Book
from .errors import NotFoundError, ValidationError
from .state import Actor, now

#: waiting: the work landed and its flow is held for the author, who may critique it, redo it or close.
STATES = ("queued", "running", "waiting", "done", "failed", "interrupted")
_lock = threading.Lock()
#: job id -> the flow held for it (agents/flow.py). In memory: a runtime that stops forgets it.
HELD: dict[str, Any] = {}


def store_path(book: Book) -> Path:
    """Per book *and* location: two copies of one book never share their jobs."""

    import hashlib

    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    where = hashlib.sha256(str(book.root.resolve()).encode()).hexdigest()[:10]
    return Path(base) / "kdp-studio" / f"{book.id}-{where}" / "jobs.json"


def _read(book: Book) -> dict[str, dict[str, Any]]:
    path = store_path(book)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text("utf-8"))
    except ValueError:
        return {}


def _write(book: Book, jobs: dict[str, dict[str, Any]]) -> None:
    path = store_path(book)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _update(book: Book, job_id: str, **changes: Any) -> dict[str, Any]:
    with _lock:
        jobs = _read(book)
        job = jobs[job_id]
        job.update(changes, updated_at=now())
        _write(book, jobs)
        return job


def list_jobs(book: Book) -> list[dict[str, Any]]:
    return sorted(_read(book).values(), key=lambda j: j["created_at"], reverse=True)


def get_job(book: Book, job_id: str) -> dict[str, Any]:
    job = _read(book).get(job_id)
    if job is None:
        raise NotFoundError(f"No job {job_id!r}")
    return job


def reconcile(book: Book) -> None:
    """A job left running by a runtime that stopped did not finish; one that was held can still be answered."""

    from . import agents, art  # noqa: F401 - the kinds on the flow must be known to tell which waits survive

    with _lock:
        jobs = _read(book)
        for job in jobs.values():
            if job["state"] in ("queued", "running"):
                job.update(state="interrupted", updated_at=now(),
                           note="The runtime stopped before the job finished; nothing was written.")
            elif job["state"] == "waiting" and job["id"] not in HELD and job["kind"] not in FLOW_KINDS:
                # What it made is in the book; only the chance to answer it in place is gone.
                job.update(state="done", updated_at=now(), waiting=None)
        _write(book, jobs)


class Progress:
    def __init__(self, book: Book, job_id: str) -> None:
        self.book, self.job_id = book, job_id

    def __call__(self, message: str) -> None:
        job = get_job(self.book, self.job_id)
        _update(self.book, self.job_id, progress=[*job.get("progress", []), {"at": now(), "message": message}])


#: kind -> (what it does, the function). Filled by the modules that define jobs.
KINDS: dict[str, tuple[str, Callable[[Book, dict[str, Any], Actor, Progress], dict[str, Any]]]] = {}


def kind(name: str, description: str):
    def register(function):
        KINDS[name] = (description, function)
        return function
    return register


#: kind -> how its work is built from a job's payload: (work, how the flow starts, the scripted answers).
FLOW_KINDS: dict[str, Callable[[Book, dict[str, Any], Callable[[str], None]], tuple[Any, dict[str, Any], list]]] = {}


def flow_kind(name: str, description: str):
    """A job kind whose work runs on the flow (agents/flow.py): checked, landed, then held for the author.

    The function builds the work from the payload and does nothing else, so a
    runtime that restarted can build it again and resume the held graph.
    """

    def register(factory):
        FLOW_KINDS[name] = factory

        def run(book: Book, payload: dict[str, Any], actor: Actor, progress: Progress) -> dict[str, Any]:
            work, start_with, script = factory(book, payload, progress)
            flow = _flow(book, work, progress.job_id, progress, script)
            HELD[progress.job_id] = flow
            return flow.start(**start_with)

        KINDS[name] = (description, run)
        return factory
    return register


def _flow(book: Book, work: Any, job_id: str, progress: Callable[[str], None], script: list | None = None):
    from .agents.flow import Flow, persistent

    return Flow(work, interactive=True, script=script, progress=progress, thread=job_id,
                checkpointer=persistent(store_path(book).with_name("flows.sqlite")))


def _run(book: Book, job_id: str, work: Callable[[], dict[str, Any]]) -> None:
    _update(book, job_id, state="running")
    try:
        result = work()
        held = isinstance(result, dict) and result.get("waiting") and job_id in HELD
        if not held:
            HELD.pop(job_id, None)
        _update(book, job_id, state="waiting" if held else "done", result=result,
                waiting=result.get("waiting") if held else None)
    except Exception as error:  # noqa: BLE001 - the job records why it failed
        HELD.pop(job_id, None)
        message = getattr(error, "message", str(error)) or error.__class__.__name__
        _update(book, job_id, state="failed", error=message, trace=traceback.format_exc(limit=4)[-2000:])


def answer(book: Book, job_id: str, action: str, instruction: str = "", *, wait: bool = False) -> dict[str, Any]:
    """The author's answer to work that is waiting: critique it, redo it, or close it."""

    from . import agents, art  # noqa: F401 - register the job kinds

    job = get_job(book, job_id)
    if job["state"] != "waiting":
        raise ValidationError("This job is not waiting for an answer")
    progress = Progress(book, job_id)
    flow = HELD.get(job_id)
    if flow is None and job["kind"] in FLOW_KINDS:
        # Another runtime held it: build the work again from the job itself and resume its checkpoint.
        work, _, _ = FLOW_KINDS[job["kind"]](book, {**job["payload"], "_resume": True}, progress)
        flow = _flow(book, work, job_id, progress)
        if flow.held():
            HELD[job_id] = flow
        else:
            flow = None
    if flow is None:
        _update(book, job_id, state="done", waiting=None)
        raise ValidationError("The wait of this job was lost with the runtime that held it; what it made is "
                              "in the book. Start it again to redo it.")
    progress(f"You answered: {action}" + (f" — {instruction}" if instruction else ""))

    def run() -> None:
        _run(book, job_id, lambda: flow.answer(action, instruction))

    if wait:
        run()
    else:
        threading.Thread(target=run, name=job_id, daemon=True).start()
    return get_job(book, job_id)


def start(book: Book, kind_name: str, payload: dict[str, Any], actor: Actor, *, wait: bool = False) -> dict[str, Any]:
    from . import agents, art  # noqa: F401 - register their job kinds

    if kind_name not in KINDS:
        raise ValidationError(f"Unknown job kind {kind_name!r}", kinds=sorted(KINDS))
    job = {"id": f"job-{uuid.uuid4().hex[:8]}", "kind": kind_name, "payload": payload, "state": "queued",
           "created_at": now(), "updated_at": now(), "requested_by": actor.public_dict(), "progress": [],
           "result": None, "error": ""}
    with _lock:
        jobs = _read(book)
        jobs[job["id"]] = job
        _write(book, jobs)

    def run() -> None:
        _run(book, job["id"], lambda: KINDS[kind_name][1](book, payload, actor, Progress(book, job["id"])))

    if wait:
        run()
    else:
        threading.Thread(target=run, name=job["id"], daemon=True).start()
    return get_job(book, job["id"])

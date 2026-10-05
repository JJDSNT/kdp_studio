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

STATES = ("queued", "running", "done", "failed", "interrupted")
_lock = threading.Lock()


def store_path(book: Book) -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "kdp-studio" / book.id / "jobs.json"


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
    """A job left running by a runtime that stopped did not finish."""

    with _lock:
        jobs = _read(book)
        for job in jobs.values():
            if job["state"] in ("queued", "running"):
                job.update(state="interrupted", updated_at=now(),
                           note="The runtime stopped before the job finished; nothing was written.")
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


def start(book: Book, kind_name: str, payload: dict[str, Any], actor: Actor, *, wait: bool = False) -> dict[str, Any]:
    from . import agents  # noqa: F401 - registers the agent job kinds

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
        _update(book, job["id"], state="running")
        try:
            result = KINDS[kind_name][1](book, payload, actor, Progress(book, job["id"]))
            _update(book, job["id"], state="done", result=result)
        except Exception as error:  # noqa: BLE001 - the job records why it failed
            message = getattr(error, "message", str(error)) or error.__class__.__name__
            _update(book, job["id"], state="failed", error=message,
                    trace=traceback.format_exc(limit=4)[-2000:])

    if wait:
        run()
    else:
        threading.Thread(target=run, name=job["id"], daemon=True).start()
    return get_job(book, job["id"])

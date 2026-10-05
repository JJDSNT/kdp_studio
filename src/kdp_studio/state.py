"""Runtime-owned book state: gates and decisions, in ``<book>/state.json``.

Authored files are never rewritten by KDP Studio. What it decides lives here,
beside them, with a revision that every write checks (optimistic
concurrency) and a lock that holds across processes. When the book is a git
repository, every committed decision is also a git commit of this file alone,
so the book's history says who decided what, when and why.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows keeps no cross-process lock
    fcntl = None

from .errors import RevisionConflictError, ValidationError

STATE_FILENAME = "state.json"
SCHEMA_VERSION = 1
ACTOR_KINDS = {"human", "agent", "system"}


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Actor:
    id: str
    kind: str = "human"

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValidationError("Actor id must not be empty")
        if self.kind not in ACTOR_KINDS:
            raise ValidationError(f"Unknown actor kind {self.kind!r}", allowed=sorted(ACTOR_KINDS))

    def public_dict(self) -> dict[str, str]:
        return {"id": self.id, "kind": self.kind}


def empty_state() -> dict[str, Any]:
    return {"schema": SCHEMA_VERSION, "revision": 0, "updated_at": "", "gates": {}, "history": []}


def read_state(root: Path) -> dict[str, Any]:
    path = root / STATE_FILENAME
    text = path.read_text("utf-8") if path.is_file() else ""
    if not text.strip():
        return empty_state()
    data = json.loads(text)
    return {**empty_state(), **data}


_held = threading.local()


@contextmanager
def book_lock(root: Path) -> Iterator[None]:
    """One writer per book, across processes; re-entrant within a thread.

    A command that holds the lock may call another that takes it (adopting a
    plan writes the contents): a second flock on the same file from the same
    thread would wait for itself forever.
    """

    key = str(root.resolve())
    depth = getattr(_held, "depth", {})
    _held.depth = depth
    if depth.get(key):
        depth[key] += 1
        try:
            yield
        finally:
            depth[key] -= 1
        return
    path = root / STATE_FILENAME
    if fcntl is None:
        depth[key] = 1
        try:
            yield
        finally:
            depth[key] = 0
        return
    with open(path, "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        depth[key] = 1
        try:
            yield
        finally:
            depth[key] = 0
            fcntl.flock(handle, fcntl.LOCK_UN)


def commit_state(root: Path, state: dict[str, Any], *, expected_revision: int | None,
                 message: str, actor: Actor, also: tuple[Path, ...] = ()) -> dict[str, Any]:
    """Write a new revision atomically, and commit it with ``also``. The caller holds ``book_lock``."""

    current = read_state(root)
    if expected_revision is not None and expected_revision != current["revision"]:
        raise RevisionConflictError(expected_revision, current["revision"])
    state = {**state, "schema": SCHEMA_VERSION, "revision": current["revision"] + 1, "updated_at": now()}
    path = root / STATE_FILENAME
    descriptor, temporary = tempfile.mkstemp(dir=root, prefix=".state-", suffix=".json")
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary, path)
    from .history import commit

    commit(root, [path, *also], message, actor)
    return state

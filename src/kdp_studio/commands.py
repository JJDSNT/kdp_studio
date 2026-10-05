"""The single write boundary: every change to a book, whoever asks.

The CLI, the control room and the agents all call ``dispatch``. A command
names a domain intent; callers never write a book's files themselves. What an
agent may do is listed here, once: it may prepare and propose, never decide.
"""

from __future__ import annotations

from typing import Any, Callable

from . import gates, versions
from .book import Book
from .build import build_ebook, build_print
from .errors import NotFoundError, ValidationError
from .state import Actor

#: Commands an agent may run. Deciding a gate, adopting or rejecting a version
#: and editing text directly are a person's.
AGENT_COMMANDS = {"open_gate", "propose_version", "build", "check", "start_job"}


def _open_gate(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    return gates.open_gate(book, p["kind"], p.get("subject", ""), actor=actor, note=p.get("note", ""))


def _decide_gate(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    return gates.decide_gate(book, p["gate_id"], p["decision"], actor=actor, rationale=p.get("rationale", ""),
                             expected_revision=p.get("expected_revision"))


def _save_section(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    return versions.save_section(book, p["language"], p["section"], p["text"],
                                 expected_digest=p["expected_digest"], actor=actor, reason=p.get("reason", ""))


def _propose_version(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    return versions.propose_version(book, p["language"], p["section"], p["text"], actor=actor,
                                    scope=p["scope"], rationale=p.get("rationale", ""), task=p.get("task", ""))


def _adopt_version(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    return versions.adopt_version(book, p["version_id"], actor=actor, rationale=p.get("rationale", ""))


def _reject_version(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    return versions.reject_version(book, p["version_id"], actor=actor, rationale=p.get("rationale", ""))


def _build(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    language = p.get("language") or book.source_language
    edition = p.get("edition", "print")
    result = build_print(book, language) if edition == "print" else build_ebook(book, language)
    return {"edition": edition, "language": language, "output": str(result.output.relative_to(book.root)),
            "details": result.details}


def _check(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    from .checks.run import run_checks

    language = p.get("language") or book.source_language
    return run_checks(book, language, p.get("edition", "print"))


def _start_job(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    from . import jobs

    return jobs.start(book, p["kind"], dict(p.get("payload") or {}), actor)


COMMANDS: dict[str, Callable[[Book, Actor, dict[str, Any]], dict[str, Any]]] = {
    "open_gate": _open_gate,
    "decide_gate": _decide_gate,
    "save_section": _save_section,
    "propose_version": _propose_version,
    "adopt_version": _adopt_version,
    "reject_version": _reject_version,
    "build": _build,
    "check": _check,
    "start_job": _start_job,
}


def dispatch(book: Book, command: str, payload: dict[str, Any], actor: Actor) -> dict[str, Any]:
    handler = COMMANDS.get(command)
    if handler is None:
        raise NotFoundError(f"Unknown command {command!r}", commands=sorted(COMMANDS))
    if actor.kind == "agent" and command not in AGENT_COMMANDS:
        raise ValidationError(f"An agent may not run {command!r}; it prepares, the author decides",
                              allowed=sorted(AGENT_COMMANDS))
    try:
        return handler(book, actor, payload)
    except KeyError as missing:
        raise ValidationError(f"{command} needs {missing.args[0]!r}") from None

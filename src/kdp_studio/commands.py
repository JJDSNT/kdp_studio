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
#: Reordering changes the book's order, so the assistant asks the author first.
#: A new language and a first glossary are created, never overwritten; the
#: assistant asks first all the same.
AGENT_COMMANDS = {"open_gate", "propose_version", "build", "check", "start_job", "reorder", "add_section",
                  "remove_section", "add_part", "write_intentions", "add_language", "write_glossary", "add_art",
                  "set_theme", "add_report"}


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
    if edition == "cover":
        from .cover import build_cover

        result = build_cover(book, language)
    else:
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


def _reorder(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    from .structure import move

    where = {k: str(p[k]) for k in ("section", "part", "before", "after", "into") if p.get(k)}
    return move(book, actor=actor, reason=p.get("reason", ""), **where)


def _approve_chapter(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    """Open and decide a chapter gate in one act: the author approving what they just read."""

    gate = gates.open_gate(book, "chapter", p["section"], actor=actor)
    return gates.decide_gate(book, gate["id"], "approved", actor=actor, rationale=p.get("rationale", ""))


def _add_section(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    from .structure import add_section

    return add_section(book, title=p["title"], actor=actor, reason=p.get("reason", ""),
                       synopsis=p.get("synopsis", ""), promise=p.get("promise", ""), kind=p.get("kind", "chapter"),
                       before=p.get("before", ""), after=p.get("after", ""), into=str(p.get("into", "") or ""))


def _remove_section(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    from .structure import remove_section

    return remove_section(book, section=p["section"], actor=actor, reason=p.get("reason", ""))


def _add_part(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    from .structure import add_part

    return add_part(book, part=str(p["part"]), title=p["title"], actor=actor, reason=p.get("reason", ""),
                    kind=p.get("kind", "part"), before=str(p.get("before", "") or ""),
                    after=str(p.get("after", "") or ""))


def _adopt_plan(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    from .agents.architect import adopt_plan

    return adopt_plan(book, p["plan_id"], actor=actor, rationale=p.get("rationale", ""))


def _write_intentions(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    """intentions.md in the author's words, as agreed in the conversation; the author confirmed it."""

    from .history import commit
    from .state import book_lock

    text = str(p.get("text", "")).strip()
    if not text:
        raise ValidationError("intentions.md cannot be empty")
    path = book.root / "intentions.md"
    with book_lock(book.root):
        path.write_text(text + "\n", encoding="utf-8")
        commit(book.root, [path], "Intentions: " + (p.get("reason") or "written with the author"), actor)
    return {"path": "intentions.md", "words": len(text.split())}


def _add_language(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    from .translation import add_language

    return add_language(book, p["language"], actor=actor, reason=p.get("reason", ""), meta=p.get("meta") or None)


def _confirm_translation(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    from .translation import confirm_translation

    return confirm_translation(book, p["language"], p["section"], actor=actor, rationale=p.get("rationale", ""))


def _write_glossary(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    from .translation import write_glossary

    return write_glossary(book, str(p["text"]), actor=actor, reason=p.get("reason", ""),
                          replace=bool(p.get("replace")))


def _add_art(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    from pathlib import Path

    from . import art

    return art.add(book, Path(p["file"]), p["id"], actor=actor, purpose=p.get("purpose", "illustration"),
                   prompt=p.get("prompt", ""), model=p.get("model", ""), provider=p.get("provider", ""),
                   seed=p.get("seed"), derived_from=p.get("derived_from", ""), lettering=p.get("lettering", "none"),
                   notes=p.get("notes", ""), provenance=p.get("provenance") or None)


def _set_theme(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    from .gallery import apply_theme

    return apply_theme(book, p["theme"], actor=actor, reason=p.get("reason", ""))


def _add_report(book: Book, actor: Actor, p: dict[str, Any]) -> dict[str, Any]:
    """An agent's report, kept as a dated document in the book: nothing is replaced, nothing else changes."""

    import re

    from .history import commit
    from .state import book_lock, now

    text = str(p.get("text", "")).strip()
    agent, subject = str(p["agent"]), str(p.get("subject") or "book")
    if not text:
        raise ValidationError("A report cannot be empty")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,40}", agent) or not re.fullmatch(r"[\w.-]{1,80}", subject):
        raise ValidationError("A report names its agent and its subject plainly")
    stamp = now().replace(":", "").replace("-", "")[:15]
    path = book.root / "reports" / agent / f"{stamp}-{subject}.md"
    with book_lock(book.root):
        path.parent.mkdir(parents=True, exist_ok=True)
        again = 2
        while path.exists():  # a second answer in the same second is another report, never the same file
            path = path.with_name(f"{stamp}-{subject}-{again}.md")
            again += 1
        path.write_text(text + "\n", encoding="utf-8")
        commit(book.root, [path], f"Report by {agent} on {subject}", actor)
    return {"path": str(path.relative_to(book.root)), "words": len(text.split())}


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
    "reorder": _reorder,
    "approve_chapter": _approve_chapter,
    "add_section": _add_section,
    "remove_section": _remove_section,
    "add_part": _add_part,
    "adopt_plan": _adopt_plan,
    "write_intentions": _write_intentions,
    "add_language": _add_language,
    "confirm_translation": _confirm_translation,
    "write_glossary": _write_glossary,
    "add_art": _add_art,
    "set_theme": _set_theme,
    "add_report": _add_report,
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

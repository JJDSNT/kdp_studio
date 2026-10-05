"""Human gates (docs/origin, §6): the points where the work stops for the author.

A gate is a production record, not chat. It records who decided, when, why,
and *which version* was judged: a digest of the files the gate is about. An
approval is never inherited by a later version -- when those files change, the
gate shows "changed since the decision", and only a new gate can approve the
new version. A decided gate is never rewritten.

No edge skips a gate, and an agent never decides one: it may prepare the
decision, never take it.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .book import BOOK_FILENAME, Book
from .errors import NotFoundError, ValidationError
from .state import Actor, book_lock, commit_state, now, read_state

DECISIONS = {"approved", "changes_requested", "rejected"}


@dataclass(frozen=True)
class GateKind:
    id: str
    question: str
    needs_subject: bool = False


KINDS = {
    k.id: k for k in (
        GateKind("intention", "Is intentions.md the author's intention, in the author's words?"),
        GateKind("material", "What happens to the existing material?"),
        GateKind("architecture", "Does the structure serve the intention?"),
        GateKind("voice", "Is the voice right, judged on a complete, typeset pilot chapter?", needs_subject=True),
        GateKind("freeze", "Freeze the text of this language?", needs_subject=True),
        GateKind("publish", "Publish this edition?", needs_subject=True),
    )
}


def _files(book: Book, kind: str, subject: str) -> list[Path]:
    root = book.root
    if kind == "intention":
        return [root / "intentions.md"]
    if kind == "architecture":
        return [root / BOOK_FILENAME, book.manuscript_dir(book.source_language) / "meta.yaml"]
    if kind == "voice":
        return [book.manuscript_dir(book.source_language) / f"{subject}.md"]
    if kind == "freeze":
        return sorted(book.manuscript_dir(subject).glob("*")) + [root / BOOK_FILENAME]
    if kind == "publish":
        return sorted(p for p in (root / "builds" / subject).rglob("*") if p.suffix in (".pdf", ".epub"))
    if kind == "material":
        return sorted((root / "archive").rglob("*")) if (root / "archive").is_dir() else []
    raise NotFoundError(f"Unknown gate kind {kind!r}", kinds=sorted(KINDS))


def subject_digest(book: Book, kind: str, subject: str = "") -> str:
    files = [p for p in _files(book, kind, subject) if p.is_file()]
    if not files:
        raise ValidationError(f"Nothing to judge for the {kind} gate", subject=subject)
    hasher = hashlib.sha256()
    for path in files:
        hasher.update(str(path.relative_to(book.root)).encode())
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def open_gate(book: Book, kind: str, subject: str = "", *, actor: Actor, note: str = "") -> dict[str, Any]:
    gate_kind = KINDS.get(kind)
    if gate_kind is None:
        raise NotFoundError(f"Unknown gate kind {kind!r}", kinds=sorted(KINDS))
    if gate_kind.needs_subject and not subject:
        raise ValidationError(f"The {kind} gate needs a subject")
    with book_lock(book.root):
        state = read_state(book.root)
        waiting = [g for g in state["gates"].values()
                   if g["kind"] == kind and g["subject"] == subject and g["state"] == "waiting"]
        if waiting:
            return waiting[0]
        gate = {
            "id": f"{kind}-{uuid.uuid4().hex[:8]}",
            "kind": kind,
            "subject": subject,
            "question": gate_kind.question,
            "state": "waiting",
            "digest": subject_digest(book, kind, subject),
            "requested_at": now(),
            "requested_by": actor.public_dict(),
            "note": note,
        }
        state["gates"][gate["id"]] = gate
        state["history"].append({"at": gate["requested_at"], "event": "gate_opened", "gate": gate["id"],
                                 "actor": actor.public_dict()})
        commit_state(book.root, state, expected_revision=state["revision"],
                     message=f"Open gate {gate['id']}: {gate_kind.question}", actor=actor)
        return gate


def decide_gate(book: Book, gate_id: str, decision: str, *, actor: Actor, rationale: str = "",
                expected_revision: int | None = None) -> dict[str, Any]:
    if decision not in DECISIONS:
        raise ValidationError(f"Unknown decision {decision!r}", allowed=sorted(DECISIONS))
    if actor.kind != "human":
        raise ValidationError("Only a person decides a gate; an agent may prepare the decision")
    if decision != "approved" and not rationale.strip():
        raise ValidationError("Asking for changes or rejecting needs a rationale: it is what the next version fixes")
    with book_lock(book.root):
        state = read_state(book.root)
        gate = state["gates"].get(gate_id)
        if gate is None:
            raise NotFoundError(f"No gate {gate_id!r}")
        if gate["state"] != "waiting":
            raise ValidationError(f"Gate {gate_id} was already decided ({gate['state']}); open a new one")
        current = subject_digest(book, gate["kind"], gate["subject"])
        if current != gate["digest"]:
            raise ValidationError("The files changed after the gate was opened; open a new gate for this version",
                                  gate=gate_id)
        gate.update({"state": decision, "decided_at": now(), "decided_by": actor.public_dict(),
                     "rationale": rationale})
        state["history"].append({"at": gate["decided_at"], "event": "gate_decided", "gate": gate_id,
                                 "decision": decision, "actor": actor.public_dict(), "rationale": rationale})
        commit_state(book.root, state, expected_revision=expected_revision,
                     message=f"Gate {gate_id}: {decision}" + (f" — {rationale}" if rationale else ""), actor=actor)
        return gate


def gate_status(book: Book) -> list[dict[str, Any]]:
    """Every gate, with whether its files changed since it was opened or decided."""

    out = []
    for gate in read_state(book.root)["gates"].values():
        try:
            changed = subject_digest(book, gate["kind"], gate["subject"]) != gate["digest"]
        except ValidationError:
            changed = True
        out.append({**gate, "changed_since": changed})
    return sorted(out, key=lambda g: g["requested_at"])

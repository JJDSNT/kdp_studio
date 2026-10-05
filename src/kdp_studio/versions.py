"""Text versions (ADR 0006): candidates beside the text, adopted by a person.

A rewrite proposed by an agent (or by a person, for later) is a *candidate*:
it never touches the section. It is stored in the book with the text it was
based on, the task it answered and its declared scope. The author reads it
against the current text -- word by word, with the fidelity report -- and
adopts it or rejects it with a reason. Nothing is discarded: rejected
candidates stay, with why.

A person's own edit is written byte for byte, and refused if the file changed
since it was opened.
"""

from __future__ import annotations

import difflib
import re
import uuid
from pathlib import Path
from typing import Any

from .book import Book
from .errors import NotFoundError, ValidationError
from .fidelity import compare, digest
from .history import log
from .state import Actor, book_lock, commit_state, now, read_state

#: What a version may change. A change of facts under `wording` is a
#: violation even when the new fact is right (docs/origin, §5.19).
SCOPES = {
    "wording": "register, voice and phrasing; no number, date, name, URL or code may change",
    "content": "what the section says; facts may change, each one is listed",
    "structure": "order and division of the text",
}


def section_path(book: Book, language: str, section_id: str) -> Path:
    path = book.manuscript_dir(language) / f"{section_id}.md"
    if not path.is_file():
        raise NotFoundError(f"No section {section_id!r} in {language}")
    return path


def read_section(book: Book, language: str, section_id: str) -> dict[str, Any]:
    path = section_path(book, language, section_id)
    raw = path.read_bytes()
    return {"language": language, "section": section_id, "text": raw.decode("utf-8"), "digest": digest(raw),
            "history": log(book.root, path)}


def save_section(book: Book, language: str, section_id: str, text: str, *, expected_digest: str,
                 actor: Actor, reason: str = "") -> dict[str, Any]:
    """A person's edit, written exactly as they wrote it."""

    if actor.kind != "human":
        raise ValidationError("An agent proposes a version; only a person edits the text directly")
    path = section_path(book, language, section_id)
    with book_lock(book.root):
        current = digest(path.read_bytes())
        if current != expected_digest:
            raise ValidationError("The section changed since it was opened; reload it before saving",
                                  reason="stale_section")
        raw = text.encode("utf-8")
        if digest(raw) == current:
            return {"changed": False, "digest": current}
        path.write_bytes(raw)
        state = read_state(book.root)
        state["history"].append({"at": now(), "event": "section_edited", "language": language,
                                 "section": section_id, "before": current, "after": digest(raw),
                                 "actor": actor.public_dict(), "reason": reason})
        commit_state(book.root, state, expected_revision=None, also=(path,), actor=actor,
                     message=f"Edit {section_id} ({language})" + (f": {reason}" if reason else ""))
        return {"changed": True, "digest": digest(raw)}


def _version_dir(book: Book, language: str, section_id: str) -> Path:
    return book.root / "versions" / language / section_id


def propose_version(book: Book, language: str, section_id: str, text: str, *, actor: Actor, scope: str,
                    rationale: str, task: str = "") -> dict[str, Any]:
    if scope not in SCOPES:
        raise ValidationError(f"Unknown scope {scope!r}", allowed=sorted(SCOPES))
    if not rationale.strip():
        raise ValidationError("A version says why it exists")
    path = section_path(book, language, section_id)
    base = path.read_bytes()
    if digest(text.encode("utf-8")) == digest(base):
        raise ValidationError("The proposed text is identical to the current one")
    version_id = f"v-{uuid.uuid4().hex[:8]}"
    folder = _version_dir(book, language, section_id)
    with book_lock(book.root):
        folder.mkdir(parents=True, exist_ok=True)
        candidate, base_copy = folder / f"{version_id}.md", folder / f"{version_id}.base.md"
        candidate.write_bytes(text.encode("utf-8"))
        base_copy.write_bytes(base)
        state = read_state(book.root)
        entry = {
            "id": version_id, "language": language, "section": section_id, "state": "candidate",
            "scope": scope, "rationale": rationale, "task": task, "base_digest": digest(base),
            "digest": digest(text.encode("utf-8")), "proposed_at": now(), "proposed_by": actor.public_dict(),
        }
        state.setdefault("versions", {})[version_id] = entry
        state["history"].append({"at": entry["proposed_at"], "event": "version_proposed", "version": version_id,
                                 "section": section_id, "actor": actor.public_dict()})
        commit_state(book.root, state, expected_revision=None, also=(candidate, base_copy), actor=actor,
                     message=f"Propose {version_id} of {section_id} ({language}, {scope}): {rationale}")
        return entry


def _tokens(text: str) -> list[str]:
    return re.findall(r"\s+|\w+|[^\w\s]", text)


def word_diff(before: str, after: str) -> list[dict[str, str]]:
    """Segments for display: equal, delete, insert, at the granularity of words."""

    a, b = _tokens(before), _tokens(after)
    segments: list[dict[str, str]] = []
    for tag, a0, a1, b0, b1 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            segments.append({"op": "equal", "text": "".join(a[a0:a1])})
            continue
        if a1 > a0:
            segments.append({"op": "delete", "text": "".join(a[a0:a1])})
        if b1 > b0:
            segments.append({"op": "insert", "text": "".join(b[b0:b1])})
    return segments


def version_report(book: Book, version_id: str) -> dict[str, Any]:
    entry = read_state(book.root).get("versions", {}).get(version_id)
    if entry is None:
        raise NotFoundError(f"No version {version_id!r}")
    folder = _version_dir(book, entry["language"], entry["section"])
    base = (folder / f"{version_id}.base.md").read_text("utf-8")
    text = (folder / f"{version_id}.md").read_text("utf-8")
    fidelity = compare(base, text)
    violations = []
    if entry["scope"] == "wording" and (fidelity.facts_added or fidelity.facts_removed):
        violations.append("Facts changed under a wording-only scope")
    current = digest(section_path(book, entry["language"], entry["section"]).read_bytes())
    return {
        **entry,
        "base_is_current": current == entry["base_digest"],
        "diff": word_diff(base, text),
        "fidelity": fidelity.public_dict(),
        "violations": violations,
        "text": text,
    }


def list_versions(book: Book, language: str | None = None, section_id: str | None = None) -> list[dict[str, Any]]:
    out = []
    for entry in read_state(book.root).get("versions", {}).values():
        if (language and entry["language"] != language) or (section_id and entry["section"] != section_id):
            continue
        out.append(entry)
    return sorted(out, key=lambda e: e["proposed_at"], reverse=True)


def _decide(book: Book, version_id: str, decision: str, actor: Actor, rationale: str) -> dict[str, Any]:
    if actor.kind != "human":
        raise ValidationError("Only a person adopts or rejects a version; an agent proposes")
    if decision == "rejected" and not rationale.strip():
        raise ValidationError("Rejecting a version needs a reason: it is what the next one fixes")
    with book_lock(book.root):
        state = read_state(book.root)
        entry = state.get("versions", {}).get(version_id)
        if entry is None:
            raise NotFoundError(f"No version {version_id!r}")
        if entry["state"] != "candidate":
            raise ValidationError(f"Version {version_id} was already {entry['state']}")
        also: tuple[Path, ...] = ()
        if decision == "adopted":
            path = section_path(book, entry["language"], entry["section"])
            if digest(path.read_bytes()) != entry["base_digest"]:
                raise ValidationError(
                    "The section changed since this version was proposed; it no longer applies cleanly",
                    reason="stale_base")
            folder = _version_dir(book, entry["language"], entry["section"])
            path.write_bytes((folder / f"{version_id}.md").read_bytes())
            also = (path,)
        entry.update({"state": decision, "decided_at": now(), "decided_by": actor.public_dict(),
                      "decision_rationale": rationale})
        state["history"].append({"at": entry["decided_at"], "event": f"version_{decision}", "version": version_id,
                                 "section": entry["section"], "actor": actor.public_dict(), "rationale": rationale})
        verb = "Adopt" if decision == "adopted" else "Reject"
        by = entry["proposed_by"]["id"]
        commit_state(book.root, state, expected_revision=None, also=also, actor=actor,
                     message=f"{verb} {version_id} of {entry['section']} ({entry['scope']}, proposed by {by})"
                     + (f": {rationale}" if rationale else f": {entry['rationale']}"))
        return entry


def adopt_version(book: Book, version_id: str, *, actor: Actor, rationale: str = "") -> dict[str, Any]:
    return _decide(book, version_id, "adopted", actor, rationale)


def reject_version(book: Book, version_id: str, *, actor: Actor, rationale: str) -> dict[str, Any]:
    return _decide(book, version_id, "rejected", actor, rationale)

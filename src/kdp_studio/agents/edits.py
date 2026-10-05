"""What every text-changing agent shares (ADR 0009).

An agent answers with edits -- an exact passage, its replacement, why --
and KDP Studio applies them, refusing any that is ambiguous, overlapping, or
touches what must never change. The result is recorded as a candidate
version with the task, audited for fidelity.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any

from ..book import Book, split_frontmatter
from ..errors import ValidationError
from ..markdown import callout, parse
from ..state import Actor
from ..versions import propose_version, read_section, version_report

EDITS_SCHEMA = {
    "type": "object",
    "properties": {
        "edits": {"type": "array", "items": {"type": "object", "properties": {
            "find": {"type": "string"}, "replace": {"type": "string"},
            "practice": {"type": "string"}, "why": {"type": "string"}},
            "required": ["find", "replace", "practice", "why"]}},
        "skipped": {"type": "array", "items": {"type": "object", "properties": {
            "excerpt": {"type": "string"}, "why": {"type": "string"}}, "required": ["excerpt", "why"]}},
        "summary": {"type": "string"},
    },
    "required": ["edits", "skipped", "summary"],
}

EDITS_RULES = (
    "Answer with edits: `find` is an exact passage copied from the section, long enough to occur once; "
    "`replace` is what it becomes; `practice` names what the edit serves; `why` says why in one sentence. "
    "Keep each edit as small as the change allows; several small edits beat one large one. To move a "
    "paragraph, delete it with one edit (replace with an empty string) and insert it with another (replace "
    "the passage it should follow with that passage plus the paragraph). Never touch the frontmatter, a "
    "prompt block (`> [!prompt] …`), or code: those edits are refused. What you decide not to change, put "
    "in `skipped` with why. Write in the book's language and voice."
)


def protected_spans(text: str) -> list[tuple[int, int]]:
    """Character spans an edit may not touch: frontmatter, prompts, code."""

    lines = text.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    spans = []
    frontmatter = re.match(r"\A---\n.*?\n---\n?", text, re.S)
    offset_lines = 0
    if frontmatter:
        spans.append((0, frontmatter.end()))
        offset_lines = text[:frontmatter.end()].count("\n")
    body = text[frontmatter.end():] if frontmatter else text
    for node in parse(body).walk():
        is_prompt = node.type == "blockquote" and (found := callout(node)) is not None and found.kind == "prompt"
        if (node.type in ("fence", "code_block") or is_prompt) and node.map:
            first, last = node.map[0] + offset_lines, node.map[1] + offset_lines
            spans.append((starts[min(first, len(starts) - 1)], starts[min(last, len(starts) - 1)]))
    return spans


def apply_edits(text: str, edits: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    spans = protected_spans(text)
    applied, refused, planned = [], [], []
    for edit in edits:
        find = edit.get("find", "")
        count = text.count(find) if find else 0
        if count != 1:
            refused.append({**edit, "reason": "passage not found" if not count else f"passage found {count} times"})
            continue
        start = text.index(find)
        end = start + len(find)
        if any(start < b and end > a for a, b in spans):
            refused.append({**edit, "reason": "touches a prompt, code or the frontmatter"})
            continue
        if any(start < e and end > s for s, e, _ in planned):
            refused.append({**edit, "reason": "overlaps another edit"})
            continue
        planned.append((start, end, edit))
    for start, end, edit in sorted(planned, key=lambda p: p[0], reverse=True):
        text = text[:start] + edit["replace"] + text[end:]
        applied.append(edit)
    return text, list(reversed(applied)), refused


def book_context(book: Book, settings: dict[str, Any]) -> str:
    """The intention and the voice guide: book-level, shared by every agent."""

    parts = []
    intention = book.root / "intentions.md"
    if intention.is_file():
        parts.append(f"[intentions.md — wins every conflict]\n{intention.read_text('utf-8')}")
    for relative in settings.get("guide") or []:
        path = (book.root / relative).resolve()
        if book.root.resolve() in path.parents and path.is_file():
            parts.append(f"[{relative} — the book's voice]\n{path.read_text('utf-8')}")
    pilot = approved_voice(book)
    if pilot:
        parts.append(f"[{pilot['section']} — the pilot chapter whose voice the author approved for the whole book "
                     f"on {pilot['decided_at'][:10]}; every chapter is written in this voice]\n{pilot['text']}")
    return "\n\n".join(parts) or "(the book declares no intention or voice guide)"


def approved_voice(book: Book) -> dict[str, Any] | None:
    """The pilot chapter of the latest approved voice gate, if the voice was chosen on one.

    Once chosen, the voice belongs to the whole book: every agent reads this
    chapter as the reference, whatever chapter it works on.
    """

    from ..gates import gate_status

    approved = [g for g in gate_status(book) if g["kind"] == "voice" and g["state"] == "approved" and g["subject"]]
    if not approved:
        return None
    gate = max(approved, key=lambda g: g.get("decided_at", ""))
    path = book.manuscript_dir(book.source_language) / f"{gate['subject']}.md"
    if not path.is_file():
        return None
    return {"section": gate["subject"], "decided_at": gate.get("decided_at", ""), "text": path.read_text("utf-8"),
            "changed_since": gate["changed_since"]}


def clean(answer: dict[str, Any]) -> dict[str, Any]:
    # Some answers arrive with JSON escapes left inside the prose.
    answer["summary"] = str(answer.get("summary", "")).replace('\\"', '"')
    return answer


def record(book: Book, language: str, section: str, answer: dict[str, Any], *, agent: Actor, scope: str,
           rationale: str, task: dict[str, Any]) -> dict[str, Any]:
    """Apply the edits to the current text and record a candidate version."""

    current = read_section(book, language, section)
    revised, applied, refused = apply_edits(current["text"], answer.get("edits") or [])
    outcome: dict[str, Any] = {"applied": len(applied), "refused": refused, "skipped": answer.get("skipped") or [],
                               "summary": answer.get("summary", "")}
    if not applied:
        return {**outcome, "version": None}
    payload = json.dumps({**task, "applied": applied, "refused": refused, "skipped": outcome["skipped"]},
                         ensure_ascii=False)
    try:
        version = propose_version(book, language, section, revised, actor=agent, scope=scope,
                                  rationale=rationale + (" " + outcome["summary"] if outcome["summary"] else ""),
                                  task=payload)
    except ValidationError as error:
        return {**outcome, "version": None, "summary": error.message}
    audit = version_report(book, version["id"])
    original = next(s for s in book.sections(language) if s.id == section)
    candidate = replace(original, body=split_frontmatter(revised)[1], path=original.path.with_suffix(".candidate"))
    return {**outcome, "version": version["id"], "violations": audit["violations"], "candidate": candidate}

"""The voice reviser (docs/origin, §5.6): register and form, nothing else.

It reads one section with the style findings the checks produced and the
book's voice guide, and answers with *edits*: an exact passage and its
replacement, each tied to the practice it fixes. KDP Studio applies them
itself, so everything outside the edits stays byte for byte -- the scope is
enforced by construction, not by trusting the model. An edit is refused when
its passage is not found exactly once, or when it touches what must never
change: the frontmatter, a prompt to an agent, code.

The result is a candidate version (scope `wording`), audited for fidelity: a
changed number, date, name or URL shows as a violation even if it is right.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any

from ..book import Book, split_frontmatter
from ..errors import ValidationError
from ..jobs import Progress, kind
from ..markdown import callout, parse
from ..model import Model, model_from_env
from ..state import Actor
from ..style import catalogue, check_sections, check_style
from ..versions import propose_version, read_section, version_report

AGENT = Actor("voice-reviser", "agent")
CATEGORIES = {"register", "form", "vocabulary"}

SYSTEM = (
    "You are the voice reviser of a book. You fix register and form only: the findings listed, and nothing "
    "else. You never change meaning, facts, numbers, dates, names, URLs, quotations or the order of ideas. "
    "Answer with edits: `find` is an exact passage copied from the section (long enough to occur once), "
    "`replace` is the same passage rewritten, `practice` is the finding's practice id. Keep each edit as "
    "small as the fix allows. If a finding should not be changed (the form is right in context), leave it "
    "and say why in `skipped`. Write in the book's language, as the voice guide asks."
)

SCHEMA = {
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
        protected = node.type in ("fence", "code_block") or (node.type == "blockquote" and (found := callout(node))
                                                             and found.kind == "prompt")
        if protected and node.map:
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


def _guide(book: Book, settings: dict[str, Any]) -> str:
    texts = []
    for relative in settings.get("guide") or []:
        path = (book.root / relative).resolve()
        if book.root.resolve() in path.parents and path.is_file():
            texts.append(f"[{relative}]\n{path.read_text('utf-8')}")
    return "\n\n".join(texts) or "(the book declares no voice guide; follow the findings)"


def revise(book: Book, language: str, section: str, *, model: Model | None = None,
           progress=lambda message: None) -> dict[str, Any]:
    practices, settings = catalogue(book, language)
    categories = {p.id: p.category for p in practices}
    progress("Checking the section against the catalogue")
    report = check_style(book, language, [section])
    findings = [f for f in report.findings
                if categories.get(f.practice) in CATEGORIES
                or (f.practice.startswith("lt:") and "MORFOLOGIK" not in f.practice)]
    if not findings:
        return {"version": None, "summary": "No register or form finding in this section: nothing to revise."}
    current = read_section(book, language, section)
    listed = "\n".join(f"- [{f.practice}] line {f.line}: “{f.match}” in “{f.excerpt}”"
                       + (f" ({f.message})" if f.message else "") for f in findings)
    rules = "\n".join(f"- {p.id}: {p.rule}" for p in practices if p.id in {f.practice for f in findings})
    prompt = (f"Voice guide:\n{_guide(book, settings)}\n\nPractices involved:\n{rules}\n\n"
              f"Findings ({len(findings)}):\n{listed}\n\nThe section ({language}, {section}):\n\n{current['text']}")
    progress(f"Asking the model to fix {len(findings)} finding(s)")
    answer = (model or model_from_env()).ask(SYSTEM, prompt, SCHEMA)
    # Some answers arrive with JSON escapes left inside the prose.
    answer["summary"] = str(answer.get("summary", "")).replace('\\"', '"')
    revised, applied, refused = apply_edits(current["text"], answer.get("edits") or [])
    if not applied:
        return {"version": None, "summary": answer.get("summary", ""), "refused": refused,
                "skipped": answer.get("skipped") or []}
    progress(f"Applied {len(applied)} edit(s); recording a candidate version")
    task = json.dumps({"agent": "voice-reviser", "findings": len(findings), "applied": applied,
                       "refused": refused, "skipped": answer.get("skipped") or []}, ensure_ascii=False)
    try:
        version = propose_version(book, language, section, revised, actor=AGENT, scope="wording",
                                  rationale=f"Voice review: {len(applied)} fix(es) of register and form. "
                                  + answer.get("summary", ""), task=task)
    except ValidationError as error:
        return {"version": None, "summary": error.message}
    audit = version_report(book, version["id"])
    original = next(s for s in book.sections(language) if s.id == section)
    candidate = replace(original, body=split_frontmatter(revised)[1], path=original.path.with_suffix(".candidate"))
    remaining = [f for f in check_sections(book, language, [candidate], engines=False).findings
                 if categories.get(f.practice) in CATEGORIES]
    return {"version": version["id"], "applied": len(applied), "refused": refused,
            "skipped": answer.get("skipped") or [], "violations": audit["violations"],
            "findings_before": len(findings), "remaining_in_candidate": len(remaining),
            "summary": answer.get("summary", "")}


@kind("revise_voice", "Voice reviser: fix register and form findings of a section as a candidate version")
def revise_voice_job(book: Book, payload: dict[str, Any], actor: Actor, progress: Progress) -> dict[str, Any]:
    return revise(book, payload.get("language") or book.source_language, payload["section"], progress=progress)

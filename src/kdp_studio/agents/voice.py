"""The voice reviser (docs/origin, §5.6): register and form, nothing else.

It reads one section with the style findings the checks produced and the
book's voice -- intention and guide, decided once for the whole book -- and
answers with edits (agents/edits.py). The result is a candidate version
(scope `wording`), audited for fidelity: a changed number, date, name or URL
shows as a violation even if it is right.
"""

from __future__ import annotations

from typing import Any

from ..book import Book
from ..jobs import Progress, kind
from ..model import Model, model_from_env
from ..state import Actor
from ..style import catalogue, check_sections, check_style
from ..versions import read_section
from .edits import EDITS_RULES, EDITS_SCHEMA, apply_edits, book_context, clean, protected_spans, record

__all__ = ["apply_edits", "protected_spans", "revise"]

AGENT = Actor("voice-reviser", "agent")
CATEGORIES = {"register", "form", "vocabulary"}

SYSTEM = (
    "You are the voice reviser of a book. You fix register and form only: the findings listed, and nothing "
    "else. You never change meaning, facts, numbers, dates, names, URLs, quotations or the order of ideas. "
    "If a finding should not be changed (the form is right in context), skip it. " + EDITS_RULES
)


def revise(book: Book, language: str, section: str, *, model: Model | None = None,
           progress=lambda message: None) -> dict[str, Any]:
    practices, settings = catalogue(book, language)
    categories = {p.id: p.category for p in practices}
    progress("Checking the section against the catalogue")
    findings = [f for f in check_style(book, language, [section]).findings
                if categories.get(f.practice) in CATEGORIES
                or (f.practice.startswith("lt:") and "MORFOLOGIK" not in f.practice)]
    if not findings:
        return {"version": None, "summary": "No register or form finding in this section: nothing to revise."}
    current = read_section(book, language, section)
    listed = "\n".join(f"- [{f.practice}] line {f.line}: “{f.match}” in “{f.excerpt}”"
                       + (f" ({f.message})" if f.message else "") for f in findings)
    rules = "\n".join(f"- {p.id}: {p.rule}" for p in practices if p.id in {f.practice for f in findings})
    prompt = (f"The book:\n{book_context(book, settings)}\n\nPractices involved:\n{rules}\n\n"
              f"Findings ({len(findings)}):\n{listed}\n\nThe section ({language}, {section}):\n\n{current['text']}")
    progress(f"Asking the model to fix {len(findings)} finding(s)")
    answer = clean((model or model_from_env()).ask(SYSTEM, prompt, EDITS_SCHEMA))
    result = record(book, language, section, answer, agent=AGENT, scope="wording",
                    rationale=f"Voice review: {len(answer.get('edits') or [])} fix(es) of register and form.",
                    task={"agent": "voice-reviser", "findings": len(findings)})
    candidate = result.pop("candidate", None)
    if candidate is not None:
        progress(f"Applied {result['applied']} edit(s); recorded a candidate version")
        remaining = [f for f in check_sections(book, language, [candidate], engines=False).findings
                     if categories.get(f.practice) in CATEGORIES]
        result["remaining_in_candidate"] = len(remaining)
    result["findings_before"] = len(findings)
    return result


@kind("revise_voice", "Voice reviser: fix register and form findings of a section as a candidate version")
def revise_voice_job(book: Book, payload: dict[str, Any], actor: Actor, progress: Progress) -> dict[str, Any]:
    return revise(book, payload.get("language") or book.source_language, payload["section"], progress=progress)

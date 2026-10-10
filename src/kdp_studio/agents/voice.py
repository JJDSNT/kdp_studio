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
from ..jobs import flow_kind
from ..model import Model, model_from_env
from ..state import Actor
from ..style import catalogue, check_sections, check_style
from ..versions import read_section
from .edits import (EDITS_RULES, EDITS_SCHEMA, apply_edits, book_context, clean, edit_checks, protected_spans,
                    record, version_text)
from .flow import SimpleWork, again, review_work, run_work

__all__ = ["apply_edits", "protected_spans", "revise"]

AGENT = Actor("voice-reviser", "agent")
CATEGORIES = {"register", "form", "vocabulary"}

SYSTEM = (
    "You are the voice reviser of a book. You fix register and form only: the findings listed, and nothing "
    "else. You never change meaning, facts, numbers, dates, names, URLs, quotations or the order of ideas. "
    "If a finding should not be changed (the form is right in context), skip it. " + EDITS_RULES
)


NOTHING = "No register or form finding in this section: nothing to revise."


def _work(book: Book, language: str, section: str, *, model: Model | None = None,
          reviewer: Model | None = None) -> SimpleWork:
    practices, settings = catalogue(book, language)
    categories = {p.id: p.category for p in practices}
    findings = [f for f in check_style(book, language, [section]).findings
                if categories.get(f.practice) in CATEGORIES
                or (f.practice.startswith("lt:") and "MORFOLOGIK" not in f.practice)]
    current = read_section(book, language, section)
    listed = "\n".join(f"- [{f.practice}] line {f.line}: “{f.match}” in “{f.excerpt}”"
                       + (f" ({f.message})" if f.message else "") for f in findings)
    rules = "\n".join(f"- {p.id}: {p.rule}" for p in practices if p.id in {f.practice for f in findings})
    prompt = (f"The book:\n{book_context(book, settings)}\n\nPractices involved:\n{rules}\n\n"
              f"Findings ({len(findings)}):\n{listed}\n\nThe section ({language}, {section}):\n\n{current['text']}")
    chosen = model

    def ask(request: str, standing: dict[str, Any] | None, error: str) -> dict[str, Any]:
        if not findings and not request:  # the checks found nothing: there is nothing to ask a model
            return {"edits": [], "skipped": [], "summary": NOTHING}
        return clean((chosen or model_from_env()).ask(SYSTEM, again(prompt, request, standing, error), EDITS_SCHEMA))

    def land(answer: dict[str, Any]) -> dict[str, Any]:
        if not findings and not answer.get("edits"):
            return {"version": None, "summary": NOTHING, "section": section, "language": language}
        result = record(book, language, section, answer, agent=AGENT, scope="wording",
                        rationale=f"Voice review: {len(answer.get('edits') or [])} fix(es) of register and form.",
                        task={"agent": "voice-reviser", "findings": len(findings)})
        candidate = result.pop("candidate", None)
        if candidate is not None:
            remaining = [f for f in check_sections(book, language, [candidate], engines=False).findings
                         if categories.get(f.practice) in CATEGORIES]
            result["remaining_in_candidate"] = len(remaining)
        return {**result, "findings_before": len(findings), "section": section, "language": language}

    def review(outcome: dict[str, Any]) -> dict[str, Any]:
        return review_work(reviewer or chosen or model_from_env(), title="Voice reviser",
                           role="Fixes register and form only, the findings listed; never meaning or facts.",
                           shown=prompt, answered=version_text(book, language, section, outcome.get("version")))

    return SimpleWork(f"Voice reviser: {section}", ask=ask, land=land, review=review,
                      checks=edit_checks(book, language, section, "wording"))


def revise(book: Book, language: str, section: str, *, model: Model | None = None,
           progress=lambda message: None) -> dict[str, Any]:
    result = run_work(_work(book, language, section, model=model), progress=progress)
    if result.get("summary") == NOTHING:
        return {"version": None, "summary": NOTHING}
    return result


@flow_kind("revise_voice", "Voice reviser: fix register and form findings of a section as a candidate version")
def revise_voice_flow(book: Book, payload: dict[str, Any], progress) -> tuple[Any, dict[str, Any], list]:
    return _work(book, payload.get("language") or book.source_language, payload["section"]), {}, []

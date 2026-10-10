"""The reviser: a chapter changed as the author asks, in words.

"Tighten the opening", "move the example to the end", "explain the term
before using it": the author's instruction, a declared scope, and the book's
intention and voice as context. The reviser answers with edits
(agents/edits.py) and the result is a candidate version the author compares
and adopts -- or asks again with a better instruction.
"""

from __future__ import annotations

from typing import Any

from ..book import Book
from ..errors import ValidationError
from ..jobs import flow_kind
from ..model import Model, model_from_env
from ..state import Actor
from ..style import catalogue
from ..versions import SCOPES, read_section
from .edits import EDITS_RULES, EDITS_SCHEMA, book_context, clean, edit_checks, record, version_text
from .flow import SimpleWork, again, review_work, run_work

AGENT = Actor("reviser", "agent")

SYSTEM = (
    "You are the reviser of a book. You change one section exactly as the author's instruction asks, and "
    "nothing more: the declared scope is a promise. Under `wording` you change phrasing only — never a number, "
    "date, name, URL or quotation. Under `content` you may change what the section says; under `structure`, "
    "the order and division of its text. The book's intention wins every conflict: if the instruction would "
    "work against it, do the closest thing that does not and say so in the summary. " + EDITS_RULES
)


def _work(book: Book, language: str, section: str, instruction: str, scope: str, *, model: Model | None = None,
          reviewer: Model | None = None) -> SimpleWork:
    if scope not in SCOPES:
        raise ValidationError(f"Unknown scope {scope!r}", allowed=sorted(SCOPES))
    if not instruction.strip():
        raise ValidationError("The reviser needs an instruction")
    _, settings = catalogue(book, language)
    current = read_section(book, language, section)
    prompt = (f"The book:\n{book_context(book, settings)}\n\nScope: {scope} — {SCOPES[scope]}\n\n"
              f"The author's instruction:\n{instruction}\n\nThe section ({language}, {section}):\n\n{current['text']}")
    chosen = model or model_from_env()

    def ask(request: str, standing: dict[str, Any] | None, error: str) -> dict[str, Any]:
        return clean(chosen.ask(SYSTEM, again(prompt, request, standing, error), EDITS_SCHEMA))

    def land(answer: dict[str, Any]) -> dict[str, Any]:
        result = record(book, language, section, answer, agent=AGENT, scope=scope, rationale=instruction.strip(),
                        task={"agent": "reviser", "instruction": instruction})
        result.pop("candidate", None)
        return {**result, "section": section, "language": language}

    def review(outcome: dict[str, Any]) -> dict[str, Any]:
        return review_work(reviewer or chosen, title="Reviser",
                           role=f"Changes one section exactly as the author's instruction asks, under the scope {scope}.",
                           shown=prompt, answered=version_text(book, language, section, outcome.get("version")))

    return SimpleWork(f"Reviser: {section}", ask=ask, land=land, review=review,
                      checks=edit_checks(book, language, section, scope))


def revise_section(book: Book, language: str, section: str, instruction: str, scope: str, *,
                   model: Model | None = None, progress=lambda message: None) -> dict[str, Any]:
    return run_work(_work(book, language, section, instruction, scope, model=model), progress=progress)


@flow_kind("revise_section", "Reviser: change a section as the author's instruction asks, as a candidate version")
def revise_section_flow(book: Book, payload: dict[str, Any], progress) -> tuple[Any, dict[str, Any], list]:
    return _work(book, payload.get("language") or book.source_language, payload["section"],
                 payload.get("instruction", ""), payload.get("scope", "content")), {}, []

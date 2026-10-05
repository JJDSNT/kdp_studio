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
from ..jobs import Progress, kind
from ..model import Model, model_from_env
from ..state import Actor
from ..style import catalogue
from ..versions import SCOPES, read_section
from .edits import EDITS_RULES, EDITS_SCHEMA, book_context, clean, record

AGENT = Actor("reviser", "agent")

SYSTEM = (
    "You are the reviser of a book. You change one section exactly as the author's instruction asks, and "
    "nothing more: the declared scope is a promise. Under `wording` you change phrasing only — never a number, "
    "date, name, URL or quotation. Under `content` you may change what the section says; under `structure`, "
    "the order and division of its text. The book's intention wins every conflict: if the instruction would "
    "work against it, do the closest thing that does not and say so in the summary. " + EDITS_RULES
)


def revise_section(book: Book, language: str, section: str, instruction: str, scope: str, *,
                   model: Model | None = None, progress=lambda message: None) -> dict[str, Any]:
    if scope not in SCOPES:
        raise ValidationError(f"Unknown scope {scope!r}", allowed=sorted(SCOPES))
    if not instruction.strip():
        raise ValidationError("The reviser needs an instruction")
    _, settings = catalogue(book, language)
    current = read_section(book, language, section)
    prompt = (f"The book:\n{book_context(book, settings)}\n\nScope: {scope} — {SCOPES[scope]}\n\n"
              f"The author's instruction:\n{instruction}\n\nThe section ({language}, {section}):\n\n{current['text']}")
    progress("Asking the model for edits")
    answer = clean((model or model_from_env()).ask(SYSTEM, prompt, EDITS_SCHEMA))
    result = record(book, language, section, answer, agent=AGENT, scope=scope, rationale=instruction.strip(),
                    task={"agent": "reviser", "instruction": instruction})
    result.pop("candidate", None)
    if result.get("version"):
        progress(f"Applied {result['applied']} edit(s); recorded a candidate version")
    return result


@kind("revise_section", "Reviser: change a section as the author's instruction asks, as a candidate version")
def revise_section_job(book: Book, payload: dict[str, Any], actor: Actor, progress: Progress) -> dict[str, Any]:
    return revise_section(book, payload.get("language") or book.source_language, payload["section"],
                          payload.get("instruction", ""), payload.get("scope", "content"), progress=progress)

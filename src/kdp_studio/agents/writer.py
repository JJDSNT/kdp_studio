"""The writer (docs/origin, §5.5): a chapter written to its promise.

It writes one section's body from its plan (synopsis and promise in the
frontmatter), the plan of the whole book (so it does not take what belongs to
another chapter), the end of the previous chapter (for the transition), the
research dossiers the section names, the book's intention and voice, and the
writing vices to avoid. The frontmatter is kept byte for byte; the body is a
candidate version (scope `content`) the author reads, adopts, or sends back
with an instruction.
"""

from __future__ import annotations

from typing import Any

from ..book import Book, split_frontmatter
from ..errors import NotFoundError
from ..jobs import flow_kind
from ..model import Model, model_from_env
from ..state import Actor
from ..style import catalogue, check_sections
from ..versions import propose_version, read_section, version_report
from .edits import book_context, version_text
from .flow import SimpleWork, again, review_work, run_work

AGENT = Actor("writer", "agent")

FORMAT = (
    "The manuscript format: Markdown; sections inside the chapter start at `##`; no chapter heading (the title "
    "is in the frontmatter). Callouts: `> [!concept] Title` (also warning, practice, challenge, note, framework). "
    "A hands-on block: `::: exercise Title` … `:::`, with `#### ` sub-labels inside. A prompt for the reader to "
    "give an agent: `> [!prompt] EX-NN-NN` followed by a blank `>` line and the prompt. Editorial notes the "
    "reader must not see go in HTML comments."
)

SYSTEM = (
    "You are the writer of a book. Write the body of ONE chapter so that it keeps its promise: the reader "
    "finishes able to do what the promise says. Stay inside this chapter's synopsis; what the plan gives to "
    "another chapter is not yours to use, and an example that belongs to another part must not leak here. "
    "Demonstrate the book's thesis in a new situation instead of restating it. Use only what the research and "
    "the intention support; never invent sources, quotations, numbers or URLs — where a fact is missing, leave "
    "an HTML comment saying what must be checked. Write in the book's language and voice. "
)

SCHEMA = {
    "type": "object",
    "properties": {
        "body": {"type": "string"},
        "notes": {"type": "string"},
        "to_check": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["body", "notes", "to_check"],
}


def _plan(book: Book, current: str) -> str:
    lines = []
    for section in book.sections(book.source_language):
        mark = "  ← THIS CHAPTER" if section.id == current else ""
        number = f"{section.number}. " if section.number else ""
        lines.append(f"- {number}{section.title}{mark}\n  covers: {section.synopsis or '—'}"
                     + (f"\n  promise: {section.promise}" if section.promise else ""))
    return "\n".join(lines)


def manuscript_format(body: str) -> list[str]:
    """`manuscript_format`: what the book format refuses in a section's body."""

    from ..markdown import is_comment, parse

    problems = []
    if not body.strip():
        return ["The chapter has no text."]
    for node in parse(body).walk():
        if node.type in ("html_block", "html_inline") and not is_comment(node):
            problems.append(f"Raw HTML is not part of the format: {node.content.strip()[:60]!r}")
        if node.type == "heading" and node.tag == "h1":
            problems.append("A `#` heading: the chapter's title is in the frontmatter, sections start at `##`.")
    return problems[:6]


def _work(book: Book, language: str, section: str, instruction: str = "", *, model: Model | None = None,
          reviewer: Model | None = None) -> SimpleWork:
    sections = book.sections(language)
    index = next((i for i, s in enumerate(sections) if s.id == section), None)
    if index is None:
        raise NotFoundError(f"No section {section!r} in {language}")
    target = sections[index]
    current = read_section(book, language, section)
    front, body = split_frontmatter(current["text"])
    header = current["text"][: len(current["text"]) - len(body)]
    practices, settings = catalogue(book, language)
    research = []
    for name in front.get("research") or []:
        path = book.root / "research" / f"{name}.md"
        if path.is_file():
            research.append(f"[research/{name}.md]\n{path.read_text('utf-8')}")
    previous = sections[index - 1].body.strip()[-3000:] if index > 0 else "(this is the first section)"
    vices = "\n".join(f"- {p.rule}" for p in practices)
    prompt = (f"The book:\n{book_context(book, settings)}\n\nThe plan of the whole book:\n{_plan(book, section)}\n\n"
              f"This chapter: {target.title}\nCovers: {target.synopsis or '—'}\nPromise: {target.promise or '—'}\n\n"
              f"End of the previous section:\n{previous}\n\n"
              f"Research for this chapter:\n{chr(10).join(research) or '(none named in its frontmatter)'}\n\n"
              f"Writing vices to avoid:\n{vices}\n\n{FORMAT}\n\n"
              + (f"The current text (rewrite it):\n{body}\n\n" if body.strip() else "")
              + f"The author's instruction:\n{instruction.strip() or '(none: write the chapter)'}")
    chosen = model or model_from_env()

    def ask(request: str, standing: dict[str, Any] | None, error: str) -> dict[str, Any]:
        return chosen.ask(SYSTEM, again(prompt, request, standing, error), SCHEMA)

    def land(answer: dict[str, Any]) -> dict[str, Any]:
        from dataclasses import replace

        text = header + "\n" + answer["body"].strip() + "\n"
        version = propose_version(book, language, section, text, actor=AGENT, scope="content",
                                  rationale=("Draft by the writer" if not body.strip() else "Rewrite by the writer")
                                  + (f": {instruction.strip()}" if instruction.strip() else "."),
                                  task=answer.get("notes", ""))
        candidate = replace(target, body=split_frontmatter(text)[1], path=target.path.with_suffix(".candidate"))
        findings = check_sections(book, language, [candidate], engines=False).findings
        report = version_report(book, version["id"])
        return {"version": version["id"], "section": section, "language": language,
                "words": len(answer["body"].split()), "notes": answer.get("notes", ""),
                "to_check": answer.get("to_check") or [], "style_findings": len(findings),
                "facts_added": len(report["fidelity"]["facts_added"]), "summary": answer.get("notes", "")}

    def review(outcome: dict[str, Any]) -> dict[str, Any]:
        return review_work(reviewer or chosen, title="Writer",
                           role="Writes one chapter so that it keeps its promise, in the book's voice.", shown=prompt,
                           answered=version_text(book, language, section, outcome.get("version")))

    return SimpleWork(f"Writer: {target.title}", ask=ask, land=land, review=review,
                      checks=[("manuscript_format", lambda answer: manuscript_format(str(answer.get("body", ""))))])


def write_section(book: Book, language: str, section: str, instruction: str = "", *,
                  model: Model | None = None, progress=lambda message: None) -> dict[str, Any]:
    return run_work(_work(book, language, section, instruction, model=model), progress=progress)


@flow_kind("write_section", "Writer: write a section to its synopsis and promise, as a candidate version")
def write_flow(book: Book, payload: dict[str, Any], progress) -> tuple[Any, dict[str, Any], list]:
    return _work(book, payload.get("language") or book.source_language, payload["section"],
                 payload.get("instruction", "")), {}, []

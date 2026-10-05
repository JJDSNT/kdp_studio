"""The researcher (docs/origin, §5.3): sources found, opened, and recorded.

It searches the web and opens what it cites. Its answer is a dossier -- what
was asked, what was found, with which source supporting which claim, and
what was *not* found ("not found" is a valid answer) -- written to
`research/<slug>.md`, and every source joins the ledger `research/sources.yaml`
with the date it was opened. A source that was not opened does not enter.

Checking that a source supports the claim the *text* makes is a different
agent's job (the fact-checker), on purpose: whoever researched is biased
toward their own find.
"""

from __future__ import annotations

from typing import Any

import yaml

from ..book import Book
from ..errors import ValidationError
from ..history import commit
from ..jobs import Progress, kind
from ..model import Model, model_from_env
from ..state import Actor, book_lock, now
from ..structure import slug
from .edits import book_context

AGENT = Actor("researcher", "agent")
LEDGER = "research/sources.yaml"

SYSTEM = (
    "You are the researcher of a book. Search the web and OPEN every page you cite; a source you did not open "
    "does not exist. Prefer official documentation, original repositories and primary literature; date what "
    "changes. For each finding, give the claim and the sources that support it, quoting or paraphrasing what "
    "the page actually says. Separate verified capability from vendor promise and speculation. When you could "
    "not find something, say so in `not_found`: that is a valid, useful answer. Write in the book's language."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "object", "properties": {
            "claim": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "string", "enum": ["verified", "partial", "vendor_claim", "speculative"]}},
            "required": ["claim", "sources", "confidence"]}},
        "sources": {"type": "array", "items": {"type": "object", "properties": {
            "url": {"type": "string"}, "title": {"type": "string"}, "publisher": {"type": "string"},
            "published": {"type": "string"}, "says": {"type": "string"}},
            "required": ["url", "title", "says"]}},
        "not_found": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "findings", "sources", "not_found"],
}


def dossiers(book: Book) -> list[dict[str, Any]]:
    folder = book.root / "research"
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.glob("*.md")):
        text = path.read_text("utf-8")
        title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), path.stem)
        out.append({"slug": path.stem, "title": title, "path": str(path.relative_to(book.root)),
                    "words": len(text.split())})
    return out


def ledger(book: Book) -> list[dict[str, Any]]:
    path = book.root / LEDGER
    return (yaml.safe_load(path.read_text("utf-8")) or []) if path.is_file() else []


def _dossier(question: str, answer: dict[str, Any], opened: str, words: dict[str, str]) -> str:
    lines = [f"# {question}", "", f"*{words['note'].format(date=opened, ledger=LEDGER)}*", "",
             answer.get("summary", "").strip(), ""]
    if answer.get("findings"):
        lines += [f"## {words['findings']}", ""]
        for finding in answer["findings"]:
            sources = ", ".join(f"<{url}>" for url in finding.get("sources") or [])
            lines.append(f"- {finding['claim']} — *{finding.get('confidence', '')}* {sources}".rstrip())
        lines.append("")
    if answer.get("not_found"):
        lines += [f"## {words['not_found']}", ""] + [f"- {item}" for item in answer["not_found"]] + [""]
    if answer.get("sources"):
        lines += [f"## {words['sources']}", ""]
        for source in answer["sources"]:
            meta = ", ".join(x for x in (source.get("publisher"), source.get("published")) if x)
            lines.append(f"- [{source['title']}]({source['url']})" + (f" ({meta})" if meta else "")
                         + f": {source['says']}")
        lines.append("")
    return "\n".join(lines)


def research(book: Book, question: str, *, name: str = "", model: Model | None = None,
             progress=lambda message: None) -> dict[str, Any]:
    if not question.strip():
        raise ValidationError("Research needs a question")
    from ..style import catalogue

    _, settings = catalogue(book, book.source_language)
    prompt = (f"The book:\n{book_context(book, settings)}\n\nWhat the author needs researched:\n{question}\n\n"
              f"Already in the book's research: {', '.join(d['title'] for d in dossiers(book)) or 'nothing yet'}.")
    progress("Searching and opening sources")
    answer = (model or model_from_env()).ask(SYSTEM, prompt, SCHEMA, web=True)
    opened = now()[:10]
    dossier_slug = slug(name or question)[:50]
    folder = book.root / "research"
    with book_lock(book.root):
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{dossier_slug}.md"
        n = 2
        while path.exists():
            path, n = folder / f"{dossier_slug}-{n}.md", n + 1
        from ..labels import labels

        words = labels(book.source_language)["research"]
        path.write_text(_dossier(question.strip(), answer, opened, words), encoding="utf-8")
        entries = ledger(book)
        known = {e["url"] for e in entries}
        for source in answer.get("sources") or []:
            if source["url"] not in known:
                entries.append({"url": source["url"], "title": source["title"], "opened": opened,
                                "says": source["says"], "dossier": path.stem,
                                **({"publisher": source["publisher"]} if source.get("publisher") else {}),
                                **({"published": source["published"]} if source.get("published") else {})})
        ledger_path = book.root / LEDGER
        ledger_path.write_text(yaml.safe_dump(entries, allow_unicode=True, sort_keys=False, width=100),
                               encoding="utf-8")
        commit(book.root, [path, ledger_path], f"Research: {question.strip()[:80]}", AGENT)
    progress(f"Recorded {len(answer.get('sources') or [])} source(s)")
    return {"dossier": str(path.relative_to(book.root)), "sources": len(answer.get("sources") or []),
            "findings": len(answer.get("findings") or []), "not_found": answer.get("not_found") or [],
            "summary": answer.get("summary", "")}


@kind("research", "Researcher: search, open and record sources into a dossier")
def research_job(book: Book, payload: dict[str, Any], actor: Actor, progress: Progress) -> dict[str, Any]:
    return research(book, payload.get("question", ""), name=payload.get("name", ""), progress=progress)

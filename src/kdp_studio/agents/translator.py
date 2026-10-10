"""The translator (docs/origin, §5.13): the book adapted for another language.

Not a literal translation: examples, puns, cultural references and
instructions that depend on a keyboard, a system or what is available in a
region are adapted, and each adaptation is declared. What must not move --
structure, prompt ids, code, URLs, numbers, the glossary's terms -- is
measured afterwards by code (translation.py), not promised by the model.

It works section by section. The result is a candidate version of the
section in the target language, with the digest of the source it was made
from: when the source changes later, the translation shows as stale. The
author reads, adopts or sends it back with an instruction, as with any text.
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from ..book import Book, Part, split_frontmatter
from ..checks import PASS, summary
from ..errors import NotFoundError, ValidationError
from ..jobs import Progress, kind
from ..model import Model, model_from_env
from ..state import Actor, read_state
from ..style import catalogue
from ..translation import (GLOSSARY, META_TEXT, compare_translation, glossary, glossary_text, section_states)
from ..versions import propose_version, read_section
from .edits import book_context

AGENT = Actor("translator", "agent")

SYSTEM = (
    "You are the translator of a book: you adapt ONE section editorially into the target language, for a reader "
    "who lives in that language. A text that reads as translated has failed. Carry the book's voice over — its "
    "register, rhythm and how it addresses the reader — into natural, native prose. Adapt what would not work "
    "literally: examples, puns, cultural references, units, and instructions that depend on a keyboard, an "
    "operating system, an interface label or what is available in a region; list every adaptation in "
    "`adaptations` with why. Do not add, remove or reorder ideas, and never change a fact: names, dates, "
    "quantities, URLs, file names and code stay; numbers follow the target language's separators. Use the "
    "glossary's terms always, and write the never-translated names exactly as given. "
    "Keep the Markdown structure exactly: the same headings at the same levels, the same callouts (the marker "
    "`> [!concept]`, `> [!warning]`… is syntax and stays in English; the title after it is translated), the same "
    "exercises (`::: exercise Title` — `exercise` is syntax, the title is translated), the same footnote ids, "
    "images and tables. A prompt block keeps its id line unchanged (`> [!prompt] EX-02-01`); the prompt itself is "
    "translated so the reader can give it to an agent in their language, and keeps its `---` separators and "
    "bold labels. Code blocks and inline code are copied unchanged. HTML comments are editorial notes: keep each "
    "one, translated. A reference to a chapter by number keeps the number. Titles carry no numbering. "
    "`terms` lists the terms of art you met that the glossary does not have, with the translation you used."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "toc_title": {"type": "string"},
        "synopsis": {"type": "string"},
        "promise": {"type": "string"},
        "body": {"type": "string"},
        "adaptations": {"type": "array", "items": {"type": "object", "properties": {
            "source": {"type": "string"}, "target": {"type": "string"}, "why": {"type": "string"}},
            "required": ["source", "target", "why"]}},
        "terms": {"type": "array", "items": {"type": "object", "properties": {
            "source": {"type": "string"}, "target": {"type": "string"}}, "required": ["source", "target"]}},
        "notes": {"type": "string"},
    },
    "required": ["title", "body", "adaptations", "terms", "notes"],
}

META_SYSTEM = (
    "You are the translator of a book. Translate what the book says about itself — title, subtitle, tagline, "
    "part titles, the copyright page (`colophon`, Markdown) and the sales copy (`description`) — into the target "
    "language, as a publisher of that language would write them. Keep names, the author, years, ISBNs, URLs, "
    "placeholders in square brackets and inline code exactly. Part titles carry no numbering. Use the glossary. "
    "Leave a field empty when the source has none. A title is the author's decision: offer the one you would "
    "print and say in `notes` what you weighed."
)

META_SCHEMA = {
    "type": "object",
    "properties": {
        **{key: {"type": "string"} for key in META_TEXT},
        "parts": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "title": {"type": "string"}}, "required": ["id", "title"]}},
        "notes": {"type": "string"},
    },
    "required": ["title", "parts", "notes"],
}

GLOSSARY_SYSTEM = (
    "You prepare the bilingual glossary of a book before it is translated: the terms of art whose translation "
    "must be the same in every chapter. List each term the book uses as a concept — not ordinary words — with "
    "the forms it takes in the source (singular and plural, as written) and the forms to use in the target "
    "language, choosing the term a reader of that language already knows from the field. `keep` lists the names "
    "that are never translated: products, companies, file names, commands. Follow the book's own localisation "
    "notes when it has them; they win. Say in `notes` which choices the author should look at."
)

GLOSSARY_SCHEMA = {
    "type": "object",
    "properties": {
        "terms": {"type": "array", "items": {"type": "object", "properties": {
            "source": {"type": "array", "items": {"type": "string"}},
            "target": {"type": "array", "items": {"type": "string"}},
            "note": {"type": "string"}}, "required": ["source", "target"]}},
        "keep": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
    },
    "required": ["terms", "keep", "notes"],
}


def _guides(book: Book) -> str:
    """The book's own localisation notes, named in its glossary."""

    found = []
    for relative in glossary(book).guide:
        path = (book.root / relative).resolve()
        if book.root.resolve() in path.parents and path.is_file():
            found.append(f"[{relative} — the book's localisation notes]\n{path.read_text('utf-8')}")
    return "\n\n".join(found)


def _best_text(book: Book, language: str, section: str) -> str:
    """The section in the target language as it stands: adopted, else the latest candidate."""

    text = read_section(book, language, section)["text"]
    if split_frontmatter(text)[1].strip():
        return text
    waiting = [v for v in read_state(book.root).get("versions", {}).values()
               if v["language"] == language and v["section"] == section and v["state"] == "candidate"
               and v["proposed_by"]["id"] == AGENT.id]
    if not waiting:
        return ""
    latest = max(waiting, key=lambda v: v["proposed_at"])
    return (book.root / "versions" / language / section / f"{latest['id']}.md").read_text("utf-8")


def _titles(book: Book, language: str) -> str:
    """Titles already chosen in the target language, so a cross-reference names them the same way."""

    lines = []
    source_parts = {e.id: e.title for e in book.contents(book.source_language) if isinstance(e, Part)}
    for entry in book.contents(language):
        if isinstance(entry, Part) and entry.title != source_parts.get(entry.id):
            lines.append(f"- part “{source_parts.get(entry.id)}” → “{entry.title}”")
    for source in book.sections(book.source_language):
        text = _best_text(book, language, source.id)
        title = str(split_frontmatter(text)[0].get("title", "")) if text else ""
        if title and title != source.title:
            lines.append(f"- “{source.title}” → “{title}”")
    return "\n".join(lines) or "(none yet)"


def _frontmatter(source_front: dict[str, Any], answer: dict[str, Any]) -> str:
    front = dict(source_front)
    for key in ("title", "toc_title", "synopsis", "promise"):
        if source_front.get(key) and str(answer.get(key) or "").strip():
            front[key] = str(answer[key]).strip()
    return "---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=100).strip() + "\n---\n"


def translate_section(book: Book, language: str, section: str, instruction: str = "", *,
                      model: Model | None = None, progress=lambda message: None) -> dict[str, Any]:
    states = section_states(book, language)
    if section not in states:
        raise NotFoundError(f"No section {section!r} in the book")
    source_language = book.source_language
    sources = book.sections(source_language)
    index = next(i for i, s in enumerate(sources) if s.id == section)
    source_text = read_section(book, source_language, section)["text"]
    source_front, source_body = split_frontmatter(source_text)
    if not source_body.strip():
        raise ValidationError(f"{section} has no text in {source_language} yet: there is nothing to translate")
    current = split_frontmatter(read_section(book, language, section)["text"])[1]
    practices, settings = catalogue(book, language)
    terms = glossary(book)
    previous = _best_text(book, language, sources[index - 1].id) if index else ""
    vices = "\n".join(f"- {p.rule}" for p in practices) or "(none catalogued for this language)"
    guides = _guides(book)
    prompt = (f"Translate from {source_language} into {language}.\n\n"
              f"The book (in its source language; carry this voice over):\n{book_context(book, settings)}\n\n"
              + (f"{guides}\n\n" if guides else "")
              + f"Glossary ({source_language} → {language}):\n{glossary_text(terms, source_language, language)}\n\n"
              f"Titles already chosen in {language}:\n{_titles(book, language)}\n\n"
              f"Writing vices to avoid in {language}:\n{vices}\n\n"
              + (f"How the previous section ends in {language} (continue in this voice):\n"
                 f"{split_frontmatter(previous)[1].strip()[-2500:]}\n\n" if previous else "")
              + (f"The current translation (the source changed since, or the author wants another; keep what "
                 f"still corresponds):\n{current}\n\n" if current.strip() else "")
              + f"The author's instruction:\n{instruction.strip() or '(none)'}\n\n"
              f"The section to translate ({section}):\n\n{source_text}")
    progress(f"Translating {section} into {language}")
    answer = (model or model_from_env()).ask(SYSTEM, prompt, SCHEMA)
    text = _frontmatter(source_front, answer) + "\n" + str(answer["body"]).strip() + "\n"
    task = {"agent": AGENT.id, "source_language": source_language, "source_digest": states[section]["source_digest"],
            "instruction": instruction.strip(), "adaptations": answer.get("adaptations") or [],
            "terms": answer.get("terms") or [], "notes": answer.get("notes", "")}
    version = propose_version(book, language, section, text, actor=AGENT, scope="content",
                              rationale=f"Translation from {source_language} by the translator"
                              + (f": {instruction.strip()}" if instruction.strip() else "."),
                              task=json.dumps(task, ensure_ascii=False))
    findings = compare_translation(source_text, text, source_language=source_language, language=language, terms=terms)
    open_findings = [f.public_dict() for f in findings if f.verdict != PASS]
    progress(f"Recorded a candidate version ({len(open_findings)} finding(s) to read)")
    return {"version": version["id"], "section": section, "language": language,
            "words": len(str(answer["body"]).split()), "checks": summary(findings), "findings": open_findings,
            "adaptations": task["adaptations"], "terms": task["terms"], "notes": task["notes"],
            "summary": task["notes"]}


def pending(book: Book, language: str) -> list[str]:
    """Sections with nothing to read yet: untranslated or stale, and no candidate waiting."""

    return [section for section, state in section_states(book, language).items()
            if state["state"] in ("untranslated", "stale") and not state["candidates"]]


def translate_book(book: Book, language: str, sections: list[str] | None = None, instruction: str = "", *,
                   model: Model | None = None, progress=lambda message: None) -> dict[str, Any]:
    """Every pending section, in reading order; one that fails does not stop the others."""

    todo = [s.id for s in book.sections(book.source_language)
            if s.id in set(sections or pending(book, language)) and s.body.strip()]
    done, failed = [], []
    for number, section in enumerate(todo, start=1):
        progress(f"{number}/{len(todo)}: {section}")
        try:
            result = translate_section(book, language, section, instruction, model=model)
            done.append({k: result[k] for k in ("section", "version", "words", "checks")}
                        | {"adaptations": len(result["adaptations"])})
        except Exception as error:  # noqa: BLE001 - the job reports it and goes on
            failed.append({"section": section, "error": getattr(error, "message", str(error))})
    terms: dict[str, str] = {}
    for item in done:
        task = json.loads(read_state(book.root)["versions"][item["version"]]["task"])
        terms.update({t["source"]: t["target"] for t in task.get("terms") or []})
    return {"language": language, "translated": done, "failed": failed,
            "terms_outside_the_glossary": [{"source": k, "target": v} for k, v in sorted(terms.items())],
            "summary": f"{len(done)} section(s) translated as candidates" + (f", {len(failed)} failed" if failed else "")}


def translate_meta(book: Book, language: str, *, model: Model | None = None) -> dict[str, Any]:
    """meta.yaml in the target language: the translated fields, and the translator's notes."""

    source = book.meta(book.source_language)
    fields = {key: source[key] for key in META_TEXT if source.get(key)}
    parts = {str(k): v for k, v in (source.get("parts") or {}).items()}
    _, settings = catalogue(book, language)
    prompt = (f"Translate from {book.source_language} into {language}.\n\n"
              f"The book:\n{book_context(book, settings)}\n\n"
              f"Glossary:\n{glossary_text(glossary(book), book.source_language, language)}\n\n"
              f"Author: {book.author}\n\nFields:\n{yaml.safe_dump(fields, allow_unicode=True, sort_keys=False)}\n"
              f"Parts (id: title):\n{yaml.safe_dump(parts, allow_unicode=True, sort_keys=False)}")
    answer = (model or model_from_env()).ask(META_SYSTEM, prompt, META_SCHEMA)
    translated: dict[str, Any] = {key: answer[key] for key in fields if str(answer.get(key) or "").strip()}
    translated["parts"] = {str(p["id"]): p["title"] for p in answer.get("parts") or [] if str(p["id"]) in parts}
    return {"meta": translated, "notes": answer.get("notes", "")}


def propose_glossary(book: Book, language: str, *, model: Model | None = None) -> dict[str, Any]:
    """The terms the book uses as concepts, with a translation for each: a draft of glossary.yaml."""

    source = book.source_language
    text = "\n\n".join(f"# {s.title}\n\n{s.body}" for s in book.sections(source))
    # The book's own notes on localisation, wherever it keeps them under editorial/.
    names = ("locali", "glossar", "translat", "tradu")
    notes = sorted(str(p.relative_to(book.root)) for p in (book.root / "editorial").glob("*.md")
                   if any(name in p.name.lower() for name in names))
    guides = "\n\n".join(f"[{path}]\n{(book.root / path).read_text('utf-8')}" for path in notes)
    intention = book.root / "intentions.md"
    prompt = (f"Source language: {source}. Target language: {language}.\n\n"
              + (f"[intentions.md]\n{intention.read_text('utf-8')}\n\n" if intention.is_file() else "")
              + (f"The book's localisation notes (they win):\n{guides}\n\n" if guides else "")
              + f"The book:\n\n{text}")
    answer = (model or model_from_env()).ask(GLOSSARY_SYSTEM, prompt, GLOSSARY_SCHEMA)
    terms = [{source: t["source"], language: t["target"], **({"note": t["note"]} if t.get("note") else {})}
             for t in answer.get("terms") or [] if t.get("source") and t.get("target")]
    data: dict[str, Any] = {"terms": terms, "keep": sorted(set(answer.get("keep") or []))}
    if notes:
        data["guide"] = notes

    def flow(value: Any) -> str:
        # A bare scalar is dumped with a document end ("...") after it.
        text = yaml.safe_dump(value, allow_unicode=True, default_flow_style=True, width=10000).strip()
        return text.removesuffix("...").strip()

    # One line per language: a glossary is read down its columns.
    lines = ["# The bilingual decisions of this book (docs/book-format.md). Drafted by the translator;",
             "# yours to edit. The translation report counts every term and name listed here.", "terms:"]
    for term in terms:
        lines += [f"  - {source}: {flow(term[source])}", f"    {language}: {flow(term[language])}"]
        if term.get("note"):
            lines.append(f"    note: {flow(term['note'])}")
    lines.append(f"keep: {flow(data['keep'])}")
    if notes:
        lines.append(f"guide: {flow(notes)}")
    draft = "\n".join(lines) + "\n"
    return {"glossary": draft, "terms": len(terms), "keep": len(data["keep"]), "notes": answer.get("notes", "")}


@kind("translate_section", "Translator: adapt one section into another language, as a candidate version")
def translate_section_job(book: Book, payload: dict[str, Any], actor: Actor, progress: Progress) -> dict[str, Any]:
    return translate_section(book, payload["language"], payload["section"], payload.get("instruction", ""),
                             progress=progress)


@kind("translate_book", "Translator: every untranslated or stale section of a language, each as a candidate version")
def translate_book_job(book: Book, payload: dict[str, Any], actor: Actor, progress: Progress) -> dict[str, Any]:
    return translate_book(book, payload["language"], payload.get("sections"), payload.get("instruction", ""),
                          progress=progress)


@kind("add_language", "Translator: add a language to the book, with its meta.yaml translated and a stub per section")
def add_language_job(book: Book, payload: dict[str, Any], actor: Actor, progress: Progress) -> dict[str, Any]:
    from ..commands import dispatch

    language = payload["language"]
    translated: dict[str, Any] = {}
    notes = ""
    if not payload.get("copy_meta"):
        progress(f"Translating the title, the part titles and the copyright page into {language}")
        answer = translate_meta(book, language)
        translated, notes = answer["meta"], answer["notes"]
    result = dispatch(book, "add_language", {"language": language, "meta": translated,
                                             "reason": payload.get("reason", "")}, actor)
    progress(f"{language} added: {result['sections']} section(s) waiting for translation")
    return {**result, "notes": notes,
            "summary": f"{language} added. Read manuscript/{language}/meta.yaml: the title is yours to decide."}


@kind("propose_glossary", "Translator: draft the book's bilingual glossary; written only when the book has none")
def propose_glossary_job(book: Book, payload: dict[str, Any], actor: Actor, progress: Progress) -> dict[str, Any]:
    from ..commands import dispatch

    progress("Reading the book for its terms")
    result = propose_glossary(book, payload["language"])
    if (book.root / GLOSSARY).is_file():
        return {**result, "written": False,
                "summary": f"{GLOSSARY} exists and is yours: the draft is here for you to compare."}
    dispatch(book, "write_glossary", {"text": result["glossary"], "reason": "drafted by the translator"}, actor)
    return {**result, "written": True, "summary": f"{GLOSSARY} drafted: {result['terms']} term(s). Read it first."}

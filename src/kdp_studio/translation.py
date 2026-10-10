"""A second language of the same book, and what a machine can say about it.

A translation is an editorial adaptation (docs/origin, §5.13): whether it
reads well is for a person. What is *measured* here is everything that must
survive it whatever the wording -- the structure (headings, callouts,
exercises, prompt ids, footnotes, code), the facts a machine can see (URLs,
numbers, code spans), the terms the book decided in its glossary -- and
whether the translation still corresponds to the source it was made from.

- `add_language` -- the language joins `book.yaml`, with its `meta.yaml` and
  one stub per section (the source's frontmatter, no body yet);
- `glossary` -- the book's bilingual decisions (`glossary.yaml`);
- `compare_translation` -- one section against its source, as findings;
- `report` -- every section's state (untranslated, translated, stale,
  unrecorded) with its findings, and the language's `meta.yaml`.

A difference is a finding for the author to read, never a rewrite: a number
the adaptation converted on purpose shows as a warning, and stays.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any

import yaml
from markdown_it.tree import SyntaxTreeNode

from .book import BOOK_FILENAME, Book, load_book, split_frontmatter
from .checks import FAIL, INFO, PASS, WARN, Finding, summary
from .errors import BookFormatError, NotFoundError, ValidationError
from .fidelity import digest, reading_lines
from .history import commit
from .markdown import callout, is_comment, parse
from .state import Actor, book_lock, commit_state, now, read_state
from .style import units

GLOSSARY = "glossary.yaml"
_LANGUAGE = re.compile(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*")
#: Languages that write 1,000.5; the others write 1.000,5.
_POINT_DECIMAL = {"en", "ja", "zh", "ko", "he", "th", "hi"}
#: Words of a translation per word of its source, outside which someone should look.
LENGTH_RATIO = (0.7, 1.4)
#: What `meta.yaml` says in words, and so changes with the language.
META_TEXT = ("title", "subtitle", "tagline", "description", "colophon")
#: The words of the cover (`cover:` in meta.yaml) that are prose. How the
#: title breaks (`cover.title`) is decided again in each language.
COVER_TEXT = ("line", "back", "about")


# ---------------------------------------------------------------- glossary

@dataclass(frozen=True)
class Term:
    #: language -> the forms the term takes there (singular, plural...).
    forms: dict[str, tuple[str, ...]]
    note: str = ""


@dataclass(frozen=True)
class Glossary:
    terms: tuple[Term, ...] = ()
    #: Names that stay as they are in every language (products, files).
    keep: tuple[str, ...] = ()
    #: The book's own localisation notes, read by the translator.
    guide: tuple[str, ...] = ()
    present: bool = False

    def pairs(self, source: str, target: str) -> list[tuple[tuple[str, ...], tuple[str, ...], str]]:
        return [(t.forms[source], t.forms[target], t.note) for t in self.terms
                if t.forms.get(source) and t.forms.get(target)]


def _forms(value: Any) -> tuple[str, ...]:
    items = value if isinstance(value, list) else [value]
    return tuple(str(i).strip() for i in items if str(i).strip())


def glossary(book: Book) -> Glossary:
    path = book.root / GLOSSARY
    if not path.is_file():
        return Glossary()
    data = yaml.safe_load(path.read_text("utf-8")) or {}
    if not isinstance(data, dict):
        raise BookFormatError(f"{GLOSSARY} must be a mapping")
    terms = []
    for entry in data.get("terms") or []:
        if not isinstance(entry, dict):
            raise BookFormatError(f"{GLOSSARY}: a term is a mapping of language to its forms")
        forms = {str(k): _forms(v) for k, v in entry.items() if k != "note"}
        terms.append(Term(forms, str(entry.get("note") or "")))
    return Glossary(tuple(terms), _forms(data.get("keep") or []), _forms(data.get("guide") or []), True)


def glossary_text(found: Glossary, source: str, target: str) -> str:
    """The glossary as an agent reads it."""

    lines = [f"- {' / '.join(a)} → {' / '.join(b)}" + (f"  ({note})" if note else "")
             for a, b, note in found.pairs(source, target)]
    if found.keep:
        lines.append("Never translated, written exactly so: " + ", ".join(found.keep))
    return "\n".join(lines) or "(the book has no glossary yet)"


def _occurrences(forms: tuple[str, ...], text: str) -> int:
    pattern = "|".join(re.escape(f) for f in sorted(forms, key=len, reverse=True))
    return len(re.findall(rf"(?<!\w)(?:{pattern})(?!\w)", text, re.IGNORECASE))


# ------------------------------------------------------- what is compared

def _canonical_number(raw: str, language: str) -> str:
    """One spelling for a number, whatever separators its language uses."""

    point = language.split("-")[0] in _POINT_DECIMAL
    thousands, decimal = (",", ".") if point else (".", ",")
    if re.fullmatch(rf"\d{{1,3}}(?:{re.escape(thousands)}\d{{3}})+(?:{re.escape(decimal)}\d+)?", raw):
        raw = raw.replace(thousands, "")
    raw = raw.replace(decimal, ".") if raw.count(decimal) == 1 else raw
    return raw.lstrip("0") or "0" if raw.isdigit() else raw


@dataclass
class Shape:
    """What of a section a translation must carry over."""

    headings: Counter
    callouts: Counter
    prompts: list[str]
    exercises: int
    fences: list[str]
    code: Counter
    footnotes: Counter
    images: Counter
    tables: int
    comments: int
    urls: Counter
    numbers: Counter
    paragraphs: list[str]
    reader_text: str
    words: int


def shape(body: str, language: str) -> Shape:
    found = Shape(Counter(), Counter(), [], 0, [], Counter(), Counter(), Counter(), 0, 0, Counter(), Counter(),
                  [], "", 0)

    def walk(node: SyntaxTreeNode) -> None:
        if is_comment(node):
            found.comments += 1
            return
        if node.type == "heading":
            found.headings[node.tag] += 1
        elif node.type == "blockquote" and (declared := callout(node)) is not None:
            found.callouts[declared.kind] += 1
            if declared.kind == "prompt":
                found.prompts.append(declared.title)
        elif node.type == "container_exercise":
            found.exercises += 1
        elif node.type in ("fence", "code_block"):
            found.fences.append(node.content)
        elif node.type == "code_inline":
            found.code[node.content] += 1
        elif node.type == "image":
            found.images[str(node.attrs.get("src", ""))] += 1
        elif node.type == "table":
            found.tables += 1
        for child in node.children:
            walk(child)

    walk(parse(body))
    found.footnotes.update(re.findall(r"\[\^([^\]\s]+)\]", body))
    found.urls.update(u.rstrip(".,;:") for u in re.findall(r"https?://[^\s)>\]]+", body))
    lines = "\n".join(reading_lines(body))
    lines = re.sub(r"https?://[^\s)>\]]+", " ", lines)
    # An ordinal is its number: "dia 14" and "the 14th" say the same.
    found.numbers.update(_canonical_number(n, language) for n in re.findall(
        r"(?<![\w.,])(\d+(?:[.,]\d+)*)(?:st|nd|rd|th|[ºª°])?(?![\w])", lines))
    found.paragraphs = [u.text for u in units(body)]
    found.reader_text = "\n".join(found.paragraphs)
    found.words = len(re.findall(r"\w+", re.sub(r"<!--.*?-->", "", body, flags=re.S)))
    return found


def _difference(source: Counter, target: Counter, limit: int = 8) -> str:
    missing = sorted((source - target).items())
    extra = sorted((target - source).items())

    def listed(items: list[tuple[Any, int]]) -> str:
        shown = ", ".join(f"{value}" + (f" ×{count}" if count > 1 else "") for value, count in items[:limit])
        return shown + (f" … (+{len(items) - limit})" if len(items) > limit else "")

    parts = []
    if missing:
        parts.append(f"only in the source: {listed(missing)}")
    if extra:
        parts.append(f"only in the translation: {listed(extra)}")
    return "; ".join(parts)


def _counted(identifier: str, item: str, source: Counter, target: Counter, verdict: str) -> Finding:
    same = source == target
    return Finding(identifier, item, PASS if same else verdict,
                   f"{sum(target.values())} in the translation, {sum(source.values())} in the source",
                   "the same as the source", "" if same else _difference(source, target))


def compare_translation(source_text: str, target_text: str, *, source_language: str, language: str,
                        terms: Glossary | None = None) -> list[Finding]:
    """One section against its source: what a machine can measure of a translation."""

    source_front, source_body = split_frontmatter(source_text)
    target_front, target_body = split_frontmatter(target_text)
    if not target_body.strip():
        return [Finding("translated", "The section is translated", FAIL, "no body yet", "a translation")]
    a, b = shape(source_body, source_language), shape(target_body, language)
    kind_a, kind_b = source_front.get("kind", "chapter"), target_front.get("kind", "chapter")
    findings = [
        Finding("kind", "Kind of section", PASS if kind_a == kind_b else FAIL, str(kind_b), str(kind_a)),
        Finding("prompts", "Prompt ids, in order", PASS if a.prompts == b.prompts else FAIL,
                ", ".join(b.prompts) or "none", ", ".join(a.prompts) or "none"),
        Finding("exercises", "Exercises", PASS if a.exercises == b.exercises else FAIL,
                str(b.exercises), str(a.exercises)),
        _counted("callouts", "Callouts, by kind", a.callouts, b.callouts, FAIL),
        _counted("headings", "Headings, by level", a.headings, b.headings, WARN),
        _counted("footnotes", "Footnote marks and notes", a.footnotes, b.footnotes, FAIL),
        _counted("images", "Images", a.images, b.images, FAIL),
        Finding("tables", "Tables", PASS if a.tables == b.tables else FAIL, str(b.tables), str(a.tables)),
        Finding("code-blocks", "Code blocks", PASS if len(a.fences) == len(b.fences) else FAIL,
                f"{len(b.fences)}, {sum(1 for x, y in zip(a.fences, b.fences) if x == y)} identical to the source",
                str(len(a.fences))),
        _counted("code", "Inline code", a.code, b.code, WARN),
        _counted("urls", "URLs", a.urls, b.urls, WARN),
        _counted("numbers", "Numbers (separators normalised per language)", a.numbers, b.numbers, WARN),
        Finding("comments", "Editorial comments", PASS if a.comments == b.comments else WARN,
                str(b.comments), str(a.comments),
                "" if a.comments == b.comments else "a pending verification must not be lost in translation"),
    ]
    ratio = b.words / a.words if a.words else 0.0
    low, high = LENGTH_RATIO
    findings.append(Finding("length", "Words per word of the source", PASS if low <= ratio <= high else WARN,
                            f"{ratio:.2f} ({b.words} / {a.words})", f"{low:.1f} to {high:.1f}"))
    originals = {p for p in a.paragraphs if len(p.split()) >= 8}
    left = [p for p in b.paragraphs if p in originals]
    findings.append(Finding("untranslated", "Paragraphs identical to the source", WARN if left else PASS,
                            str(len(left)), "0", "; ".join(f"“{p[:70]}…”" for p in left[:3])))
    title_a, title_b = str(source_front.get("title", "")), str(target_front.get("title", ""))
    findings.append(Finding("title", "Title", WARN if title_a == title_b and len(title_a.split()) > 1 else PASS,
                            title_b, "", "identical to the source" if title_a == title_b else ""))
    toc_a, toc_b = str(source_front.get("toc_title", "")), str(target_front.get("toc_title", ""))
    if toc_a:
        findings.append(Finding("toc-title", "Title in the contents", WARN if toc_a == toc_b else PASS, toc_b, "",
                                "identical to the source" if toc_a == toc_b else ""))
    if terms and terms.present:
        findings.extend(_glossary_findings(terms, a, b, source_language, language))
    return findings


def _glossary_findings(terms: Glossary, a: Shape, b: Shape, source: str, target: str) -> list[Finding]:
    used, lost = 0, []
    for forms_a, forms_b, _ in terms.pairs(source, target):
        before = _occurrences(forms_a, a.reader_text)
        if not before:
            continue
        used += 1
        after = _occurrences(forms_b, b.reader_text)
        if not after:
            lost.append(f"{forms_a[0]} ×{before} → {forms_b[0]} ×0")
    findings = [Finding("glossary", "Glossary terms carried", WARN if lost else PASS,
                        f"{used - len(lost)} of {used} used in the source", "every term", "; ".join(lost))]
    drift = []
    for name in terms.keep:
        before, after = _occurrences((name,), a.reader_text), _occurrences((name,), b.reader_text)
        if before != after:
            drift.append(f"{name} ×{before} → ×{after}")
    if terms.keep:
        findings.append(Finding("kept-names", "Names that are never translated", WARN if drift else PASS,
                                f"{len(terms.keep) - len(drift)} of {len(terms.keep)} with the same count",
                                "the same count as the source", "; ".join(drift)))
    return findings


# ------------------------------------------------------------------ status

def _recorded_sources(book: Book, language: str) -> dict[str, dict[str, str]]:
    """section -> the source digest its translation was last made from, or confirmed against."""

    state = read_state(book.root)
    found: dict[str, dict[str, str]] = {}

    def offer(section: str, source_digest: str, at: str, how: str) -> None:
        if source_digest and at >= found.get(section, {}).get("at", ""):
            found[section] = {"digest": source_digest, "at": at, "how": how}

    for entry in state.get("versions", {}).values():
        if entry["language"] != language or entry["state"] != "adopted":
            continue
        try:
            task = json.loads(entry.get("task") or "{}")
        except ValueError:
            continue
        if isinstance(task, dict):
            offer(entry["section"], str(task.get("source_digest", "")), entry.get("decided_at", ""), "translated")
    for section, record in (state.get("translations", {}).get(language) or {}).items():
        offer(section, record.get("source_digest", ""), record.get("at", ""), "confirmed")
    return found


def _require_translation(book: Book, language: str) -> None:
    if language not in book.languages:
        raise NotFoundError(f"The book has no language {language!r}", languages=book.languages)
    if language == book.source_language:
        raise ValidationError(f"{language} is the book's source language; a translation is of another one")


def section_states(book: Book, language: str) -> dict[str, dict[str, Any]]:
    """Each section's translation: untranslated, translated, stale or unrecorded."""

    _require_translation(book, language)
    recorded = _recorded_sources(book, language)
    waiting: Counter = Counter()
    for entry in read_state(book.root).get("versions", {}).values():
        if entry["language"] == language and entry["state"] == "candidate":
            waiting[entry["section"]] += 1
    out = {}
    for source, target in zip(book.sections(book.source_language), book.sections(language)):
        current = digest(source.path.read_bytes())
        record = recorded.get(source.id)
        if not target.body.strip():
            state = "untranslated"
        elif record is None:
            state = "unrecorded"
        else:
            state = "translated" if record["digest"] == current else "stale"
        out[source.id] = {"state": state, "source_digest": current, "candidates": waiting[source.id],
                          "recorded": record}
    return out


def meta_findings(book: Book, language: str) -> list[Finding]:
    source, target = book.meta(book.source_language), book.meta(language)
    findings = []
    for key in META_TEXT:
        if not source.get(key):
            continue
        if not target.get(key):
            findings.append(Finding(f"meta-{key}", f"meta.yaml: {key}", FAIL if key == "title" else WARN,
                                    "missing", "present, as in the source"))
        else:
            same = str(source[key]).strip() == str(target[key]).strip()
            findings.append(Finding(f"meta-{key}", f"meta.yaml: {key}", WARN if same else PASS,
                                    "identical to the source" if same else "translated", "translated"))
    cover_a, cover_b = source.get("cover") or {}, target.get("cover") or {}
    for key in COVER_TEXT:
        if cover_a.get(key):
            same = str(cover_a[key]).strip() == str(cover_b.get(key) or "").strip()
            findings.append(Finding(f"meta-cover-{key}", f"meta.yaml: cover.{key}",
                                    WARN if same or not cover_b.get(key) else PASS,
                                    "missing" if not cover_b.get(key) else "identical to the source" if same
                                    else "translated", "translated"))
    parts_a, parts_b = source.get("parts") or {}, target.get("parts") or {}
    same = sorted(str(k) for k in parts_a if str(parts_b.get(k, "")).strip() == str(parts_a[k]).strip())
    missing = sorted(str(k) for k in parts_a if not parts_b.get(k))
    findings.append(Finding("meta-parts", "meta.yaml: part titles", FAIL if missing else WARN if same else PASS,
                            f"{len(parts_a) - len(same) - len(missing)} of {len(parts_a)} translated", "every part",
                            "; ".join(filter(None, [f"missing: {', '.join(missing)}" if missing else "",
                                                    f"identical to the source: {', '.join(same)}" if same else ""]))))
    if source.get("identifier") or target.get("identifier"):
        shared = source.get("identifier") == target.get("identifier")
        findings.append(Finding("meta-identifier", "meta.yaml: the ebook identifier of this language",
                                FAIL if shared else PASS, str(target.get("identifier") or "generated"),
                                "its own, different from the source's"))
    if source.get("labels") and not target.get("labels"):
        findings.append(Finding("meta-labels", "meta.yaml: label overrides", INFO,
                                "none; the built-in labels of this language apply",
                                "", "the source overrides: " + ", ".join(sorted(source["labels"]))))
    return findings


def report(book: Book, language: str, section_ids: list[str] | None = None) -> dict[str, Any]:
    """Every section of a translated language against its source."""

    states = section_states(book, language)
    terms = glossary(book)
    sections = []
    counts: Counter = Counter()
    verdicts: Counter = Counter()
    for source, target in zip(book.sections(book.source_language), book.sections(language)):
        if section_ids and source.id not in section_ids:
            continue
        state = states[source.id]
        findings = [] if state["state"] == "untranslated" else compare_translation(
            source.path.read_text("utf-8"), target.path.read_text("utf-8"), source_language=book.source_language,
            language=language, terms=terms)
        counts[state["state"]] += 1
        verdicts.update(summary(findings))
        sections.append({"id": source.id, "number": source.number, "kind": source.kind, "title": target.title,
                         "source_title": source.title, "state": state["state"], "candidates": state["candidates"],
                         "words": target.words, "source_words": source.words,
                         "findings": [f.public_dict() for f in findings], "summary": summary(findings)})
    meta = meta_findings(book, language)
    return {"language": language, "source_language": book.source_language,
            "glossary": {"present": terms.present, "terms": len(terms.pairs(book.source_language, language)),
                         "keep": len(terms.keep)},
            "meta": [f.public_dict() for f in meta], "meta_summary": summary(meta),
            "sections": sections, "states": dict(counts), "summary": dict(verdicts)}


# ------------------------------------------------------------------ writes

def _with_languages(text: str, languages: list[str]) -> str:
    """book.yaml with its `languages` block replaced; every other line as it was."""

    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.startswith("languages:")), None)
    if start is None:
        anchor = next((i for i, line in enumerate(lines) if line.startswith("source_language:")), None)
        if anchor is None:
            raise ValidationError(f"{BOOK_FILENAME} has no source_language line to put languages after")
        return "".join(lines[:anchor + 1]) + f"languages: [{', '.join(languages)}]\n" + "".join(lines[anchor + 1:])
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].strip() and not lines[i].startswith((" ", "-", "#"))), len(lines))
    inline = "[" in lines[start]
    block = (f"languages: [{', '.join(languages)}]\n" if inline
             else "languages:\n" + "".join(f"- {language}\n" for language in languages))
    return "".join(lines[:start]) + block + "".join(lines[end:])


def language_meta(book: Book, translated: dict[str, Any] | None = None) -> dict[str, Any]:
    """The meta.yaml a new language starts with: the source's, with what was translated over it."""

    source = book.meta(book.source_language)
    meta = {k: v for k, v in source.items() if k not in ("labels", "identifier")}
    translated = translated or {}
    for key in META_TEXT:
        if source.get(key) and str(translated.get(key) or "").strip():
            meta[key] = translated[key]
    if isinstance(source.get("cover"), dict):
        words = translated.get("cover") or {}
        # The break of the title belongs to the source's words: the template breaks the new one.
        meta["cover"] = {k: (words.get(k) or v) for k, v in source["cover"].items() if k != "title"}
    titles = {str(k): str(v) for k, v in (translated.get("parts") or {}).items() if str(v).strip()}
    meta["parts"] = {k: titles.get(str(k), v) for k, v in (source.get("parts") or {}).items()}
    # Two languages of one book are two ebooks: each has its own identifier.
    meta["identifier"] = f"urn:uuid:{uuid.uuid4()}"
    return meta


def add_language(book: Book, language: str, *, actor: Actor, reason: str = "",
                 meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """A new language of the book: its meta.yaml and a stub per section, ready for the translator.

    Files the author already put in `manuscript/<language>/` are left as they
    are; only what is missing is created.
    """

    from .labels import labels

    if not _LANGUAGE.fullmatch(language):
        raise ValidationError(f"{language!r} is not a language tag (pt-BR, en, es...)")
    if language in book.languages:
        raise ValidationError(f"The book already has {language}", languages=book.languages)
    if not book.sections(book.source_language):
        raise ValidationError("The book has no sections yet: plan and write it in its source language first")
    labels(language)  # refused here if no edition could print this language's labels
    folder = book.manuscript_dir(language)
    manifest = book.root / BOOK_FILENAME
    created = []
    with book_lock(book.root):
        before = manifest.read_text("utf-8")
        try:
            folder.mkdir(parents=True, exist_ok=True)
            meta_path = folder / "meta.yaml"
            if not meta_path.is_file():
                meta_path.write_text(yaml.safe_dump(language_meta(book, meta), allow_unicode=True, sort_keys=False,
                                                    width=100), encoding="utf-8")
                created.append(meta_path)
            for section in book.sections(book.source_language):
                path = folder / f"{section.id}.md"
                if path.is_file():
                    continue
                raw = section.path.read_text("utf-8")
                path.write_text(raw[: len(raw) - len(section.body)], encoding="utf-8")
                created.append(path)
            manifest.write_text(_with_languages(before, [*book.languages, language]), encoding="utf-8")
            load_book(book.root).contents(language)
        except Exception:
            manifest.write_text(before, encoding="utf-8")
            for path in created:
                path.unlink(missing_ok=True)
            raise
        commit(book.root, [manifest, *created], f"Add language {language}" + (f": {reason}" if reason else ""), actor)
    stubs = [p for p in created if p.suffix == ".md"]
    return {"language": language, "sections": len(stubs), "meta_translated": bool(meta),
            "created": [str(p.relative_to(book.root)) for p in created]}


def confirm_translation(book: Book, language: str, section: str, *, actor: Actor,
                        rationale: str = "") -> dict[str, Any]:
    """The author says this translation corresponds to the source as it reads now."""

    if actor.kind != "human":
        raise ValidationError("Only a person confirms that a translation corresponds to its source")
    states = section_states(book, language)
    if section not in states:
        raise NotFoundError(f"No section {section!r} in {language}")
    if states[section]["state"] == "untranslated":
        raise ValidationError(f"{section} has no translation in {language} yet")
    with book_lock(book.root):
        state = read_state(book.root)
        record = {"source_digest": states[section]["source_digest"], "at": now(), "by": actor.public_dict(),
                  "rationale": rationale}
        state.setdefault("translations", {}).setdefault(language, {})[section] = record
        state["history"].append({"at": record["at"], "event": "translation_confirmed", "language": language,
                                 "section": section, "actor": actor.public_dict(), "rationale": rationale})
        commit_state(book.root, state, expected_revision=None, actor=actor,
                     message=f"Confirm the {language} translation of {section} against the current source"
                     + (f": {rationale}" if rationale else ""))
    return {"language": language, "section": section, **record}


def write_glossary(book: Book, text: str, *, actor: Actor, reason: str = "", replace: bool = False) -> dict[str, Any]:
    """glossary.yaml, created; replacing the author's own is the author's act alone."""

    path = book.root / GLOSSARY
    if path.is_file() and not (replace and actor.kind == "human"):
        raise ValidationError(f"{GLOSSARY} exists; it is the author's file — edit it, or replace it yourself")
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or not isinstance(data.get("terms") or [], list):
        raise ValidationError(f"{GLOSSARY} needs a `terms` list")
    with book_lock(book.root):
        path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        try:
            found = glossary(book)
        except Exception:
            path.unlink()
            raise
        commit(book.root, [path], "Glossary: " + (reason or "the book's bilingual decisions"), actor)
    return {"path": GLOSSARY, "terms": len(found.terms), "keep": len(found.keep)}

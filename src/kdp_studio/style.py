"""The writing-vice catalogue as checks (docs/origin, §9).

A *practice* is a rule the book's writing must follow. Each one says whether a
check enforces it (`check`) or whether it still depends on someone reading
(`check: null`) -- the report lists those by name, so the tool is honest about
its own coverage (Cine Toaster's `enforced_by`).

The built-in catalogue is per language (`style/<language>.yaml`); a book adds
its own decisions in `<book>/style.yaml`, with approved exceptions, and may
disable a built-in rule. Prompts to agents and code are frozen literals and
are never checked: they are written for a machine, not a reader.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import resources
from typing import Any, Callable, Iterator

import yaml
from markdown_it.tree import SyntaxTreeNode

from .book import Book, Section
from .markdown import callout, is_comment, parse, plain_text

BOOK_STYLE = "style.yaml"


@dataclass(frozen=True)
class Unit:
    """One paragraph-like piece of reader text, with where it is."""

    text: str
    line: int
    in_exercise: bool
    kind: str  # paragraph | heading | item


@dataclass(frozen=True)
class Practice:
    id: str
    category: str
    rule: str
    why: str = ""
    check: dict[str, Any] | None = None
    allow: tuple[str, ...] = ()
    source: str = "built-in"

    @property
    def enforced(self) -> bool:
        return self.check is not None


@dataclass
class Finding:
    practice: str
    section: str
    line: int
    excerpt: str
    match: str
    message: str = ""

    def public_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class StyleReport:
    language: str
    findings: list[Finding] = field(default_factory=list)
    practices: list[Practice] = field(default_factory=list)
    #: Open engines that ran (or could not, and why).
    engines: dict[str, str] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        by_practice: dict[str, int] = {}
        for finding in self.findings:
            by_practice[finding.practice] = by_practice.get(finding.practice, 0) + 1
        enforced = [p for p in self.practices if p.enforced]
        return {
            "language": self.language,
            "coverage": {"enforced": len(enforced), "total": len(self.practices),
                         "unenforced": [{"id": p.id, "rule": p.rule} for p in self.practices if not p.enforced]},
            "counts": by_practice,
            "practices": [{"id": p.id, "category": p.category, "rule": p.rule, "why": p.why,
                           "enforced": p.enforced, "source": p.source} for p in self.practices],
            "engines": self.engines,
            "findings": [f.public_dict() for f in self.findings],
        }


# ------------------------------------------------------------------ units

def units(markdown: str) -> Iterator[Unit]:
    """Reader text, paragraph by paragraph; prompts, code and comments left out."""

    def walk(node: SyntaxTreeNode, exercise: bool) -> Iterator[Unit]:
        if is_comment(node) or node.type in ("fence", "code_block", "footnote_block"):
            return
        if node.type == "blockquote":
            found = callout(node)
            if found and found.kind == "prompt":
                return
        if node.type == "container_exercise":
            exercise = True
        if node.type in ("paragraph", "heading"):
            # A callout's marker is markup; its title is reader text.
            text = re.sub(r"^\[![a-z-]+\]\s*", "", " ".join(plain_text(node).split()))
            if text:
                line = (node.map[0] + 1) if node.map else 0
                kind = "heading" if node.type == "heading" else "paragraph"
                yield Unit(text, line, exercise, kind)
            return
        for child in node.children:
            yield from walk(child, exercise)

    yield from walk(parse(markdown), False)


# --------------------------------------------------------------- catalogue

def _load(text: str, source: str) -> tuple[list[Practice], dict[str, Any]]:
    data = yaml.safe_load(text) or {}
    practices = [Practice(id=str(p["id"]), category=str(p.get("category", "form")), rule=str(p["rule"]),
                          why=str(p.get("why", "")), check=p.get("check"), allow=tuple(p.get("allow") or ()),
                          source=source) for p in data.get("practices") or []]
    return practices, data


def catalogue(book: Book, language: str) -> tuple[list[Practice], dict[str, Any]]:
    """Built-in practices for the language, then the book's own decisions."""

    practices: list[Practice] = []
    base = language if language in ("pt-BR", "en") else language.split("-")[0]
    path = resources.files(__package__).joinpath("style", f"{base}.yaml")
    if path.is_file():
        practices, _ = _load(path.read_text("utf-8"), "built-in")
    settings: dict[str, Any] = {}
    own = book.root / BOOK_STYLE
    if own.is_file():
        added, settings = _load(own.read_text("utf-8"), "book")
        disabled = set(settings.get("disable") or [])
        practices = [p for p in practices if p.id not in disabled]
        replaced = {p.id for p in added}
        practices = [p for p in practices if p.id not in replaced] + added
    return practices, settings


# ------------------------------------------------------------------ checks

def _excerpt(text: str, start: int, end: int, width: int = 60) -> str:
    left = max(0, start - width)
    right = min(len(text), end + width)
    return ("…" if left else "") + text[left:right] + ("…" if right < len(text) else "")


def _pattern(practice: Practice, section: Section, found: list[Unit]) -> list[Finding]:
    check = practice.check or {}
    flags = re.IGNORECASE if "i" in str(check.get("flags", "")) else 0
    pattern = re.compile(check["pattern"], flags)
    where = check.get("where", "text")
    out: list[Finding] = []
    for unit in found:
        if where == "exercise" and not unit.in_exercise:
            continue
        if where == "outside_exercise" and unit.in_exercise:
            continue
        haystack = unit.text
        for match in pattern.finditer(haystack):
            if where == "paragraph_start" and (match.start() != 0 or unit.kind != "paragraph"):
                continue
            excerpt = _excerpt(haystack, match.start(), match.end())
            if any(allowed in haystack for allowed in practice.allow):
                continue
            out.append(Finding(practice.id, section.id, section_line(section, unit), excerpt, match.group(0)))
    limit = check.get("max_per_section")
    if limit is not None:
        if len(out) <= int(limit):
            return []
        message = f"{len(out)} in this section (at most {limit})"
        return [Finding(practice.id, section.id, out[0].line, out[0].excerpt, out[0].match, message)]
    return out


def section_line(section: Section, unit: Unit) -> int:
    """The line in the file: the body starts after the frontmatter."""

    raw = section.path.read_text("utf-8") if section.path.is_file() else section.body
    offset = raw[: len(raw) - len(section.body)].count("\n") if raw.endswith(section.body) else 0
    return unit.line + offset


def _person_switch(practice: Practice, section: Section, found: list[Unit]) -> list[Finding]:
    text = " ".join(u.text for u in found)
    if not re.search(r"\bvocê\b", text, re.IGNORECASE):
        return []
    out = []
    for unit in found:
        for match in re.finditer(r"\b(?:o|a|do|da|ao|à|pelo|pela) (?:leitor|leitora)\b", unit.text, re.IGNORECASE):
            out.append(Finding(practice.id, section.id, section_line(section, unit),
                               _excerpt(unit.text, match.start(), match.end()), match.group(0),
                               "the section addresses the reader as “você”"))
    return out


def _broken_reference(practice: Practice, section: Section, found: list[Unit], chapters: int) -> list[Finding]:
    out = []
    for unit in found:
        for match in re.finditer(r"\bcap[ií]tulo (\d+)\b|\bchapter (\d+)\b", unit.text, re.IGNORECASE):
            number = int(match.group(1) or match.group(2))
            if number < 1 or number > chapters:
                out.append(Finding(practice.id, section.id, section_line(section, unit),
                                   _excerpt(unit.text, match.start(), match.end()), match.group(0),
                                   f"the book has {chapters} chapters"))
    return out


def _refrain(practice: Practice, section: Section, found: list[Unit], refrains: list[str]) -> list[Finding]:
    out = []
    for refrain in refrains:
        pattern = re.compile(re.escape(refrain), re.IGNORECASE)
        for unit in found:
            for match in pattern.finditer(unit.text):
                out.append(Finding(practice.id, section.id, section_line(section, unit),
                                   _excerpt(unit.text, match.start(), match.end()), match.group(0),
                                   "the thesis restated: demonstrate it in a new situation instead"))
    return out


def check_style(book: Book, language: str, section_ids: list[str] | None = None, *,
                engines: bool = True) -> StyleReport:
    sections = [s for s in book.sections(language) if not section_ids or s.id in section_ids]
    return check_sections(book, language, sections, engines=engines)


def check_sections(book: Book, language: str, sections: list[Section], *, engines: bool = True) -> StyleReport:
    """Check these sections; a section may be a candidate text that is not on disk yet."""

    practices, settings = catalogue(book, language)
    chapters = sum(1 for s in book.sections(language) if s.kind == "chapter")
    report = StyleReport(language, practices=practices)
    special: dict[str, Callable[..., list[Finding]]] = {
        "person_switch": _person_switch,
        "broken_reference": lambda p, s, f: _broken_reference(p, s, f, chapters),
        "refrain": lambda p, s, f: _refrain(p, s, f, list(settings.get("refrains") or [])),
    }
    for section in sections:
        found = list(units(section.body))
        for practice in practices:
            if not practice.enforced:
                continue
            check = practice.check or {}
            if "pattern" in check:
                report.findings.extend(_pattern(practice, section, found))
            elif check.get("builtin") in special:
                report.findings.extend(special[check["builtin"]](practice, section, found))
    if engines:
        _run_engines(book, language, sections, settings, report)
    return report


def _run_engines(book: Book, language: str, sections: list[Section], settings: dict[str, Any],
                 report: StyleReport) -> None:
    from .errors import KdpStudioError
    from .linters import run_languagetool, run_vale

    for name, run in (("vale", run_vale), ("languagetool", run_languagetool)):
        if name not in settings:
            continue
        try:
            found = run(book, language, sections, settings.get(name) or {})
            # The book's own words (names, terms) are not misspellings.
            words = {str(w) for w in settings.get("words") or []}
            spelling = ("MORFOLOGIK", "Spelling")
            found = [f for f in found if not (f.match in words and any(k in f.practice for k in spelling))]
            report.findings.extend(found)
            report.engines[name] = f"ran: {len(found)} finding(s)"
        except KdpStudioError as error:
            report.engines[name] = f"did not run: {error.message}"

"""Agents as manifests: a role declared in data, run by one runtime.

Most agents have the same shape: a role, what they read of the book, a task,
and one of two things to hand back -- a *report* (findings a person reads) or
*edits* (a candidate version of a section). Such an agent is a YAML manifest
(`agents/<id>.yaml`), not a Python module; the catalogue has the usual three
layers: built in, the person's own (`$XDG_DATA_HOME/kdp-studio/agents/`), a
book's (`<book>/agents/`).

What a manifest cannot do is the point. It names what it reads from a fixed
list of *readers*; it gets the web only if it says so; it has no tool, no
file, no command. Its output is one of the two kinds, and each lands the only
way it can: a report through `add_report`, as a dated document in the book;
edits through the same boundary as every reviser, refused where they touch
what must not change and audited for fidelity. An agent that needs more than
this -- the translator's measurements, the designer's build -- stays in code.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Callable

import yaml

from ..book import Book
from ..errors import BookFormatError, NotFoundError, ValidationError
from ..jobs import Progress, kind
from ..model import Model, model_from_env
from ..state import Actor, now
from ..versions import SCOPES, read_section
from .edits import EDITS_RULES, EDITS_SCHEMA, book_context, clean, record

OUTPUTS = ("report", "edits")
SCOPES_OF_WORK = ("section", "book")
SEVERITIES = ("problem", "question", "note")
_ID = re.compile(r"[a-z][a-z0-9-]{1,40}")
#: How much of one long text an agent is given.
LIMIT = 60000

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "body": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "object", "properties": {
            "where": {"type": "string"}, "what": {"type": "string"}, "why": {"type": "string"},
            "severity": {"type": "string", "enum": list(SEVERITIES)}, "suggestion": {"type": "string"}},
            "required": ["where", "what", "why", "severity", "suggestion"]}},
        "could_not": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "body", "findings", "could_not"],
}

REPORT_RULES = (
    " Answer with a report. `body` is Markdown, written for the author in the book's language: what you found, "
    "argued, with no preamble. `findings` lists each point someone must act on: `where` (the passage, quoted "
    "short, or the place), `what`, `why` it matters, a `severity` (`problem`: wrong or missing; `question`: the "
    "author must decide; `note`: worth knowing) and a `suggestion`. `could_not` lists what you were unable to "
    "establish — saying so is a valid answer; never fill a gap with a guess. You change nothing: the author "
    "reads and decides."
)


# ------------------------------------------------------------------ readers

def _cut(text: str, limit: int = LIMIT) -> str:
    return text if len(text) <= limit else text[:limit] + "\n(… cut: too long to give whole)"


def _plan(book: Book, language: str, section: str) -> str:
    lines = []
    for item in book.sections(language):
        mark = "  ← THIS SECTION" if item.id == section else ""
        number = f"{item.number}. " if item.number else ""
        lines.append(f"- {number}{item.title} [{item.id}], {item.words} words{mark}"
                     + (f"\n  covers: {item.synopsis}" if item.synopsis else "")
                     + (f"\n  promise: {item.promise}" if item.promise else ""))
    return "\n".join(lines) or "(the book has no sections yet)"


def _previous(book: Book, language: str, section: str) -> str:
    sections = book.sections(language)
    index = next((i for i, s in enumerate(sections) if s.id == section), 0)
    return sections[index - 1].body.strip()[-3000:] if index else "(this is the first section)"


def _book_text(book: Book, language: str, section: str) -> str:
    sections = book.sections(language)
    share = max(LIMIT * 3 // max(len(sections), 1), 2000)
    return "\n\n".join(f"## {s.number or '·'} {s.title} [{s.id}]\n\n{_cut(s.body.strip(), share)}" for s in sections)


def _research(book: Book, language: str, section: str) -> str:
    from .researcher import dossiers

    return "\n\n".join(f"[{d['path']}]\n{_cut((book.root / d['path']).read_text('utf-8'), 12000)}"
                       for d in dossiers(book)) or "(no research dossier)"


def _sources(book: Book, language: str, section: str) -> str:
    from .researcher import ledger

    return yaml.safe_dump(ledger(book), allow_unicode=True, sort_keys=False) if ledger(book) else "(no source recorded)"


def _glossary(book: Book, language: str, section: str) -> str:
    from ..translation import glossary, glossary_text

    others = [lang for lang in book.languages if lang != book.source_language]
    return "\n".join(f"{book.source_language} → {lang}:\n{glossary_text(glossary(book), book.source_language, lang)}"
                     for lang in others) or "(the book has one language)"


def _style(book: Book, language: str, section: str) -> str:
    from ..style import check_style

    found = check_style(book, language, [section] if section else None, engines=False).findings
    return "\n".join(f"- [{f.practice}] {f.section}:{f.line} “{f.match}” in “{f.excerpt}”" for f in found[:200]) \
        or "(no finding)"


def _continuity(book: Book, language: str, section: str) -> str:
    from ..continuity import repetitions

    found = [r for r in repetitions(book, language)
             if not section or any(o["section"] == section for o in r["occurrences"])]
    return "\n".join(f"- {r['sections']}× “{r['passage']}” in " + ", ".join(o["section"] for o in r["occurrences"])
                     for r in found[:80]) or "(no passage recurs)"


def _meta(book: Book, language: str, section: str) -> str:
    return yaml.safe_dump({"author": book.author, "languages": book.languages, "editions": book.editions,
                           **book.meta(language)}, allow_unicode=True, sort_keys=False)


def _folder(book: Book, name: str, each: int) -> str:
    folder = book.root / name
    if not folder.is_dir():
        return f"(no {name}/ in the book)"
    found = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        relative = path.relative_to(book.root)
        if path.suffix.lower() in (".md", ".txt", ".yaml", ".yml"):
            found.append(f"[{relative}, {path.stat().st_size} bytes]\n{_cut(path.read_text('utf-8', 'replace'), each)}")
        else:
            found.append(f"[{relative}, {path.stat().st_size} bytes — not text, not read]")
    return "\n\n".join(found) or f"({name}/ is empty)"


def _gates(book: Book, language: str, section: str) -> str:
    from ..gates import gate_status

    return "\n".join(f"- {g['kind']} {g['subject']}: {g['state']}" + (" (changed since)" if g["changed_since"] else "")
                     for g in gate_status(book)) or "(no gate opened)"


def _art(book: Book, language: str, section: str) -> str:
    from .. import art

    return "\n".join(f"- {a['id']}: {a.get('purpose', '')}, {a['width']} × {a['height']} px, lettering "
                     f"{a.get('lettering', '?')}" + (f", prompt: {a['prompt']}" if a.get("prompt") else "")
                     for a in art.records(book)) or "(the book has no art yet)"


def _section(book: Book, language: str, section: str) -> str:
    return read_section(book, language, section)["text"]


def _source_section(book: Book, language: str, section: str) -> str:
    return read_section(book, book.source_language, section)["text"]


#: name -> (what the agent is told it is, how it is read, needs a section)
READERS: dict[str, tuple[str, Callable[[Book, str, str], str], bool]] = {
    "section": ("The section", _section, True),
    "source_section": ("The same section in the book's source language", _source_section, True),
    "previous_section": ("How the previous section ends", _previous, True),
    "plan": ("The plan of the whole book", _plan, False),
    "book_text": ("The text of the whole book", _book_text, False),
    "research": ("The research dossiers", _research, False),
    "sources": ("The ledger of sources opened", _sources, False),
    "glossary": ("The glossary", _glossary, False),
    "style_findings": ("What the style checks found", _style, False),
    "continuity": ("Passages that recur across sections", _continuity, False),
    "meta": ("What the book says about itself (meta.yaml)", _meta, False),
    "editorial": ("The author's editorial documents", lambda book, language, section: _folder(book, "editorial", 14000), False),
    "archive": ("The existing material (archive/)", lambda book, language, section: _folder(book, "archive", 9000), False),
    "gates": ("The human gates", _gates, False),
    "art": ("The pictures the book has", _art, False),
}


# ---------------------------------------------------------------- manifests

@dataclass(frozen=True)
class Manifest:
    id: str
    title: str
    role: str
    works_on: str
    reads: tuple[str, ...]
    system: str
    output: str
    web: bool = False
    scope: str = "content"
    knowledge: tuple[str, ...] = ()
    source: str = "built-in"
    origin: dict[str, Any] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "role": self.role, "works_on": self.works_on,
                "reads": list(self.reads), "output": self.output, "web": self.web, "scope": self.scope,
                "knowledge": list(self.knowledge), "source": self.source, "origin": self.origin,
                "system": self.system}


def user_root() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "kdp-studio"


def _roots(book_root: Path | None) -> list[tuple[str, Path]]:
    roots = [("built-in", Path(str(resources.files("kdp_studio").joinpath("agent_manifests")))),
             ("yours", user_root() / "agents")]
    if book_root is not None:
        roots.append(("book", book_root / "agents"))
    return roots


def parse(data: Any, source: str = "") -> Manifest:
    """A manifest from its data, or the reason it is not one."""

    if not isinstance(data, dict):
        raise BookFormatError("An agent manifest is a mapping")
    agent_id = str(data.get("id", ""))
    if not _ID.fullmatch(agent_id):
        raise ValidationError(f"{agent_id!r} is not an agent id (lowercase letters, digits and hyphens)")
    reads = tuple(str(r) for r in data.get("reads") or [])
    unknown = [r for r in reads if r not in READERS]
    if unknown:
        raise ValidationError(f"Agent {agent_id}: no reader named {', '.join(unknown)}", readers=sorted(READERS))
    works_on, output = str(data.get("works_on", "section")), str(data.get("output", "report"))
    if works_on not in SCOPES_OF_WORK:
        raise ValidationError(f"Agent {agent_id}: works_on is one of {', '.join(SCOPES_OF_WORK)}")
    if output not in OUTPUTS:
        raise ValidationError(f"Agent {agent_id}: output is one of {', '.join(OUTPUTS)}")
    if output == "edits" and (works_on != "section" or "section" not in reads):
        raise ValidationError(f"Agent {agent_id}: an agent that answers with edits works on, and reads, one section")
    if works_on == "book" and any(READERS[r][2] for r in reads):
        raise ValidationError(f"Agent {agent_id}: it works on the whole book but reads one section")
    scope = str(data.get("scope", "content"))
    if scope not in SCOPES:
        raise ValidationError(f"Agent {agent_id}: unknown scope {scope!r}", allowed=sorted(SCOPES))
    system = " ".join(str(data.get("system", "")).split())
    if len(system) < 80:
        raise ValidationError(f"Agent {agent_id}: `system` must say who the agent is and how it judges")
    if not str(data.get("role", "")).strip():
        raise ValidationError(f"Agent {agent_id}: `role` says in one line what it is for")
    return Manifest(agent_id, str(data.get("title") or agent_id), str(data["role"]).strip(), works_on, reads, system,
                    output, bool(data.get("web", False)), scope, tuple(str(k) for k in data.get("knowledge") or []),
                    source, dict(data.get("origin") or {}))


def manifests(book_root: Path | None = None) -> dict[str, Manifest]:
    found: dict[str, Manifest] = {}
    for source, root in _roots(book_root):
        for path in sorted(root.glob("*.yaml")) if root.is_dir() else []:
            found[path.stem] = parse({"id": path.stem, **(yaml.safe_load(path.read_text("utf-8")) or {})}, source)
    return found


def get(agent_id: str, book_root: Path | None = None) -> Manifest:
    found = manifests(book_root)
    if agent_id not in found:
        raise NotFoundError(f"No agent named {agent_id!r}", available=sorted(found))
    return found[agent_id]


def knowledge(name: str, book_root: Path | None = None) -> str:
    """A note agents share: `knowledge/<name>.md`, the book's over the person's over the built-in."""

    roots = [Path(str(resources.files("kdp_studio").joinpath("knowledge"))), user_root() / "knowledge"]
    if book_root is not None:
        roots.append(book_root / "knowledge")
    for root in reversed(roots):
        path = root / f"{name}.md"
        if path.is_file():
            return path.read_text("utf-8")
    raise NotFoundError(f"No knowledge note named {name!r}")


# ------------------------------------------------------------------ running

def context(manifest: Manifest, book: Book, language: str, section: str) -> str:
    from ..style import catalogue

    _, settings = catalogue(book, language)
    parts = [f"The book (its intention wins every conflict):\n{book_context(book, settings)}"]
    for name in manifest.knowledge:
        parts.append(f"What you know ({name}):\n{knowledge(name, book.root)}")
    for name in manifest.reads:
        label, reader, _ = READERS[name]
        try:
            parts.append(f"{label}:\n{reader(book, language, section)}")
        except Exception as error:  # noqa: BLE001 - an agent is told what it could not be given
            parts.append(f"{label}: (could not be read: {getattr(error, 'message', error)})")
    return "\n\n".join(parts)


def report_markdown(manifest: Manifest, language: str, section: str, answer: dict[str, Any]) -> str:
    lines = [f"# {manifest.title}: {section or 'the book'}", "",
             f"*{manifest.id}, {now()[:10]}, {language}. A report by an agent: it changes nothing.*", "",
             str(answer.get("summary", "")).strip(), "", str(answer.get("body", "")).strip(), ""]
    findings = answer.get("findings") or []
    if findings:
        lines += ["## Findings", ""]
        for item in findings:
            lines += [f"- **{item['severity']}** — {item['where']}: {item['what']}  ",
                      f"  {item['why']}  ", f"  → {item['suggestion']}"]
        lines.append("")
    if answer.get("could_not"):
        lines += ["## Could not establish", "", *[f"- {item}" for item in answer["could_not"]], ""]
    return "\n".join(lines)


def run(book: Book, agent_id: str, *, language: str = "", section: str = "", instruction: str = "",
        model: Model | None = None, manifest: Manifest | None = None, save: bool = True,
        progress=lambda message: None) -> dict[str, Any]:
    from ..commands import dispatch

    manifest = manifest or get(agent_id, book.root)
    language = language or book.source_language
    if manifest.works_on == "section":
        if not section:
            raise ValidationError(f"{manifest.title} works on one section: say which")
        if section not in {s.id for s in book.sections(language)}:
            raise NotFoundError(f"No section {section!r} in {language}")
    else:
        section = ""
    actor = Actor(manifest.id, "agent")
    prompt = (context(manifest, book, language, section)
              + f"\n\nThe task, in the author's words:\n{instruction.strip() or '(none: do what your role says)'}"
              + f"\n\nWrite in {language}.")
    progress(f"{manifest.title}: reading" + (f" {section}" if section else " the book"))
    chosen = model or model_from_env()
    if manifest.output == "edits":
        system = (manifest.system + f" The declared scope is `{manifest.scope}`: {SCOPES[manifest.scope]}. "
                  + EDITS_RULES)
        answer = clean(chosen.ask(system, prompt, EDITS_SCHEMA, web=manifest.web))
        result = record(book, language, section, answer, agent=actor, scope=manifest.scope,
                        rationale=f"{manifest.title}: " + (instruction.strip() or manifest.role),
                        task={"agent": manifest.id, "instruction": instruction})
        result.pop("candidate", None)
        progress(f"{result['applied']} edit(s)" + (f": version {result['version']}" if result.get("version") else ""))
        return {**result, "agent": manifest.id, "section": section, "language": language}
    answer = chosen.ask(manifest.system + REPORT_RULES, prompt, REPORT_SCHEMA, web=manifest.web)
    findings = answer.get("findings") or []
    outcome = {"agent": manifest.id, "section": section, "language": language,
               "summary": str(answer.get("summary", "")), "findings": findings,
               "could_not": answer.get("could_not") or [],
               "problems": sum(1 for f in findings if f.get("severity") == "problem")}
    if not save:  # a trial: what it would say, kept nowhere
        return {**outcome, "body": answer.get("body", ""), "path": ""}
    saved = dispatch(book, "add_report", {"agent": manifest.id, "subject": section or "book", "language": language,
                                          "text": report_markdown(manifest, language, section, answer)}, actor)
    progress(f"Report kept in {saved['path']}")
    return {**outcome, "path": saved["path"]}


@kind("run_agent", "Run one of the catalogue's agents on a section or on the book: a report, or a candidate version")
def run_agent_job(book: Book, payload: dict[str, Any], actor: Actor, progress: Progress) -> dict[str, Any]:
    return run(book, payload["agent"], language=payload.get("language", ""), section=payload.get("section", ""),
               instruction=payload.get("instruction", ""), progress=progress)


def template(manifest: dict[str, Any]) -> str:
    """A manifest as it is written to disk."""

    ordered = {key: manifest[key] for key in ("title", "role", "works_on", "reads", "web", "output", "scope",
                                              "knowledge", "system", "origin") if manifest.get(key) not in (None, [])}
    return yaml.safe_dump(ordered, allow_unicode=True, sort_keys=False, width=100)

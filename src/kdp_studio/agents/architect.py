"""The architect (docs/origin, §5.2): the book as a progression of capability.

From the intention and the research, it proposes parts and chapters -- each
chapter with what it covers (`synopsis`), what the reader can do after it
(`promise`), and the research it draws on. Not a list of the field's topics:
a chapter without a promise is not ready.

The plan is a candidate, kept in the book's state. The author adopts it (a
person's act) and the chapters are created as stubs, ready for the writer;
or rejects it with a reason and asks again. Once a book has chapters, the
plan is advice: chapters are then added, removed and moved one by one.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

import yaml

from ..book import Book, load_book
from ..errors import NotFoundError, ValidationError
from ..jobs import flow_kind
from ..model import Model, model_from_env
from ..state import Actor, book_lock, commit_state, now, read_state
from ..structure import _stub, slug
from .edits import book_context
from .flow import SimpleWork, again, review_work, run_work
from .researcher import dossiers

AGENT = Actor("architect", "agent")

SYSTEM = (
    "You are the architect of a book. Design parts and chapters as a progression of capability, not as coverage "
    "of a field: for every chapter, `promise` says in one sentence what the reader can do after it that they "
    "could not do before. Each part may have one guiding case that runs through it. `synopsis` says what the "
    "chapter covers and how. `research` lists the slugs of the dossiers it draws on (only existing ones). The "
    "intention wins every conflict; if the research shows a gap, name it in `gaps`. Titles carry no numbering "
    "(no \"Parte I —\", no \"Capítulo 3:\"): numbers and labels are generated. Write in the book's language."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string"},
        "front": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "synopsis": {"type": "string"}}, "required": ["title", "synopsis"]}},
        "parts": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "guiding_case": {"type": "string"},
            "chapters": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string"}, "synopsis": {"type": "string"}, "promise": {"type": "string"},
                "research": {"type": "array", "items": {"type": "string"}}},
                "required": ["title", "synopsis", "promise", "research"]}}},
            "required": ["title", "guiding_case", "chapters"]}},
        "gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["rationale", "front", "parts", "gaps"],
}


def _current(book: Book) -> str:
    lines = []
    for section in book.sections(book.source_language):
        lines.append(f"- {section.id}: {section.title}" + (f" — {section.synopsis}" if section.synopsis else ""))
    return "\n".join(lines) or "(no chapters yet)"


def plan_complete(book: Book, plan: dict[str, Any]) -> list[str]:
    """`plan_complete`: every chapter says what it covers and what the reader can do after it, and names
    only research that exists."""

    known = {d["slug"] for d in dossiers(book)}
    problems = []
    if not plan.get("parts"):
        problems.append("The plan has no parts.")
    for part in plan.get("parts") or []:
        if not part.get("chapters"):
            problems.append(f"The part “{part.get('title', '?')}” has no chapters.")
        for chapter in part.get("chapters") or []:
            title = chapter.get("title", "?")
            if not str(chapter.get("promise", "")).strip():
                problems.append(f"“{title}” has no promise: what can the reader do after it?")
            if not str(chapter.get("synopsis", "")).strip():
                problems.append(f"“{title}” has no synopsis.")
            missing = [name for name in chapter.get("research") or [] if name not in known]
            if missing:
                problems.append(f"“{title}” names research that does not exist: {', '.join(missing)}")
    return problems[:10]


def _work(book: Book, instruction: str = "", *, model: Model | None = None,
          reviewer: Model | None = None) -> SimpleWork:
    from ..style import catalogue

    _, settings = catalogue(book, book.source_language)
    research = "\n".join(f"- {d['slug']}: {d['title']}" for d in dossiers(book)) or "(no research yet)"
    prompt = (f"The book:\n{book_context(book, settings)}\n\nResearch dossiers:\n{research}\n\n"
              f"Current chapters:\n{_current(book)}\n\n"
              f"The author's instruction for the plan:\n{instruction.strip() or '(none: propose the plan)'}")
    chosen = model or model_from_env()

    def ask(request: str, standing: dict[str, Any] | None, error: str) -> dict[str, Any]:
        return chosen.ask(SYSTEM, again(prompt, request, standing, error), SCHEMA)

    def land(plan: dict[str, Any]) -> dict[str, Any]:
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        with book_lock(book.root):
            state = read_state(book.root)
            entry = {"id": plan_id, "state": "candidate", "proposed_at": now(), "proposed_by": AGENT.public_dict(),
                     "instruction": instruction, "plan": plan}
            state.setdefault("plans", {})[plan_id] = entry
            state["history"].append({"at": entry["proposed_at"], "event": "plan_proposed", "plan": plan_id,
                                     "actor": AGENT.public_dict()})
            commit_state(book.root, state, expected_revision=None, actor=AGENT,
                         message=f"Propose {plan_id}: {len(plan.get('parts') or [])} part(s), "
                         f"{sum(len(p['chapters']) for p in plan.get('parts') or [])} chapter(s)")
        chapters = sum(len(p["chapters"]) for p in plan.get("parts") or [])
        return {"plan": plan_id, "parts": len(plan.get("parts") or []), "chapters": chapters,
                "gaps": plan.get("gaps") or [], "summary": plan.get("rationale", "")}

    def review(outcome: dict[str, Any]) -> dict[str, Any]:
        import json

        plan = read_state(book.root)["plans"][outcome["plan"]]["plan"]
        return review_work(reviewer or chosen, title="Architect",
                           role="Designs parts and chapters as a progression of capability, not as coverage of a "
                                "field: judge whether each promise is something a reader can DO, whether the order "
                                "builds, and what a chapter takes that belongs to another.",
                           shown=prompt, answered=json.dumps(plan, ensure_ascii=False, indent=1))

    return SimpleWork("Architect: the plan", ask=ask, land=land, review=review,
                      checks=[("plan_complete", lambda plan: plan_complete(book, plan))])


def propose_plan(book: Book, instruction: str = "", *, model: Model | None = None,
                 progress=lambda message: None) -> dict[str, Any]:
    return run_work(_work(book, instruction, model=model), progress=progress)


def _unnumbered(title: str) -> str:
    """“Parte I — Escolher” → “Escolher”: the label and number are generated."""

    import re

    return re.sub(r"^(?:part|parte|cap[ií]tulo|chapter)\s+[\divxlc]+\s*[—–:.-]\s*", "", title.strip(),
                  flags=re.IGNORECASE) or title


def plans(book: Book) -> list[dict[str, Any]]:
    return sorted(read_state(book.root).get("plans", {}).values(), key=lambda p: p["proposed_at"], reverse=True)


def adopt_plan(book: Book, plan_id: str, *, actor: Actor, rationale: str = "") -> dict[str, Any]:
    if actor.kind != "human":
        raise ValidationError("Only a person adopts a plan; an agent proposes")
    if book.sections(book.source_language):
        raise ValidationError("The book already has chapters: add, remove and move them one by one")
    with book_lock(book.root):
        state = read_state(book.root)
        entry = state.get("plans", {}).get(plan_id)
        if entry is None:
            raise NotFoundError(f"No plan {plan_id!r}")
        if entry["state"] != "candidate":
            raise ValidationError(f"Plan {plan_id} was already {entry['state']}")
        plan = entry["plan"]
        language = book.source_language
        folder = book.manuscript_dir(language)
        folder.mkdir(parents=True, exist_ok=True)
        contents: list[Any] = []
        written = []
        taken: set[str] = set()

        def create(title: str, kind_: str, synopsis: str, promise: str, research: list[str] | None = None) -> str:
            section_id = slug(title)
            base, n = section_id, 2
            while section_id in taken:
                section_id, n = f"{base}-{n}", n + 1
            taken.add(section_id)
            text = _stub(title, kind_, synopsis, promise, research)
            path = folder / f"{section_id}.md"
            path.write_text(text, encoding="utf-8")
            written.append(path)
            return section_id

        for item in plan.get("front") or []:
            contents.append(create(item["title"], "front", item.get("synopsis", ""), ""))
        meta_path = folder / "meta.yaml"
        meta = (yaml.safe_load(meta_path.read_text("utf-8")) if meta_path.is_file() else {}) or {}
        meta["parts"] = {}
        for number, part in enumerate(plan.get("parts") or [], start=1):
            meta["parts"][number] = _unnumbered(part["title"])
            contents.append({"part": number, "sections": [
                create(_unnumbered(c["title"]), "chapter", c["synopsis"], c["promise"], c.get("research"))
                for c in part["chapters"]
            ]})
        meta_path.write_text(yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")
        entry.update({"state": "adopted", "decided_at": now(), "decided_by": actor.public_dict(),
                      "decision_rationale": rationale})
        state["history"].append({"at": entry["decided_at"], "event": "plan_adopted", "plan": plan_id,
                                 "actor": actor.public_dict()})
        from ..structure import write_contents

        manifest_text = (book.root / "book.yaml").read_text("utf-8")
        if "contents:" not in manifest_text:
            (book.root / "book.yaml").write_text(manifest_text.rstrip() + "\ncontents: []\n", encoding="utf-8")
        write_contents(load_book(book.root), copy.deepcopy(contents), actor=actor,
                       reason=f"adopt {plan_id}" + (f": {rationale}" if rationale else ""),
                       also=(*written, meta_path))
        commit_state(book.root, state, expected_revision=None, actor=actor, message=f"Adopt {plan_id}")
    return {"plan": plan_id, "sections": len(written)}


@flow_kind("plan_book", "Architect: propose parts and chapters, each with a synopsis and a promise")
def plan_flow(book: Book, payload: dict[str, Any], progress) -> tuple[Any, dict[str, Any], list]:
    return _work(book, payload.get("instruction", "")), {}, []

"""The meta-agent: it writes other agents, as manifests, and tries each before it is kept.

Asked for an agent -- "someone who checks every chapter opens with a scene"
-- it designs one from what the runtime offers (agents/manifest.py): the
readers it may use, the two kinds of output, and nothing else. It can also
write a *knowledge note* the agent reads, when the role rests on facts worth
keeping in one place.

It cannot widen the boundary it works inside. A manifest names readers from a
fixed list and has no tool, file or command; so whatever the meta-agent
writes, the agent it creates can only read the book and hand back a report or
edits. Before the manifest joins the person's catalogue it is **tried**: run
once on the book (a report is shown and not kept; edits are never tried on
the author's text), and an agent that cannot be parsed or fails its trial is
not catalogued.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..book import Book
from ..errors import KdpStudioError, ValidationError
from ..jobs import Progress, kind
from ..model import Model, model_from_env
from ..state import Actor, now
from . import manifest as manifests

AGENT = Actor("meta-agent", "agent")

SYSTEM = (
    "You design agents for a book production tool. An agent here is a manifest: a role, what it reads of the "
    "book, and a system prompt; it hands back either a `report` (findings a person reads; it changes nothing) or "
    "`edits` (a candidate version of ONE section, which the author compares and adopts). It has no tools and "
    "takes no decision: a person decides. Design the narrowest agent that does what is asked.\n"
    "- `works_on`: `section` (it is run on one section) or `book` (run once on the whole).\n"
    "- `reads`: only the readers listed below, and only those the role needs — every extra one costs attention.\n"
    "- `web`: true only if the role cannot be done without opening pages.\n"
    "- `output`: prefer `report`. Choose `edits` only when the role is to change wording in a section, and then "
    "give `scope`: `wording` (no fact may change), `content` or `structure`.\n"
    "- `system`: the agent's own instructions, in English, written to it in the second person. Say who it is and "
    "what it judges; what it must NOT do (the neighbouring jobs that are someone else's); how it decides in the "
    "hard case; what a good answer contains; and the failure this role exists to prevent. Concrete, not a list of "
    "virtues. It must tell the agent to say what it could not establish rather than guess.\n"
    "- `knowledge_note`: optional. When the role rests on facts or rules worth keeping apart from the prompt, "
    "write them as a short Markdown note; leave it empty otherwise. Do not invent facts for it.\n"
    "If an existing agent already does this, say so in `notes` and design only what is missing. `trial` is the "
    "instruction to try the new agent with."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "role": {"type": "string"},
        "works_on": {"type": "string", "enum": list(manifests.SCOPES_OF_WORK)},
        "reads": {"type": "array", "items": {"type": "string", "enum": sorted(manifests.READERS)}},
        "web": {"type": "boolean"},
        "output": {"type": "string", "enum": list(manifests.OUTPUTS)},
        "scope": {"type": "string", "enum": ["wording", "content", "structure"]},
        "system": {"type": "string"},
        "knowledge_note": {"type": "string"},
        "trial": {"type": "string"},
        "notes": {"type": "string"},
    },
    "required": ["title", "role", "works_on", "reads", "web", "output", "scope", "system", "knowledge_note", "trial",
                 "notes"],
}


def create_agent(book: Book, agent_id: str, brief: str, *, language: str = "", section: str = "",
                 model: Model | None = None, trial_model: Model | None = None, attempts: int = 2,
                 progress=lambda message: None) -> dict[str, Any]:
    if not manifests._ID.fullmatch(agent_id):
        raise ValidationError(f"{agent_id!r} is not an agent id (lowercase letters, digits and hyphens)")
    if not brief.strip():
        raise ValidationError("An agent starts from a brief: what it should do, and for what")
    existing = manifests.manifests(book.root)
    if agent_id in existing:
        raise ValidationError(f"An agent named {agent_id!r} exists; nothing is replaced — give this one another name")
    language = language or book.source_language
    readers = "\n".join(f"- {name}: {label}" + (" (of the section it is run on)" if needs else "")
                        for name, (label, _, needs) in manifests.READERS.items())
    others = "\n".join(f"- {m.id} ({m.output}, on a {m.works_on}): {m.role}" for m in existing.values())
    prompt = (f"The agent's id: {agent_id}\n\nWhat the author asks for:\n{brief.strip()}\n\n"
              f"The readers:\n{readers}\nEvery agent is also given the book's intention and voice.\n\n"
              f"Agents the catalogue already has:\n{others}\n\n"
              "Agents written in code, which a manifest cannot replace: the researcher, the architect, the writer, "
              "the reviser by instruction, the voice reviser, the translator, the designer and the critic of themes.")
    chosen = model or model_from_env()
    problem, answer, trial = "", {}, {}
    for attempt in range(1, attempts + 1):
        progress(f"Designing {agent_id}" + (f" (again: {problem[:80]})" if problem else ""))
        answer = chosen.ask(SYSTEM, prompt if not problem else prompt + f"\n\nYour last design was refused: {problem}",
                            SCHEMA)
        try:
            data = {"id": agent_id, **{k: answer[k] for k in ("title", "role", "works_on", "reads", "web", "output",
                                                              "scope", "system")}}
            note = str(answer.get("knowledge_note") or "").strip()
            if note:
                data["knowledge"] = [agent_id]
            data["origin"] = {"created_by": AGENT.id, "created_at": now(), "brief": brief.strip()}
            made = manifests.parse(data, "yours")
            # Tried before it is kept. Edits are not tried: a trial must not leave a version in the author's book.
            if made.output == "report":
                sections = [s for s in book.sections(language) if s.body.strip()]
                where = section or (sections[0].id if sections else "")
                if made.works_on == "section" and not where:
                    raise ValidationError("There is no written section to try the agent on")
                progress(f"Trying {agent_id}" + (f" on {where}" if made.works_on == "section" else " on the book"))
                trial = _try(book, made, note, language, where, str(answer.get("trial", "")), trial_model or chosen)
            problem = ""
            break
        except KdpStudioError as error:
            problem = error.message
    if problem:
        raise ValidationError(f"The agent {agent_id!r} was not catalogued: {problem}")
    root = manifests.user_root()
    (root / "agents").mkdir(parents=True, exist_ok=True)
    (root / "agents" / f"{agent_id}.yaml").write_text(manifests.template(data), encoding="utf-8")
    if note:
        (root / "knowledge").mkdir(parents=True, exist_ok=True)
        (root / "knowledge" / f"{agent_id}.md").write_text(note + "\n", encoding="utf-8")
    progress(f"{agent_id} is in your catalogue")
    return {"agent": agent_id, "title": made.title, "role": made.role, "works_on": made.works_on,
            "reads": list(made.reads), "output": made.output, "web": made.web, "knowledge_note": bool(note),
            "notes": answer.get("notes", ""), "trial": trial,
            "summary": f"Agent {made.title} ({agent_id}) " + ("tried and " if trial else "") + "catalogued: "
                       + made.role}


def _try(book: Book, made: manifests.Manifest, note: str, language: str, section: str, instruction: str,
         model: Model) -> dict[str, Any]:
    """One run of an agent that is not catalogued yet; nothing is kept in the book."""

    kept: Path | None = None
    if note:  # the note it would read, where the runtime looks for it, for the length of the trial
        kept = manifests.user_root() / "knowledge" / f"{made.id}.md"
        kept.parent.mkdir(parents=True, exist_ok=True)
        kept.write_text(note + "\n", encoding="utf-8")
    try:
        result = manifests.run(book, made.id, language=language, section=section, instruction=instruction,
                               model=model, manifest=made, save=False)
    finally:
        if kept is not None:
            kept.unlink(missing_ok=True)
    return {"on": section or "the book", "summary": result["summary"], "findings": len(result["findings"]),
            "could_not": len(result["could_not"]), "sample": result["findings"][:3]}


def remove_agent(agent_id: str) -> dict[str, Any]:
    root = manifests.user_root()
    path = root / "agents" / f"{agent_id}.yaml"
    if not path.is_file():
        raise ValidationError(f"{agent_id!r} is not in your catalogue (built-in agents cannot be removed)")
    path.unlink()
    (root / "knowledge" / f"{agent_id}.md").unlink(missing_ok=True)
    return {"agent": agent_id}


@kind("create_agent", "Meta-agent: design a new agent as a manifest, try it once, and catalogue it if it holds")
def create_agent_job(book: Book, payload: dict[str, Any], actor: Actor, progress: Progress) -> dict[str, Any]:
    return create_agent(book, payload["id"], payload.get("brief", ""), language=payload.get("language", ""),
                        section=payload.get("section", ""), progress=progress)

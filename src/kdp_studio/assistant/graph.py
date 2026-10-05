"""The editorial assistant: a LangGraph graph behind AG-UI, a CopilotKit CoAgent.

Each turn it is given what the page says the author is looking at (AG-UI
context) and an overview of the book. When a question needs more, it reads --
a few times -- then answers. It may take the screen somewhere (shared state:
that only moves the view), run builds and checks (disposable output), and
*propose* changes to the book. A proposal is put to the author as an
interrupt; only on their yes is it carried out, as a command with an agent
actor. Deciding a gate or adopting a version is not among its actions.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from ..commands import dispatch
from ..gates import KINDS as GATE_KINDS
from ..server import Studio
from ..state import Actor
from ..versions import SCOPES
from .models import Model, ModelUnavailable
from .reads import READS, overview, read

AGENT = Actor("assistant", "agent")
MAX_READS = 4

Assistant = TypedDict("Assistant", {
    "messages": Annotated[list, add_messages],
    "ag-ui": dict,        # what the page sends: its context
    "navigate": dict,     # shared with the page: where to take the author's screen
    "proposal": dict,     # a change to the book waiting for the author's yes
    "notes": list,        # what it looked up during the current turn
    "turn": str,
})

VIEWS = {
    "book": "the book's structure", "section": "one section: read, edit, versions (needs language, section)",
    "version": "a candidate version against the current text (needs version)", "gates": "the human gates",
    "editions": "builds and measured checks", "proofs": "the print pages, to look at",
    "documents": "intentions and editorial documents (document optional)",
}

#: Changes it may propose; each is a command, confirmed by the author first.
PROPOSALS = {
    "propose_version": "propose a new version of a section (needs language, section, scope, rationale, and "
                       "`text` = the complete new Markdown of the section, frontmatter included). It is a "
                       "candidate: the author compares and decides.",
    "open_gate": "open a human gate for the author to decide (needs gate_kind; subject when the kind needs one)",
}
#: Runs at once: builds are disposable and checks only measure.
RUNS = {
    "build": "build an edition (edition print|ebook, language)",
    "check": "measure an edition (edition print|ebook, language)",
}

SYSTEM = (
    "You are the editorial assistant inside KDP Studio, a book production tool. Answer in the author's language, "
    "briefly and concretely. You know only what is under 'The page', 'The book' and 'What you looked up'; never "
    "invent text, sources or results. When a question needs more, set `action` to `read` with `query` one of: "
    + "; ".join(f"`{n}` ({t}; needs: {needs or 'nothing'})" for n, (t, needs, _) in READS.items())
    + ". Read only what the question needs, then answer. "
    "You cannot change the book yourself. You may propose: "
    + "; ".join(f"`{n}`: {t}" for n, t in PROPOSALS.items())
    + ". Version scopes: " + "; ".join(f"`{n}`: {t}" for n, t in SCOPES.items())
    + ". A proposal is not done until the author says yes to the confirmation that follows your reply: present "
    "it as a proposal (\"proponho…\"), never as done. When you propose a version, read the section first and "
    "keep everything outside the declared scope "
    "byte for byte: a changed number, date, name or URL under `wording` is a violation even when it is right. "
    "Gate kinds: " + ", ".join(GATE_KINDS) + ". "
    "You may run at once: " + "; ".join(f"`{n}`: {t}" for n, t in RUNS.items()) + ". "
    "Approving a gate, adopting or rejecting a version and editing text directly are the author's own "
    "decisions: explain, compare, point at problems, never decide for them. "
    "You may take the author's screen somewhere with `navigate` when they ask to see something or when showing "
    "answers better than words: `view` one of " + "; ".join(f"`{n}` ({t})" for n, t in VIEWS.items())
    + ". It only moves the screen, so do it without asking, and say where you took them. "
    "The book's intentions.md wins every conflict; when unsure what the book is for, read it."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "action": {"type": "string", "enum": ["none", "read", *PROPOSALS, *RUNS]},
        "query": {"type": "string", "enum": list(READS)},
        "language": {"type": "string"},
        "section": {"type": "string"},
        "path": {"type": "string"},
        "version": {"type": "string"},
        "edition": {"type": "string", "enum": ["", "print", "ebook"]},
        "scope": {"type": "string", "enum": ["", *SCOPES]},
        "rationale": {"type": "string"},
        "text": {"type": "string"},
        "gate_kind": {"type": "string", "enum": ["", *GATE_KINDS]},
        "subject": {"type": "string"},
        "navigate": {"type": "object", "properties": {
            "view": {"type": "string", "enum": ["", *VIEWS]}, "language": {"type": "string"},
            "section": {"type": "string"}, "version": {"type": "string"}, "document": {"type": "string"}}},
    },
    "required": ["reply", "action"],
}


def page_context(state: dict[str, Any]) -> dict[str, str]:
    """What the page says the author sees: AG-UI Context objects or plain dicts."""

    found: dict[str, str] = {}
    for item in (state.get("ag-ui") or {}).get("context") or []:
        get = (lambda key: item.get(key)) if isinstance(item, dict) else (lambda key: getattr(item, key, None))
        found[str(get("description"))] = str(get("value"))
    return found


def build(model: Model, studio: Studio, checkpointer=None):
    def assistant(state: Assistant) -> dict[str, Any]:
        seen = page_context(state)
        language = seen.get("Language", "") or studio.book.source_language
        human = next((m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None)
        turn = str(getattr(human, "id", "") or len(state["messages"]))
        notes = list(state.get("notes") or []) if state.get("turn") == turn else []
        try:
            book = overview(studio)
        except Exception as error:  # noqa: BLE001
            book = f"(the book could not be read: {getattr(error, 'message', error)})"
        turns = [f"{'Author' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content}"
                 for m in state["messages"][-10:]]
        looked = "\n\n".join(f"[{n['query']} {n['args']}]\n{n['result']}" for n in notes) or "(nothing yet)"
        left = MAX_READS - len(notes)
        prompt = ("The page:\n" + ("\n".join(f"- {k}: {v}" for k, v in seen.items()) or "- (nothing)")
                  + f"\n\nThe book:\n{book}\n\nWhat you looked up this turn ({left} read(s) left):\n{looked}"
                  + "\n\nConversation:\n" + "\n".join(turns))
        try:
            answer = model.ask(SYSTEM, prompt, SCHEMA)
        except ModelUnavailable as error:
            return {"messages": [AIMessage(content=f"Não consegui falar com o modelo: {error.message}")],
                    "proposal": {}, "notes": [], "turn": turn}
        action = answer.get("action", "none")
        args = {k: answer[k] for k in ("language", "section", "path", "version", "edition") if answer.get(k)}
        if action == "read" and left > 0:
            args.setdefault("language", language)
            name = str(answer.get("query", ""))
            return {"notes": notes + [{"query": name, "args": args, "result": read(studio, name, args)}],
                    "turn": turn, "proposal": {}}
        update: dict[str, Any] = {"proposal": {}, "notes": notes, "turn": turn}
        reply = answer.get("reply", "")
        if action in RUNS:
            payload = {"language": answer.get("language") or language, "edition": answer.get("edition") or "print"}
            try:
                result = dispatch(studio.book, action, payload, AGENT)
                reply += "\n\n" + _ran(action, result)
            except Exception as error:  # noqa: BLE001
                reply += f"\n\n(Não deu certo: {getattr(error, 'message', error)})"
        elif action in PROPOSALS:
            update["proposal"] = {
                "action": action, "language": answer.get("language") or language,
                "section": answer.get("section", ""), "scope": answer.get("scope") or "wording",
                "rationale": answer.get("rationale", ""), "text": answer.get("text", ""),
                "kind": answer.get("gate_kind", ""), "subject": answer.get("subject", ""),
            }
        update["messages"] = [AIMessage(content=reply)]
        where = answer.get("navigate") or {}
        if where.get("view") in VIEWS:
            # A fresh id, so asking for the same place twice moves the screen twice.
            keys = ("view", "language", "section", "version", "document")
            update["navigate"] = {**{k: where.get(k) or "" for k in keys}, "id": uuid.uuid4().hex[:8]}
            update["navigate"]["language"] = update["navigate"]["language"] or language
        return update

    def route(state: Assistant) -> str:
        if state.get("proposal"):
            return "confirm"
        last = state["messages"][-1] if state["messages"] else None
        # A read leaves the author's message last: look again before answering.
        return "assistant" if isinstance(last, HumanMessage) else END

    def confirm(state: Assistant) -> dict[str, Any]:
        """Put the proposal to the author; act only on their yes, only through a command."""

        p = state["proposal"]
        if p["action"] == "propose_version":
            question = (f"Registrar uma versão candidata de {p['section']} ({p['language']}, escopo {p['scope']})? "
                        f"Motivo: {p['rationale'].rstrip('. ')}. Ela não muda o texto: você compara e decide depois.")
            payload = {k: p[k] for k in ("language", "section", "scope", "rationale", "text")}
        else:
            question = f"Abrir o portão {p['kind']}{' de ' + p['subject'] if p['subject'] else ''} para você decidir?"
            payload = {"kind": p["kind"], "subject": p["subject"]}
        answer = interrupt({"message": question, "proposal": {k: v for k, v in p.items() if k != "text"}})
        if not (isinstance(answer, dict) and answer.get("approved")):
            return {"messages": [AIMessage(content="Certo, não fiz nada.")], "proposal": {}}
        try:
            result = dispatch(studio.book, p["action"], payload, AGENT)
        except Exception as error:  # noqa: BLE001
            return {"messages": [AIMessage(content=f"O KDP Studio recusou: {getattr(error, 'message', error)}")],
                    "proposal": {}}
        if p["action"] == "propose_version":
            # Show it: the comparison is where the author decides.
            return {"messages": [AIMessage(content=f"Registrei a versão {result['id']}. Abri a comparação.")],
                    "proposal": {},
                    "navigate": {"view": "version", "version": result["id"], "language": p["language"],
                                 "section": p["section"], "document": "", "id": uuid.uuid4().hex[:8]}}
        return {"messages": [AIMessage(content=f"Abri o portão {result['id']}: {result['question']}")],
                "proposal": {}, "navigate": {"view": "gates", "language": p["language"], "section": "",
                                             "version": "", "document": "", "id": uuid.uuid4().hex[:8]}}

    graph = StateGraph(Assistant)
    graph.add_node("assistant", assistant)
    graph.add_node("confirm", confirm)
    graph.add_edge(START, "assistant")
    graph.add_conditional_edges("assistant", route, {"confirm": "confirm", "assistant": "assistant", END: END})
    graph.add_edge("confirm", END)
    return graph.compile(checkpointer=checkpointer)


def _ran(action: str, result: dict[str, Any]) -> str:
    if action == "build":
        return f"Gerei {result['output']}."
    counts = result.get("summary", {})
    return f"Medi {result['target']}: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) + "."

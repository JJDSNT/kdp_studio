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
from ..model import Model, ModelUnavailable
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
    "style": "the writing-vice findings of the whole book", "continuity": "passages that recur across sections",
    "jobs": "background jobs, with their progress and results",
    "translation": "a translated language against its source (needs language = the translated one)",
    "reader": "the built ebook, read as on a device", "templates": "the edition templates and publisher profiles",
    "library": "the other books that can be opened",
    "publish": "what stands between a language and the publisher: freeze, builds, checks, the decision",
}

#: Changes it may propose; each is a command, confirmed by the author first.
PROPOSALS = {
    "propose_version": "propose a new version of a section (needs language, section, scope, rationale, and "
                       "`text` = the complete new Markdown of the section, frontmatter included). It is a "
                       "candidate: the author compares and decides.",
    "open_gate": "open a human gate for the author to decide (needs gate_kind; subject when the kind needs one)",
    "revise_voice": "start the voice reviser on a section, as a background job (needs language, section): it "
                    "fixes the register and form findings and records a candidate version for the author",
    "revise_section": "start the reviser on a section with the author's instruction, as a background job (needs "
                      "language, section, `instruction` in the author's words made precise, scope): the way to "
                      "change any text — prefer it to writing a version yourself",
    "reorder": "move a section before/after another section or into a part (`section` and one of `before`, "
               "`after`, `into`), or a part before/after another part (`part`); needs `rationale`",
    "write_intentions": "write intentions.md from the interview (`text`: the author's intention in the author's "
                        "own words — for whom, from where to where, what the book is NOT, what the reader takes "
                        "away), needs `rationale`",
    "research": "start the researcher on a question (`question`; `title` = a short name): it searches, opens and "
                "records sources into a dossier",
    "plan_book": "start the architect (`instruction` optional): parts and chapters, each with synopsis and promise, "
                 "as a candidate plan the author adopts",
    "write_section": "start the writer on a section (language, section; `instruction` optional): it writes the "
                     "chapter to its synopsis and promise, as a candidate version",
    "add_section": "add a chapter (`title`, `synopsis`, `promise`; place with `before`/`after` a section or `into` "
                   "a part, else at the end; needs `rationale`) as a stub for the writer",
    "remove_section": "take a section out of the book (`section`, needs `rationale`); it is archived, not deleted",
    "add_language": "add a language to the book (`language` = the new one, e.g. en): the translator translates "
                    "the title, part titles and copyright page, and every section starts as a stub",
    "propose_glossary": "start the translator on the book's bilingual glossary (`language` = the target): terms "
                        "and never-translated names; written only when the book has no glossary.yaml",
    "translate_section": "start the translator on one section (`language` = the target, section; `instruction` "
                         "optional): an editorial adaptation as a candidate version, measured against the source",
    "set_theme": "give the book a theme of the catalogue (`title` = the theme's name; needs `rationale`): every "
                 "edition the theme covers takes it; the text is not touched",
    "design_theme": "have the designer draw a NEW theme (`title` = a short lowercase name, `instruction` = the "
                    "brief: what the book is and how its page should feel, `subject` = the existing theme to "
                    "start from, `text` = a web address to look at as an external reference, if the author gave "
                    "one). It is built over the specimen text and, only if it builds, joins the gallery",
    "critique_theme": "have the critic look at a theme's rendered pages (`title` = the theme) and judge them as a "
                      "book designer would: character, hierarchy, what fails in black ink, defects",
    "revise_theme": "have the designer draw one of the author's themes again (`title` = the theme; `instruction` = "
                    "what to change, or empty to answer the critic's last criticism)",
    "generate_art": "have a picture made for the book by an image provider — paid work, so say what it is for "
                    "(`title` = a short id for the picture, `instruction` = what it shows, in English, with no "
                    "words in it: lettering is set by the cover template; `subject` = the id of an existing "
                    "picture to repaint without its lettering, when that is the request)",
    "translate_book": "start the translator on every untranslated or stale section of `language` (the target), "
                      "each as a candidate version; propose it only after the author has read and adopted a "
                      "first translated chapter and the glossary",
}
#: Runs at once: builds are disposable and checks only measure.
RUNS = {
    "build": "build an edition (edition print|ebook|cover, language); the cover's wrap is sized from the built "
             "print interior, so build print first",
    "check": "measure an edition (edition print|ebook|cover, language)",
}

SYSTEM = (
    "You are the editorial assistant inside KDP Studio, a book production tool. Answer in the author's language, "
    "briefly and concretely. You know only what is under 'The page', 'The book' and 'What you looked up'; never "
    "invent text, sources or results. When a question needs more, set `action` to `read` with `query` one of: "
    + "; ".join(f"`{n}` ({t}; needs: {needs or 'nothing'})" for n, (t, needs, _) in READS.items())
    + ". Read only what the question needs, then answer. "
    "The author's flow: an idea; you interview them (for whom, from where to where, what the book is NOT, what "
    "the reader takes away) and, with their words, write intentions.md; research; the architect's plan, which "
    "the author adopts; the writer, chapter by chapter; then review chapter by chapter. The book gains, loses "
    "and reorders chapters at any time. Never derive the intention from a topic or from existing text: ask. "
    "The author works chapter by chapter and commands through you: to change text, start the reviser with a "
    "precise instruction rather than writing a version yourself. The voice is decided for the whole book (its "
    "voice guide), not per chapter. Chapter approval is the author's: you may say a chapter looks ready. "
    "Design: a theme is one name for the print interior, the ebook and the cover; the gallery (`navigate` to "
    "`templates`) shows every theme on the same sample text, in print (colour or black ink, which costs less to "
    "print) and as an ebook. When the author wants another look, first see what the catalogue has (read "
    "`themes`); then either propose `set_theme`, or `design_theme` with a brief in their words. The designer "
    "works from references: internal ones (the themes that exist) and external ones (a page the author points "
    "at, such as a template gallery) — from an external one it takes the design, records the address and its "
    "licence, and copies code only when the licence allows. What it draws is catalogued in the gallery beside "
    "the others; nothing changes in the book until the author takes a theme. A critic — another agent, shown "
    "the pages themselves — judges a theme with a designer's eye; its criticism is advice, shown in the gallery, "
    "and the designer can answer it (`revise_theme`). When the author asks what you think of a theme, do not "
    "improvise an opinion from its description: propose `critique_theme`. "
    "Another language: add it, draft the glossary and let the author read it, translate ONE chapter and let "
    "the author read it in that language, and only then the rest; what the translation report measures (prompt "
    "ids, numbers, URLs, code, glossary terms) is a finding for the author to read, and whether it reads well "
    "is theirs to judge. A translation whose source changed is stale: translate it again. "
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
        "edition": {"type": "string", "enum": ["", "print", "ebook", "cover"]},
        "scope": {"type": "string", "enum": ["", *SCOPES]},
        "rationale": {"type": "string"},
        "text": {"type": "string"},
        "gate_kind": {"type": "string", "enum": ["", *GATE_KINDS]},
        "instruction": {"type": "string"},
        "question": {"type": "string"},
        "title": {"type": "string"},
        "synopsis": {"type": "string"},
        "promise": {"type": "string"},
        "part": {"type": "string"},
        "before": {"type": "string"},
        "after": {"type": "string"},
        "into": {"type": "string"},
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
                "instruction": answer.get("instruction", ""),
                **{k: answer.get(k, "") for k in ("question", "title", "synopsis", "promise")},
                **{k: answer.get(k, "") for k in ("part", "before", "after", "into")},
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
        elif p["action"] == "write_intentions":
            question = f"Gravar isto como o intentions.md do livro?\n\n{p['text']}"
            payload = {"text": p["text"], "reason": p["rationale"]}
        elif p["action"] in ("research", "plan_book", "write_section"):
            if p["action"] == "research":
                question = f"Pôr o pesquisador para investigar: “{p['question']}”?"
                job = {"question": p["question"], "name": p["title"]}
            elif p["action"] == "plan_book":
                question = "Pedir ao arquiteto um plano de partes e capítulos" + (
                    f" ({p['instruction']})" if p["instruction"] else "") + "? Você adota ou não depois."
                job = {"instruction": p["instruction"]}
            else:
                question = f"Pôr o redator para escrever {p['section']}" + (
                    f" ({p['instruction']})" if p["instruction"] else "") + "? Fica como versão candidata."
                job = {"language": p["language"], "section": p["section"], "instruction": p["instruction"]}
            payload = {"kind": p["action"], "payload": job}
        elif p["action"] == "add_section":
            where = (f" antes de {p['before']}" if p["before"] else f" depois de {p['after']}" if p["after"]
                     else f" na parte {p['into']}" if p["into"] else " no fim")
            question = f"Acrescentar o capítulo “{p['title']}”{where}? Promessa: {p['promise'] or '—'}"
            payload = {k: p[k] for k in ("title", "synopsis", "promise", "before", "after", "into") if p.get(k)}
            payload["reason"] = p["rationale"]
        elif p["action"] == "remove_section":
            question = f"Tirar {p['section']} do livro? Ele vai para archive/removed, não é apagado."
            payload = {"section": p["section"], "reason": p["rationale"]}
        elif p["action"] == "revise_section":
            question = (f"Pedir ao revisor esta mudança em {p['section']} ({p['language']}, escopo {p['scope']})? "
                        f"“{p['instruction']}”. Ele deixa uma versão candidata para você comparar.")
            payload = {"kind": "revise_section", "payload": {"language": p["language"], "section": p["section"],
                                                             "instruction": p["instruction"], "scope": p["scope"]}}
        elif p["action"] == "reorder":
            what = p["section"] or f"a parte {p['part']}"
            where = (f"antes de {p['before']}" if p["before"] else f"depois de {p['after']}" if p["after"]
                     else f"para o fim da parte {p['into']}")
            question = f"Mover {what} {where}? Motivo: {p['rationale'].rstrip('. ')}."
            payload = {k: p[k] for k in ("section", "part", "before", "after", "into") if p.get(k)}
            payload["reason"] = p["rationale"]
        elif p["action"] == "revise_voice":
            question = (f"Pôr o revisor de voz para trabalhar em {p['section']} ({p['language']})? "
                        "Ele corrige só registro e forma e deixa uma versão candidata para você comparar.")
            payload = {"kind": "revise_voice", "payload": {"language": p["language"], "section": p["section"]}}
        elif p["action"] == "add_language":
            question = (f"Acrescentar {p['language']} ao livro? O tradutor traduz título, partes e página de "
                        "créditos; cada capítulo começa vazio, à espera da tradução.")
            payload = {"kind": "add_language", "payload": {"language": p["language"], "reason": p["rationale"]}}
        elif p["action"] == "propose_glossary":
            question = (f"Pedir ao tradutor um glossário {studio.book.source_language} → {p['language']}? Ele só é "
                        "gravado se o livro ainda não tiver glossary.yaml; você revisa antes de traduzir.")
            payload = {"kind": "propose_glossary", "payload": {"language": p["language"]}}
        elif p["action"] in ("translate_section", "translate_book"):
            what = p["section"] if p["action"] == "translate_section" else "todos os capítulos pendentes"
            question = f"Pôr o tradutor para traduzir {what} para {p['language']}" + (
                f" ({p['instruction']})" if p["instruction"] else "") + "? Fica como versão candidata."
            job = {"language": p["language"], "instruction": p["instruction"]}
            if p["action"] == "translate_section":
                job["section"] = p["section"]
            payload = {"kind": p["action"], "payload": job}
        elif p["action"] == "set_theme":
            question = (f"Aplicar o tema {p['title']} ao livro? Muda só o nome do template de cada edição no "
                        "book.yaml; o texto não é tocado.")
            payload = {"theme": p["title"], "reason": p["rationale"]}
        elif p["action"] == "design_theme":
            question = (f"Pedir ao designer um tema novo, “{p['title']}”, a partir de {p['subject'] or 'nocturne'}"
                        + (f", olhando {p['text']}" if p["text"] else "") + f"? Briefing: “{p['instruction']}”. "
                        "Ele só entra na galeria se compilar sobre o texto de exemplo.")
            payload = {"kind": "design_theme", "payload": {"name": p["title"], "brief": p["instruction"],
                                                           "based_on": p["subject"] or "nocturne",
                                                           "reference": p["text"], "language": p["language"]}}
        elif p["action"] == "critique_theme":
            question = f"Pedir ao crítico que olhe as páginas do tema {p['title']} e diga o que acha?"
            payload = {"kind": "critique_theme", "payload": {"theme": p["title"], "language": p["language"]}}
        elif p["action"] == "revise_theme":
            question = (f"Pedir ao designer que refaça o tema {p['title']}"
                        + (f": “{p['instruction']}”" if p["instruction"] else " respondendo à última crítica") + "?")
            payload = {"kind": "revise_theme", "payload": {"theme": p["title"], "instruction": p["instruction"],
                                                           "language": p["language"]}}
        elif p["action"] == "generate_art":
            from .. import art

            job = {"id": p["title"], "prompt": p["instruction"], "derived_from": p["subject"],
                   "remove_lettering": bool(p["subject"]), "purpose": "cover"}
            try:
                planned = art.plan(studio.book, job["id"], prompt=job["prompt"], derived_from=job["derived_from"],
                                   remove_lettering=job["remove_lettering"])
            except Exception as error:  # noqa: BLE001
                return {"messages": [AIMessage(content=f"Não dá para pedir essa imagem: "
                                                       f"{getattr(error, 'message', error)}")], "proposal": {}}
            if planned["missing"]:
                return {"messages": [AIMessage(content="O provedor de imagens não está configurado; falta: "
                                                       + ", ".join(planned["missing"]) + ".")], "proposal": {}}
            question = (f"Pedir a imagem art/{planned['id']} ao {planned['provider']} ({planned['width']} × "
                        f"{planned['height']} px)? É trabalho pago: cerca de US$ {planned['estimate_usd']}. "
                        f"Pedido: “{planned['prompt']}”")
            payload = {"kind": "generate_art", "payload": {**job, "seed": planned["seed"]}}
        else:
            question = f"Abrir o portão {p['kind']}{' de ' + p['subject'] if p['subject'] else ''} para você decidir?"
            payload = {"kind": p["kind"], "subject": p["subject"]}
        answer = interrupt({"message": question, "proposal": {k: v for k, v in p.items() if k != "text"}})
        if not (isinstance(answer, dict) and answer.get("approved")):
            return {"messages": [AIMessage(content="Certo, não fiz nada.")], "proposal": {}}
        jobs_ = ("revise_voice", "revise_section", "research", "plan_book", "write_section", "add_language",
                 "propose_glossary", "translate_section", "translate_book", "generate_art", "design_theme",
                 "critique_theme", "revise_theme")
        command = "start_job" if p["action"] in jobs_ else p["action"]
        try:
            result = dispatch(studio.book, command, payload, AGENT)
        except Exception as error:  # noqa: BLE001
            return {"messages": [AIMessage(content=f"O KDP Studio recusou: {getattr(error, 'message', error)}")],
                    "proposal": {}}
        if p["action"] == "propose_version":
            # Show it: the comparison is where the author decides.
            return {"messages": [AIMessage(content=f"Registrei a versão {result['id']}. Abri a comparação.")],
                    "proposal": {},
                    "navigate": {"view": "version", "version": result["id"], "language": p["language"],
                                 "section": p["section"], "document": "", "id": uuid.uuid4().hex[:8]}}
        if p["action"] == "reorder":
            impact = result["impact"].get(p["language"]) or next(iter(result["impact"].values()), {})
            moved = len(impact.get("renumbered", {}))
            refs = impact.get("references", [])
            text = f"Feito: a ordem mudou e {moved} capítulo(s) trocaram de número."
            if refs:
                text += " Estas remissões agora apontam para outro capítulo:\n" + "\n".join(
                    f"- {r['section']}:{r['line']} diz “{r['says']}”, que agora é o {r['now']}" for r in refs)
            return {"messages": [AIMessage(content=text)], "proposal": {},
                    "navigate": {"view": "book", "language": p["language"], "section": "", "version": "",
                                 "document": "", "id": uuid.uuid4().hex[:8]}}
        if p["action"] == "set_theme":
            return {"messages": [AIMessage(content=f"O livro agora usa o tema {p['title']} em "
                                                   f"{', '.join(result['editions'])}. Reconstrua as edições para "
                                                   "ver no seu texto.")],
                    "proposal": {}, "navigate": {"view": "templates", "language": p["language"], "section": "",
                                                 "version": "", "document": "", "id": uuid.uuid4().hex[:8]}}
        if p["action"] in ("add_section", "remove_section", "write_intentions"):
            done = {"add_section": f"Acrescentei {result.get('section', '')}: o redator pode escrevê-lo quando você "
                                   "quiser.",
                    "remove_section": f"Tirei {p['section']} do livro (arquivado em archive/removed).",
                    "write_intentions": "Gravei o intentions.md. Quando estiver de acordo, aprove o portão de "
                                        "intenção."}[p["action"]]
            view = "documents" if p["action"] == "write_intentions" else "book"
            return {"messages": [AIMessage(content=done)], "proposal": {},
                    "navigate": {"view": view, "language": p["language"], "section": "", "version": "",
                                 "document": "intentions.md" if view == "documents" else "", "id": uuid.uuid4().hex[:8]}}
        if p["action"] in jobs_:
            who = {"revise_voice": "revisor de voz", "revise_section": "revisor", "research": "pesquisador",
                   "plan_book": "arquiteto", "write_section": "redator",
                   "generate_art": "pedido de imagem", "design_theme": "designer",
                   "revise_theme": "designer", "critique_theme": "crítico"}.get(p["action"], "tradutor")
            return {"messages": [AIMessage(content=f"O {who} começou ({result['id']}). O resultado aparece "
                                                   "em Tarefas quando ficar pronto.")],
                    "proposal": {}, "navigate": {"view": "jobs", "language": p["language"], "section": "",
                                                 "version": "", "document": "", "id": uuid.uuid4().hex[:8]}}
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

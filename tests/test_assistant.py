import pytest

pytest.importorskip("langgraph")

from langchain_core.messages import HumanMessage  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from kdp_studio.assistant.graph import build  # noqa: E402
from kdp_studio.server import Studio  # noqa: E402
from kdp_studio.state import read_state  # noqa: E402


class Scripted:
    """A model that answers from a script and records what it was shown."""

    name = "scripted"

    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts = []

    def available(self):
        return ""

    def ask(self, system, prompt, schema):
        self.prompts.append(prompt)
        return self.answers.pop(0)


def run(graph, text, thread="t"):
    config = {"configurable": {"thread_id": thread}}
    state = {"messages": [HumanMessage(text)],
             "ag-ui": {"context": [{"description": "View", "value": "section"},
                                   {"description": "Language", "value": "en"},
                                   {"description": "Section", "value": "01-first-light"}]}}
    return graph.invoke(state, config), config


def test_it_reads_then_answers_with_what_the_page_shows(sample):
    model = Scripted([
        {"reply": "", "action": "read", "query": "section", "section": "01-first-light"},
        {"reply": "It opens in Lisbon.", "action": "none"},
    ])
    graph = build(model, Studio(sample), MemorySaver())
    result, _ = run(graph, "Where does chapter 1 open?")
    assert result["messages"][-1].content == "It opens in Lisbon."
    assert "- Section: 01-first-light" in model.prompts[0]
    assert "7 Rua Augusta" in model.prompts[1]


def test_a_proposal_waits_for_the_author_and_is_recorded_as_an_agent(sample):
    text = (sample / "manuscript" / "en" / "01-first-light.md").read_text().replace("opened", "first opened")
    model = Scripted([{"reply": "Here is a smoother opening.", "action": "propose_version",
                       "section": "01-first-light", "scope": "wording", "rationale": "smoother", "text": text}])
    graph = build(model, Studio(sample), MemorySaver())
    result, config = run(graph, "Make the opening smoother")
    assert graph.get_state(config).interrupts
    assert not read_state(sample).get("versions")
    result = graph.invoke(Command(resume={"approved": True}), config)
    versions = list(read_state(sample)["versions"].values())
    assert versions[0]["proposed_by"] == {"id": "assistant", "kind": "agent"}
    assert result["navigate"]["view"] == "version"
    # The text itself is untouched until the author adopts.
    assert "first opened" not in (sample / "manuscript" / "en" / "01-first-light.md").read_text()


def test_a_no_does_nothing(sample):
    model = Scripted([{"reply": "Open the intention gate?", "action": "open_gate", "gate_kind": "intention"}])
    graph = build(model, Studio(sample), MemorySaver())
    _, config = run(graph, "Let's settle the intention")
    result = graph.invoke(Command(resume={"approved": False}), config)
    assert result["messages"][-1].content == "Certo, não fiz nada."
    assert not read_state(sample)["gates"]


def test_moving_the_screen_needs_no_confirmation(sample):
    model = Scripted([{"reply": "Here are the gates.", "action": "none", "navigate": {"view": "gates"}}])
    graph = build(model, Studio(sample), MemorySaver())
    result, config = run(graph, "Show me the gates")
    assert result["navigate"]["view"] == "gates" and result["navigate"]["language"] == "en"
    assert not graph.get_state(config).interrupts

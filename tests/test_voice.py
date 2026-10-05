import json

from kdp_studio import jobs
from kdp_studio.agents.voice import apply_edits, revise
from kdp_studio.book import load_book
from kdp_studio.state import Actor, read_state
from kdp_studio.versions import version_report
from test_style import portuguese

TEXT = """---
title: T
---

Vou vê-lo amanhã.

> [!prompt] EX-01-01
>
> Quero vê-lo funcionando.
"""


def test_edits_outside_the_scope_are_refused():
    edits = [{"find": "Vou vê-lo amanhã.", "replace": "Vou ver o agente amanhã.", "practice": "x", "why": ""},
             {"find": "Quero vê-lo funcionando.", "replace": "Quero ver.", "practice": "x", "why": ""},
             {"find": "vê-lo", "replace": "ver", "practice": "x", "why": ""},
             {"find": "title: T", "replace": "title: U", "practice": "x", "why": ""}]
    text, applied, refused = apply_edits(TEXT, edits)
    assert [e["replace"] for e in applied] == ["Vou ver o agente amanhã."]
    assert [r["reason"] for r in refused] == ["touches a prompt, code or the frontmatter",
                                              "passage found 2 times", "touches a prompt, code or the frontmatter"]
    assert text == TEXT.replace("Vou vê-lo amanhã.", "Vou ver o agente amanhã.")


class Scripted:
    name = "scripted"

    def available(self):
        return ""

    def ask(self, system, prompt, schema):
        assert "vê-lo" in prompt and "EX-01-01" in prompt
        return {"edits": [{"find": "Você vai vê-lo amanhã", "replace": "Você vai ver o agente amanhã",
                           "practice": "enclise-infinitivo", "why": "objeto explícito"}],
                "skipped": [], "summary": "Uma ênclise."}


def test_the_reviser_records_a_wording_candidate(sample):
    book = portuguese(sample)
    result = revise(book, "pt-BR", "01-first-light", model=Scripted())
    report = version_report(book, result["version"])
    assert report["scope"] == "wording" and report["proposed_by"]["id"] == "voice-reviser"
    assert not report["violations"]
    assert json.loads(report["task"])["applied"][0]["practice"] == "enclise-infinitivo"
    assert result["remaining_in_candidate"] < result["findings_before"]
    # The section itself is untouched until the author adopts.
    assert "vê-lo" in (sample / "manuscript" / "pt-BR" / "01-first-light.md").read_text()


def test_a_job_records_its_result_and_a_dead_runtime_marks_it_interrupted(sample, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    book = load_book(sample)

    @jobs.kind("echo", "test job")
    def echo(book, payload, actor, progress):
        progress("echoing")
        return {"echo": payload["value"]}

    job = jobs.start(book, "echo", {"value": 7}, Actor("author"), wait=True)
    assert job["state"] == "done" and job["result"] == {"echo": 7}
    assert job["progress"][0]["message"] == "echoing"
    stuck = jobs.start(book, "echo", {"value": 8}, Actor("author"), wait=True)
    store = jobs._read(book)
    store[stuck["id"]]["state"] = "running"
    jobs._write(book, store)
    jobs.reconcile(book)
    assert jobs.get_job(book, stuck["id"])["state"] == "interrupted"
    assert not read_state(sample).get("versions")


class Instructed:
    name = "instructed"

    def available(self):
        return ""

    def ask(self, system, prompt, schema):
        assert "Shorten the opening" in prompt and "[intentions.md" in prompt
        return {"edits": [{"find": "On 12 March 1998 the workshop opened at 7 Rua Augusta, in Lisbon.",
                           "replace": "The workshop opened in Lisbon on 12 March 1998.", "practice": "instruction",
                           "why": "shorter"}], "skipped": [], "summary": "Shorter opening."}


def test_the_reviser_follows_an_instruction_as_a_candidate(sample):
    from kdp_studio.agents.reviser import revise_section

    book = load_book(sample)
    result = revise_section(book, "en", "01-first-light", "Shorten the opening", "content", model=Instructed())
    report = version_report(book, result["version"])
    assert report["proposed_by"]["id"] == "reviser" and report["scope"] == "content"
    assert report["rationale"].startswith("Shorten the opening")
    # Under `content`, the address that disappeared is reported, not hidden.
    assert ("number", "7", 1) in [tuple(f) for f in report["fidelity"]["facts_removed"]]


def test_the_voice_approved_on_a_pilot_chapter_guides_every_chapter(sample):
    from kdp_studio.agents.edits import approved_voice, book_context
    from kdp_studio.gates import decide_gate, open_gate

    book = load_book(sample)
    assert approved_voice(book) is None
    gate = open_gate(book, "voice", "01-first-light", actor=Actor("author"))
    decide_gate(book, gate["id"], "approved", actor=Actor("author"))
    context = book_context(book, {})
    assert "01-first-light — the pilot chapter whose voice the author approved for the whole book" in context
    assert "7 Rua Augusta" in context

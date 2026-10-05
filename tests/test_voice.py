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

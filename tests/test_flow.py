"""From an idea to a written chapter, with scripted models."""

import subprocess

import pytest

from kdp_studio.agents.architect import adopt_plan, propose_plan
from kdp_studio.agents.researcher import ledger, research
from kdp_studio.agents.writer import write_section
from kdp_studio.book import load_book
from kdp_studio.cli import main
from kdp_studio.errors import ValidationError
from kdp_studio.state import Actor
from kdp_studio.structure import add_section, remove_section
from kdp_studio.versions import adopt_version, version_report

AUTHOR = Actor("author")


class Answers:
    name = "answers"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def available(self):
        return ""

    def ask(self, system, prompt, schema, *, web=False):
        self.calls.append({"prompt": prompt, "web": web})
        return self.answers.pop(0)


@pytest.fixture
def new_book(tmp_path):
    root = tmp_path / "jardim"
    assert main(["new", str(root), "--title", "Jardins de Varanda", "--author", "A. Autora",
                 "--idea", "Um livro para quem mora em apartamento e quer plantar comida."]) == 0
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root)
    return root


def test_a_new_book_starts_empty_with_the_idea(new_book):
    book = load_book(new_book)
    assert book.sections("pt-BR") == []
    assert "plantar comida" in (new_book / "intentions.md").read_text()


def test_research_records_opened_sources_and_what_was_not_found(new_book):
    model = Answers({"summary": "Luz é o limite.", "findings": [
        {"claim": "Tomate pede 6 horas de sol.", "sources": ["https://x.org/a"], "confidence": "verified"}],
        "sources": [{"url": "https://x.org/a", "title": "Guia", "says": "6 horas de sol direto."}],
        "not_found": ["Dados de varandas voltadas ao sul no Brasil."]})
    result = research(load_book(new_book), "Quanto sol uma horta de varanda precisa?", model=model)
    assert model.calls[0]["web"] is True
    dossier = (new_book / result["dossier"]).read_text()
    assert "## Achados" in dossier and "## Não encontrado" in dossier and "https://x.org/a" in dossier
    assert ledger(load_book(new_book))[0]["opened"]


PLAN = {"rationale": "Do vaso ao prato.", "front": [{"title": "Antes de começar", "synopsis": "O que esperar."}],
        "parts": [{"title": "A varanda", "guiding_case": "a varanda da Ana", "chapters": [
            {"title": "Ler a luz", "synopsis": "Medir o sol.", "promise": "Saber o que cabe na sua varanda.",
             "research": []},
            {"title": "O primeiro vaso", "synopsis": "Plantar.", "promise": "Plantar sem matar.", "research": []}]}],
        "gaps": []}


def test_a_plan_is_a_candidate_until_the_author_adopts_it(new_book):
    book = load_book(new_book)
    plan = propose_plan(book, model=Answers(PLAN))
    assert load_book(new_book).sections("pt-BR") == []
    with pytest.raises(ValidationError, match="Only a person"):
        adopt_plan(book, plan["plan"], actor=Actor("architect", "agent"))
    adopt_plan(book, plan["plan"], actor=AUTHOR)
    sections = load_book(new_book).sections("pt-BR")
    assert [s.title for s in sections] == ["Antes de começar", "Ler a luz", "O primeiro vaso"]
    assert sections[1].number == 1 and sections[1].promise == "Saber o que cabe na sua varanda."
    with pytest.raises(ValidationError, match="already has chapters"):
        adopt_plan(load_book(new_book), propose_plan(load_book(new_book), model=Answers(PLAN))["plan"], actor=AUTHOR)


def test_the_writer_writes_to_the_promise_and_keeps_the_frontmatter(new_book):
    book = load_book(new_book)
    adopt_plan(book, propose_plan(book, model=Answers(PLAN))["plan"], actor=AUTHOR)
    book = load_book(new_book)
    model = Answers({"body": "## O sol da tarde\\n\\nOlhe para a varanda às três da tarde.", "notes": "ok",
                     "to_check": []})
    result = write_section(book, "pt-BR", "ler-a-luz", model=model)
    prompt = model.calls[0]["prompt"]
    assert "← THIS CHAPTER" in prompt and "Plantar sem matar." in prompt and "plantar comida" in prompt
    report = version_report(book, result["version"])
    assert report["scope"] == "content" and report["proposed_by"]["id"] == "writer"
    adopt_version(book, result["version"], actor=AUTHOR)
    text = (new_book / "manuscript" / "pt-BR" / "ler-a-luz.md").read_text()
    assert text.startswith("---\ntitle: Ler a luz\n") and "Olhe para a varanda" in text


def test_the_book_gains_and_loses_chapters(new_book):
    book = load_book(new_book)
    adopt_plan(book, propose_plan(book, model=Answers(PLAN))["plan"], actor=AUTHOR)
    added = add_section(load_book(new_book), title="Regar sem afogar", synopsis="Água.", promise="Regar certo.",
                        after="o-primeiro-vaso", actor=AUTHOR, reason="faltava")
    assert [s.id for s in load_book(new_book).sections("pt-BR")][-1] == added["section"]
    remove_section(load_book(new_book), section="ler-a-luz", actor=AUTHOR, reason="vai para o apêndice")
    assert "ler-a-luz" not in [s.id for s in load_book(new_book).sections("pt-BR")]
    assert list((new_book / "archive" / "removed" / "pt-BR").glob("*-ler-a-luz.md"))

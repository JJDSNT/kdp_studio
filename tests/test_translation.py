"""A second language: stubs, the translator's candidates, and what is measured of them."""

import json

import pytest

from kdp_studio.agents.translator import propose_glossary, translate_book, translate_meta, translate_section
from kdp_studio.book import load_book
from kdp_studio.cli import main
from kdp_studio.commands import dispatch
from kdp_studio.errors import NotFoundError, ValidationError
from kdp_studio.state import Actor
from kdp_studio.structure import add_part, add_section
from kdp_studio.translation import (Glossary, Term, add_language, compare_translation, glossary, report,
                                    section_states)
from kdp_studio.versions import adopt_version, save_section, version_report

AUTHOR = Actor("author")
TRANSLATOR = Actor("translator", "agent")

BODY = """Em 12 de março de 1998 a oficina abriu na Rua Augusta, 7, em Lisboa.

## Uma seção

Texto com **negrito**, *itálico*, `code` e uma nota.[^n]

> [!concept] Um destaque
> O corpo vem depois da linha do título.

> [!framework] Três perguntas
>
> **1. O que deve existir no fim?**
> Descreva o resultado.
>
> **2. Como você vai saber que funcionou?**
> Combine a prova.

<!-- Uma nota editorial: nunca chega a uma edição. -->

[^n]: Uma nota de rodapé, com fonte: https://example.org/source.
"""


class Answers:
    name = "answers"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def available(self):
        return ""

    def ask(self, system, prompt, schema, *, web=False):
        self.prompts.append(prompt)
        return self.answers.pop(0)


def translated(body=BODY, title="Primeira luz"):
    return {"title": title, "body": body, "notes": "ok", "terms": [{"source": "workshop", "target": "oficina"}],
            "adaptations": [{"source": "12 March 1998", "target": "12 de março de 1998", "why": "date order"}]}


@pytest.fixture
def bilingual(sample):
    add_language(load_book(sample), "pt-BR", actor=AUTHOR, reason="a Portuguese edition",
                 meta={"title": "O Livro de Amostra", "parts": {"1": "Fazer coisas", "epilogue": "Depois"}})
    return sample


def test_a_language_starts_as_stubs_with_its_own_identifier(sample):
    before = (sample / "book.yaml").read_text()
    result = add_language(load_book(sample), "pt-BR", actor=AUTHOR, meta={"title": "O Livro de Amostra"})
    after = (sample / "book.yaml").read_text()
    assert after == before.replace("languages: [en]", "languages: [en, pt-BR]")
    book = load_book(sample)
    assert result["sections"] == 4 and [s.id for s in book.sections("pt-BR")] == [s.id for s in book.sections("en")]
    stub = (sample / "manuscript" / "pt-BR" / "01-first-light.md").read_text()
    assert stub == "---\ntitle: First light\n---\n"
    assert book.meta("pt-BR")["title"] == "O Livro de Amostra"
    assert book.meta("pt-BR")["identifier"].startswith("urn:uuid:")
    assert set(s["state"] for s in section_states(book, "pt-BR").values()) == {"untranslated"}
    found = {f["id"]: f for f in report(book, "pt-BR")["meta"]}
    assert found["meta-title"]["verdict"] == "pass" and found["meta-parts"]["verdict"] == "warn"
    assert "identical to the source: 1, epilogue" in found["meta-parts"]["detail"]


def test_a_language_is_refused_when_it_cannot_be_printed_or_already_exists(sample):
    with pytest.raises(NotFoundError, match="No labels"):
        add_language(load_book(sample), "xx", actor=AUTHOR)
    with pytest.raises(ValidationError, match="already has en"):
        add_language(load_book(sample), "en", actor=AUTHOR)
    assert not (sample / "manuscript" / "xx").exists()
    assert "xx" not in (sample / "book.yaml").read_text()


def test_what_must_survive_a_translation_is_measured():
    source = "---\ntitle: T\n---\n\nOn the 14th it cost 1,250.50 in 3.5 days: see https://a.org/x and `run.sh`.\n\n" \
             "> [!prompt] EX-01-01\n>\n> Write it.\n"
    good = "---\ntitle: T\n---\n\nNo dia 14 custou 1.250,50 em 3,5 dias: veja https://a.org/x e `run.sh`.\n\n" \
           "> [!prompt] EX-01-01\n>\n> Escreva.\n"
    found = {f.id: f for f in compare_translation(source, good, source_language="en", language="pt-BR")}
    assert {f.verdict for f in found.values()} == {"pass"}

    bad = "---\ntitle: T\n---\n\nNo dia 14 custou 1.250,50 em 4 dias: veja `executar.sh`.\n\n" \
          "> [!prompt] EX-01-02\n>\n> Escreva.\n"
    found = {f.id: f for f in compare_translation(source, bad, source_language="en", language="pt-BR")}
    assert found["prompts"].verdict == "fail" and found["prompts"].measured == "EX-01-02"
    # The changed prompt id shows here too: its digits are numbers of the text.
    assert found["numbers"].verdict == "warn"
    assert found["numbers"].detail == "only in the source: 1, 3.5; only in the translation: 2, 4"
    assert found["urls"].verdict == "warn" and "https://a.org/x" in found["urls"].detail
    assert found["code"].verdict == "warn"


def test_the_glossary_is_counted_term_by_term():
    terms = Glossary((Term({"en": ("agent", "agents"), "pt-BR": ("agente", "agentes")}),
                      Term({"en": ("workflow",), "pt-BR": ("fluxo",)})), keep=("Codex",), present=True)
    source = "---\ntitle: A\n---\n\nAn agent runs the workflow in Codex. Two agents agree.\n"
    target = "---\ntitle: B\n---\n\nUm agente roda o processo no Codex. Dois agentes concordam. Codex de novo.\n"
    found = {f.id: f for f in compare_translation(source, target, source_language="en", language="pt-BR",
                                                  terms=terms)}
    assert found["glossary"].verdict == "warn" and found["glossary"].measured == "1 of 2 used in the source"
    assert found["glossary"].detail == "workflow ×1 → fluxo ×0"
    assert found["kept-names"].detail == "Codex ×1 → ×2"


def test_the_translator_proposes_a_candidate_tied_to_its_source(bilingual):
    book = load_book(bilingual)
    model = Answers(translated())
    result = translate_section(book, "pt-BR", "01-first-light", model=model)
    assert "On 12 March 1998" in model.prompts[0] and "Translate from en into pt-BR" in model.prompts[0]
    report_ = version_report(book, result["version"])
    assert report_["proposed_by"]["id"] == "translator" and report_["text"].startswith("---\ntitle: Primeira luz\n---")
    assert json.loads(report_["task"])["adaptations"][0]["why"] == "date order"
    assert result["checks"] == {"pass": 16} and result["findings"] == []
    assert section_states(book, "pt-BR")["01-first-light"] == {
        "state": "untranslated", "candidates": 1, "recorded": None,
        "source_digest": section_states(book, "pt-BR")["01-first-light"]["source_digest"]}

    adopt_version(book, result["version"], actor=AUTHOR)
    assert section_states(book, "pt-BR")["01-first-light"]["state"] == "translated"
    assert load_book(bilingual).sections("pt-BR")[1].title == "Primeira luz"


def test_a_translation_goes_stale_when_its_source_changes(bilingual):
    book = load_book(bilingual)
    result = translate_section(book, "pt-BR", "01-first-light", model=Answers(translated()))
    adopt_version(book, result["version"], actor=AUTHOR)
    source = bilingual / "manuscript" / "en" / "01-first-light.md"
    from kdp_studio.fidelity import digest

    save_section(book, "en", "01-first-light", source.read_text().replace("Lisbon", "Porto"),
                 expected_digest=digest(source.read_bytes()), actor=AUTHOR, reason="it was Porto")
    assert section_states(book, "pt-BR")["01-first-light"]["state"] == "stale"
    with pytest.raises(ValidationError, match="An agent may not run"):
        dispatch(book, "confirm_translation", {"language": "pt-BR", "section": "01-first-light"}, TRANSLATOR)
    # The translator is given what stands, to keep what still corresponds.
    model = Answers(translated(BODY.replace("Lisboa", "Porto")))
    again = translate_section(book, "pt-BR", "01-first-light", model=model)
    assert "The current translation" in model.prompts[0] and "em Lisboa" in model.prompts[0]
    adopt_version(book, again["version"], actor=AUTHOR)
    assert section_states(book, "pt-BR")["01-first-light"]["state"] == "translated"


def test_the_author_confirms_a_translation_made_by_hand(bilingual):
    book = load_book(bilingual)
    path = bilingual / "manuscript" / "pt-BR" / "03-what-remains.md"
    from kdp_studio.fidelity import digest

    save_section(book, "pt-BR", "03-what-remains", "---\ntitle: O que fica\n---\n\nO que fica é o que foi feito.\n",
                 expected_digest=digest(path.read_bytes()), actor=AUTHOR)
    assert section_states(book, "pt-BR")["03-what-remains"]["state"] == "unrecorded"
    dispatch(book, "confirm_translation", {"language": "pt-BR", "section": "03-what-remains"}, AUTHOR)
    assert section_states(book, "pt-BR")["03-what-remains"]["state"] == "translated"


def test_the_whole_book_is_translated_section_by_section(bilingual):
    book = load_book(bilingual)
    model = Answers(translated("Um prefácio.", "Prefácio"), translated(), {"broken": True},
                    translated("O que fica é o que foi feito.", "O que fica"))
    result = translate_book(book, "pt-BR", model=model)
    assert [t["section"] for t in result["translated"]] == ["00-preface", "01-first-light", "03-what-remains"]
    assert [f["section"] for f in result["failed"]] == ["02-the-workshop"]
    # The next section is told the title the previous one chose, though nobody adopted it yet.
    assert "“Why this sample exists” → “Prefácio”" in model.prompts[1] and "Um prefácio." in model.prompts[1]
    assert result["terms_outside_the_glossary"] == [{"source": "workshop", "target": "oficina"}]
    states = section_states(book, "pt-BR")
    assert states["00-preface"]["candidates"] == 1 and states["02-the-workshop"]["candidates"] == 0


def test_meta_and_glossary_are_drafted_for_the_author(sample):
    book = load_book(sample)
    meta = translate_meta(book, "pt-BR", model=Answers({
        "title": "O Livro de Amostra", "subtitle": "Cada construção, uma vez", "tagline": "", "colophon": "**x**",
        "cover_line": "Um exemplo que se lê como livro",
        "parts": [{"id": "1", "title": "Fazer coisas"}, {"id": "9", "title": "não existe"}], "notes": "n"}))
    assert meta["meta"]["parts"] == {"1": "Fazer coisas"} and "tagline" not in meta["meta"]
    assert meta["meta"]["cover"] == {"line": "Um exemplo que se lê como livro"}
    from kdp_studio.translation import language_meta

    started = language_meta(book, meta["meta"])["cover"]
    assert started["line"] == "Um exemplo que se lê como livro" and started["back"].startswith("A book is")
    draft = propose_glossary(book, "pt-BR", model=Answers({
        "terms": [{"source": ["workshop", "workshops"], "target": ["oficina", "oficinas"], "note": "not ateliê"}],
        "keep": ["Rua Augusta"], "notes": ""}))
    dispatch(book, "write_glossary", {"text": draft["glossary"]}, TRANSLATOR)
    found = glossary(load_book(sample))
    assert found.pairs("en", "pt-BR") == [(("workshop", "workshops"), ("oficina", "oficinas"), "not ateliê")]
    assert found.keep == ("Rua Augusta",)
    with pytest.raises(ValidationError, match="the author's file"):
        dispatch(book, "write_glossary", {"text": draft["glossary"], "replace": True}, TRANSLATOR)


def test_a_book_in_two_languages_gains_chapters_and_parts_in_both(bilingual):
    book = load_book(bilingual)
    added = add_section(book, title="One more", actor=AUTHOR, reason="missing", into="1")
    add_part(load_book(bilingual), part="2", title="Later", actor=AUTHOR, reason="room")
    book = load_book(bilingual)
    assert added["section"] in [s.id for s in book.sections("pt-BR")]
    assert section_states(book, "pt-BR")[added["section"]]["state"] == "untranslated"
    assert book.meta("pt-BR")["parts"][2] == "Later"


def test_the_command_line_reports_a_translation(bilingual, capsys):
    assert main(["translation", str(bilingual)]) == 1
    out = capsys.readouterr().out
    assert "[pt-BR] from en: 4 untranslated; no glossary.yaml" in out and "untranslated  01-first-light" in out
    assert main(["language", "add", str(bilingual), "pt-BR", "--copy-meta"]) == 2


def test_the_control_room_shows_a_translation_against_its_source(bilingual):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from kdp_studio.server import create_app

    result = translate_section(load_book(bilingual), "pt-BR", "01-first-light", model=Answers(translated()))
    client = TestClient(create_app(bilingual))
    found = client.get("/api/translation", params={"lang": "pt-BR"}).json()
    assert found["states"] == {"untranslated": 4} and found["sections"][1]["candidates"] == 1
    version = client.get("/api/version", params={"id": result["version"]}).json()
    assert {f["verdict"] for f in version["translation"]} == {"pass"}
    overview = client.get("/api/book").json()
    assert overview["languages"]["pt-BR"]["contents"][0]["translation"] == "untranslated"
    assert overview["languages"]["en"]["contents"][0]["translation"] is None
    assert client.get("/api/translation", params={"lang": "en"}).status_code == 422


def test_the_room_opens_another_book_shows_the_catalogue_and_reads_the_ebook(sample, tmp_path):
    pytest.importorskip("fastapi")
    import shutil

    from fastapi.testclient import TestClient

    from kdp_studio.build import build_ebook
    from kdp_studio.server import create_app

    other = sample.parent / "other-book"
    shutil.copytree(sample, other)
    (other / "book.yaml").write_text((other / "book.yaml").read_text().replace("id: sample-book", "id: other-book"))
    client = TestClient(create_app(sample))
    books = {b["id"]: b for b in client.get("/api/library").json()}
    assert books["sample-book"]["open"] and not books["other-book"]["open"] and books["other-book"]["sections"] == 4
    assert client.post("/api/open", json={"path": str(tmp_path)}).status_code == 404
    assert client.post("/api/open", json={"path": str(other)}).json()["book"] == "other-book"
    assert client.get("/api/book").json()["id"] == "other-book"

    found = client.get("/api/templates").json()
    used = {(t["kind"], t["name"]) for t in found["templates"] if t["in_use"]}
    assert used == {("print", "nocturne"), ("ebook", "nocturne"), ("cover", "nocturne")}
    assert found["publishers"][0]["name"] == "kdp" and found["publishers"][0]["in_use"]

    assert client.get("/api/epub", params={"lang": "en"}).status_code == 404
    build_ebook(load_book(other), "en")
    spine = client.get("/api/epub", params={"lang": "en"}).json()["spine"]
    assert spine[0]["href"] == "title.xhtml" and any("first-light" in item["href"] for item in spine)
    page = client.get(f"/epub/en/{spine[-1]['href']}")
    assert page.headers["content-type"].startswith("application/xhtml+xml") and "<html" in page.text
    assert client.get("/epub/en/style.css").status_code == 200 and client.get("/epub/en/nope.xhtml").status_code == 404

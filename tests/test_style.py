from kdp_studio.book import load_book
from kdp_studio.continuity import repetitions
from kdp_studio.style import check_style

CHAPTER = """---
title: Um teste
---

Você vai vê-lo amanhã, e convém lembrar que o leitor esquece.

Imagine uma sala.

Pense em outra.

Como vimos no capítulo 9, o que se faz aqui importa.

Gerar não é agir, de novo.

::: exercise Faça
Se você tiver acesso, abra o agente. Este exercício é curto.

> [!prompt] EX-01-01
>
> Quero vê-lo funcionando; convém testar.
:::
"""


def portuguese(sample):
    """The sample book, switched to Brazilian Portuguese with one chapter in it."""

    book = sample / "book.yaml"
    book.write_text(book.read_text().replace("source_language: en", "source_language: pt-BR")
                    .replace("languages: [en]", "languages: [pt-BR]"))
    (sample / "manuscript" / "en").rename(sample / "manuscript" / "pt-BR")
    (sample / "manuscript" / "pt-BR" / "01-first-light.md").write_text(CHAPTER)
    (sample / "style.yaml").write_text(
        "practices:\n"
        "  - id: pratica-nao-exercicio\n    category: vocabulary\n    rule: Prática, nunca exercício.\n"
        '    check: {pattern: "\\\\bexerc[ií]cios?\\\\b", flags: i}\n'
        "    allow: ['um exercício de completar lacunas']\n"
        "refrains: ['gerar não é agir']\n")
    return load_book(sample)


def found(report, practice):
    return [f for f in report.findings if f.practice == practice]


def test_the_catalogue_finds_register_and_form(sample):
    report = check_style(portuguese(sample), "pt-BR", ["01-first-light"], engines=False)
    assert [f.match for f in found(report, "enclise-infinitivo")] == ["vê-lo"]
    assert found(report, "convem") and found(report, "se-impessoal")
    assert found(report, "troca-de-pessoa")[0].match == "o leitor"
    assert found(report, "hedge-na-pratica")[0].match.lower() == "se você tiver acesso"
    assert found(report, "remissao-quebrada")[0].match == "capítulo 9"
    assert found(report, "tese-como-refrao")
    # Two openers in one section, one allowed: one finding that says how many.
    assert found(report, "abertura-imagine")[0].message.startswith("2 in this section")


def test_prompts_are_never_checked_and_lines_point_at_the_file(sample):
    report = check_style(portuguese(sample), "pt-BR", ["01-first-light"], engines=False)
    assert all("funcionando" not in f.excerpt for f in report.findings)
    assert found(report, "enclise-infinitivo")[0].line == 5


def test_the_book_adds_its_own_decisions_with_approved_exceptions(sample):
    book = portuguese(sample)
    report = check_style(book, "pt-BR", ["01-first-light"], engines=False)
    assert [f.match for f in found(report, "pratica-nao-exercicio")] == ["exercício"]
    chapter = sample / "manuscript" / "pt-BR" / "01-first-light.md"
    chapter.write_text(chapter.read_text().replace("Este exercício é curto.", "É um exercício de completar lacunas."))
    report = check_style(book, "pt-BR", ["01-first-light"], engines=False)
    assert not found(report, "pratica-nao-exercicio")


def test_coverage_names_what_no_check_enforces(sample):
    report = check_style(portuguese(sample), "pt-BR", engines=False).public_dict()
    assert report["coverage"]["enforced"] < report["coverage"]["total"]
    assert "cobrir-definicoes" in {u["id"] for u in report["coverage"]["unenforced"]}


def test_a_passage_repeated_across_sections_is_one_group(sample):
    line = "Esta frase longa aparece igual em dois lugares diferentes do livro de teste."
    for name in ("01-first-light", "02-the-workshop", "03-what-remains"):
        path = sample / "manuscript" / "en" / f"{name}.md"
        path.write_text(path.read_text() + f"\n{line}\n")
    groups = repetitions(load_book(sample), "en")
    assert len(groups) == 1 and groups[0]["sections"] == 3

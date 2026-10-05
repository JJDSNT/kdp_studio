#!/usr/bin/env python3
"""Migrate "A Era dos Agentes" from its legacy layout to the KDP Studio book format.

    uv run python tools/migrate_era_legacy.py <legacy dir> <new book dir>

The legacy directory is only read. The new book is written to a directory that
must not exist yet, and every section is audited by the fidelity auditor
before anything is written: the migration changes markup, never words. The
normalisations it needs are declared below, and the report says how many
times each one applied.

This is a one-off conversion of one book's conventions; it is not a general
importer (that is the ingestion step of the roadmap).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from kdp_studio.fidelity import Normalization, compare

CALLOUTS = {
    "CONCEITO": "concept",
    "ATENÇÃO": "warning",
    "NA PRÁTICA": "practice",
    "DESAFIO ABERTO": "challenge",
}
SUBLABELS = ("Passos", "Perguntas-chave", "O pedido")

#: The legacy text writes structural labels into headings; the new format
#: generates them from the structure. These are the only differences allowed.
BEFORE = [
    Normalization("part-label", "part number and label are generated", r"^Parte [IVXLC]+ — "),
    Normalization("chapter-label", "chapter number and label are generated", r"^Capítulo \d+ — "),
    Normalization("front-label", "the label of a front section moved to toc_title", r"^Apresentação — "),
    Normalization("epilogue-label", "the epilogue label is generated", r"^Epílogo — "),
    Normalization("exercise-label", "the exercise label is generated", r"^Experimente — "),
    Normalization("callout-label", "callout labels are generated from the kind",
                  r"^(?:CONCEITO|ATENÇÃO|NA PRÁTICA|DESAFIO ABERTO) — "),
    Normalization("prompt-label", "the prompt label is generated from the kind", r"^PEGUE O PEDIDO — "),
]
AFTER = [
    Normalization("callout-marker", "[!kind] is markup", r"^\[![a-z-]+\]\s*"),
    Normalization("exercise-marker", "::: exercise is markup", r"^exercise\s+"),
]


def legacy_order(src: Path) -> list[Path]:
    index = (src / "manuscrito" / "README.md").read_text("utf-8")
    return [src / "manuscrito" / link for link in re.findall(r"\]\((pt-BR/[^)]+\.md)\)", index)]


def roman_to_int(value: str) -> int:
    numerals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = 0
    for i, char in enumerate(value):
        n = numerals[char]
        total += -n if i + 1 < len(value) and numerals[value[i + 1]] > n else n
    return total


def convert(text: str) -> tuple[dict, str, tuple[str, str, str] | None]:
    """Legacy section -> (frontmatter, body, part it opens as (id, kind, title))."""

    lines = text.splitlines()
    front: dict = {}
    opens = None
    out: list[str] = []
    in_exercise = False
    i = 0

    def close_exercise() -> None:
        nonlocal in_exercise
        if in_exercise:
            while out and not out[-1].strip():
                out.pop()
            out.extend([":::", ""])
            in_exercise = False

    while i < len(lines):
        line = lines[i]
        if m := re.match(r"^# Parte ([IVXLC]+) — (.+)$", line):
            opens = (str(roman_to_int(m.group(1))), "part", m.group(2).strip())
        elif m := re.match(r"^# Epílogo — (.+)$", line):
            opens = ("epilogue", "epilogue", m.group(1).strip())
        elif m := re.match(r"^# Apresentação — (.+)$", line):
            front = {"title": m.group(1).strip(), "kind": "front", "toc_title": "Apresentação"}
        elif m := re.match(r"^## Capítulo \d+ — (.+)$", line):
            front = {"title": m.group(1).strip()}
        elif m := re.match(r"^### Experimente — (.+)$", line):
            close_exercise()
            out.append(f"::: exercise {m.group(1).strip()}")
            in_exercise = True
        elif line.startswith("#"):
            close_exercise()
            out.append(line)
        elif in_exercise and line.strip() in {f"**{s}**" for s in SUBLABELS}:
            out.append(f"#### {line.strip()[2:-2]}")
        elif line.startswith(">"):
            block = []
            while i < len(lines) and lines[i].startswith(">"):
                block.append(lines[i])
                i += 1
            out.extend(convert_quote(block))
            continue
        else:
            out.append(line)
        i += 1
    close_exercise()
    body = "\n".join(out).strip("\n") + "\n"
    return front, body, opens


def convert_quote(block: list[str]) -> list[str]:
    head = block[0][1:].strip()
    if m := re.match(r"^\*\*PEGUE O PEDIDO\*\*\s*[—–-]\s*(\S+)$", head):
        out = [f"> [!prompt] {m.group(1)}"]
        rest = block[1:]
        # The legacy block opens with a separator; the new one does not need it.
        if rest and rest[0][1:].strip() == "---":
            rest = rest[1:]
        out.append(">")
        for line in rest:
            if line[1:].strip() == "---":
                # A blank quoted line on each side, or Markdown reads the
                # line above as a heading.
                out.extend([">", "> ---", ">"])
            else:
                out.append(line)
        return out
    if m := re.match(r"^\*\*([A-ZÀ-Ý ]+?)(?:\s*[—–-]\s*(.*?))?\*\*(?:\s*[—–-]\s*(.*))?$", head):
        label, name = m.group(1).strip(), (m.group(2) or m.group(3) or "").strip()
        if label in CALLOUTS:
            return [f"> [!{CALLOUTS[label]}] {name}".rstrip(), *block[1:]]
        if label == "AS QUATRO PERGUNTAS":
            return [f"> [!framework] {label}", *block[1:]]
    return block


COLOPHON = """**{title}** — {subtitle}

Como a inteligência artificial está aprendendo a trabalhar por nós

© 2026 Jaime Dias. Todos os direitos reservados.

Primeira edição. Texto verificado tecnicamente em [data de corte].

ISBN [a definir]

Nenhuma parte desta obra pode ser reproduzida sem autorização prévia do autor.

**Sobre marcas citadas.** Os nomes de produtos e serviços mencionados pertencem a seus respectivos \
titulares e são citados apenas para fins descritivos, sem qualquer vínculo, patrocínio ou endosso.

**Aviso.** Este livro descreve a instalação e o uso de programas no computador do leitor, incluindo \
a autorização para que sistemas de inteligência artificial executem ações nesse computador. Os \
procedimentos foram verificados na data indicada acima, mas software muda. O leitor é responsável \
por avaliar cada autorização que concede, por manter cópias de segurança dos seus dados e por \
conferir os resultados antes de utilizá-los. O autor não se responsabiliza por perdas decorrentes \
do uso das instruções aqui contidas.

Materiais complementares, pedidos prontos e correções: `exemplo.livro`
"""

#: Legacy location -> new location. Everything else in the legacy directory is
#: generated output (producao/, exportacoes/) or tooling KDP Studio replaces.
COPIES = {
    "intentions.md": "intentions.md",
    "editorial": "editorial",
    "manuscrito/README.md": "editorial/estado-do-manuscrito.md",
    "manuscrito/extras/_jornada": "companion/pt-BR/jornada",
    "provas-tecnicas": "experiments",
    "planejamento": "archive/planejamento",
    "arquivo-editorial": "archive/arquivo-editorial",
    "prototipo-repositorio-exercicios": "archive/prototipo-repositorio-exercicios",
    "especificacoes": "archive/especificacoes",
    "scripts": "archive/legacy-production/scripts",
    "producao/estilo.tex": "archive/legacy-production/estilo.tex",
    "producao/livro.tex": "archive/legacy-production/livro.tex",
    "arte/capa_pt_br.jpeg": "cover/pt-BR/art.jpeg",
    "AGENTS.md": "AGENTS.md",
    "CLAUDE.md": "CLAUDE.md",
}

#: Paths the guidance files name that moved.
PATH_UPDATES = [
    ("`manuscrito/README.md`", "`editorial/estado-do-manuscrito.md`"),
    ("manuscrito/README.md", "editorial/estado-do-manuscrito.md"),
]


def main(src: Path, dest: Path) -> int:
    if dest.exists():
        print(f"{dest} already exists; the migration writes only to a new directory.")
        return 2
    contents: list = []
    meta_parts: dict = {}
    sections: dict[str, str] = {}
    report: dict = {"sections": {}, "normalizations": {}}
    failures = 0
    current_part: dict | None = None
    for path in legacy_order(src):
        legacy = path.read_text("utf-8")
        front, body, opens = convert(legacy)
        if not front.get("title"):
            raise SystemExit(f"{path.name}: no title found")
        section_id = path.stem
        frontmatter = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
        sections[section_id] = f"---\n{frontmatter}\n---\n\n{body}"
        if opens:
            part_id, kind, title = opens
            meta_parts[part_id if kind != "part" else int(part_id)] = title
            current_part = {"part": part_id if kind != "part" else int(part_id), "sections": []}
            if kind != "part":
                current_part["kind"] = kind
            contents.append(current_part)
        if front.get("kind") == "front" or current_part is None:
            contents.append(section_id)
        else:
            current_part["sections"].append(section_id)
        # Audit: the reader's text before and after, the new one with its
        # title and opened part put back where the legacy text had them.
        heading = (f"# {opens[2]}\n\n" if opens else "") + f"# {front['title']}\n\n"
        audit = compare(legacy, heading + body, before_rules=BEFORE, after_rules=AFTER)
        report["sections"][section_id] = audit.public_dict()
        for rule, count in audit.normalizations.items():
            report["normalizations"][rule] = report["normalizations"].get(rule, 0) + count
        if not audit.ok:
            failures += 1
            print(f"FIDELITY  {section_id}")
            for difference in audit.word_differences[:5]:
                print(f"   - {difference['removed']!r}\n   + {difference['added']!r}")
            for fact in audit.facts_added + audit.facts_removed:
                print(f"   fact {fact}")
    if failures:
        print(f"\n{failures} section(s) failed the fidelity audit; nothing was written.")
        return 1

    dest.mkdir(parents=True)
    for section_id, text in sections.items():
        target = dest / "manuscript" / "pt-BR" / f"{section_id}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    meta = {
        "title": "A Era dos Agentes",
        "subtitle": "Uma introdução à inteligência artificial agentiva",
        "tagline": "Da geração à autonomia",
        "identifier": "urn:uuid:5e72009a-383e-4ba4-b55d-1c705cb58aaa",
        "parts": meta_parts,
        "colophon": COLOPHON.format(title="A Era dos Agentes",
                                    subtitle="Uma introdução à inteligência artificial agentiva"),
    }
    (dest / "manuscript" / "pt-BR" / "meta.yaml").write_text(
        yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")
    manifest = {
        "schema": 1,
        "id": "a-era-dos-agentes",
        "author": "Jaime Dias",
        "source_language": "pt-BR",
        "languages": ["pt-BR"],
        "contents": contents,
        "editions": {
            "print": {"template": "nocturne", "trim": "6x9", "paper": "white", "bleed": True},
            "ebook": {"template": "nocturne"},
        },
        # The directory name is the printed address: `era`, not the full slug,
        # because the printed panel has a 51-character budget (editorial/08).
        "exercises": {"url": "https://jjdsnt.github.io/books_resources/era/{language}/{id}"},
    }
    (dest / "book.yaml").write_text(
        "# A Era dos Agentes — KDP Studio book (docs/book-format.md).\n"
        + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")

    for old, new in COPIES.items():
        source, target = src / old, dest / new
        if not source.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", ".venv"))
        else:
            shutil.copy2(source, target)
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = dest / name
        if path.is_file():
            text = path.read_text("utf-8")
            for old, new in PATH_UPDATES:
                text = text.replace(old, new)
            path.write_text(text, encoding="utf-8")
    (dest / ".gitignore").write_text("builds/\n.venv/\n__pycache__/\n", encoding="utf-8")
    (dest / "migration-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    subprocess.run(["git", "commit", "-q", "-m",
                    f"Migrate to the KDP Studio book format\n\nFrom {src}. Every section passed the "
                    "fidelity audit: markup changed, words did not (migration-report.json)."], cwd=dest, check=True)
    print(f"Migrated {len(sections)} sections to {dest}")
    print("Normalisations applied:", ", ".join(f"{k} ×{v}" for k, v in sorted(report["normalizations"].items())))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1]).expanduser().resolve(), Path(sys.argv[2]).expanduser().resolve()))

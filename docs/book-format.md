# The book format (schema 1)

A book is a directory. KDP Studio reads it where it lies; there is no import
step and no second copy. Structural names are English; the book's own content
stays in its language.

## `book.yaml`

```yaml
schema: 1
id: a-era-dos-agentes            # stable; never derived from the title
author: Jaime Dias
source_language: pt-BR
languages: [pt-BR, en]
contents:                        # the reading order, language-neutral
  - 00-apresentacao              # a section on its own
  - part: 1                      # a numbered part
    sections: [parte-i-01-ensinar-sem-explicar, ...]
  - part: epilogue
    kind: epilogue               # part | epilogue | appendix
    sections: [epilogo-24-o-que-ainda-nao-sabemos-delegar]
editions:
  print: {template: nocturne, trim: 6x9, paper: white, bleed: true}
  ebook: {template: nocturne}
exercises:
  url: "https://jjdsnt.github.io/books_resources/era/{language}/{id}"
design:
  colors: {cold: "32D9E2"}       # optional overrides of the template palette
```

A section id is its file name without `.md`, and it is the same in every
language: that is what keeps a translated section tied to its source.

## `manuscript/<language>/meta.yaml`

Everything that changes with the language:

```yaml
title: A Era dos Agentes
subtitle: Uma introdução à inteligência artificial agentiva
tagline: Da geração à autonomia
identifier: urn:uuid:…           # the ebook identifier for this language
parts: {1: A longa viagem da inteligência artificial, epilogue: Os próximos horizontes}
labels: {exercise: Experimente}  # overrides of the built-in labels
colophon: |                      # Markdown; the copyright page
  © 2026 Jaime Dias. …
description: …                   # sales copy (ebook metadata)
```

## A section: `manuscript/<language>/<id>.md`

```markdown
---
title: Ver um agente programar
kind: chapter          # chapter (default, numbered) | front | back
toc_title: …           # optional, when the contents need another title
---

Body text. Sections inside a chapter start at `##`.
```

Chapter numbers, part numbers and their labels are generated. Writing
"Capítulo 11 —" in the text is how a renumbering once broke a book.

### Constructs

**Callouts**, written as GitHub-style alerts:

```markdown
> [!concept] A prova é comportamental
> Você não precisa ler uma linha do que foi escrito…
```

Kinds: `concept`, `warning`, `practice`, `challenge`, `note`, and `framework`
(a recurring framework whose title is its label). Each line inside a callout
stands on its own line.

**Exercises**, written as containers; `####` inside one is a sub-label:

```markdown
::: exercise Um programa que nasce da sua descrição
**O que você vai ver acontecer.** …

#### Passos

1. …
:::
```

**Prompts**: a callout whose title is the exercise id. The printed panel gets a
QR code to `exercises.url`, and the companion page is generated from the same
block, so the page and the print can never disagree. A line in bold labels the
prompt after it; `---` separates prompts, with a blank quoted line on each
side (otherwise Markdown reads the line above as a heading):

```markdown
> [!prompt] EX-02-01
>
> **Primeiro pedido**
> Crie um anúncio curto…
>
> ---
>
> **Segundo pedido**
> Reescreva sem inventar…
```

**Editorial comments** are HTML comments. They stay in the manuscript and
never reach an edition: a pending verification goes there, never into a hedge
in the reader's text.

Footnotes (`[^id]`), lists, tables, images and code blocks are CommonMark.
Raw HTML is refused.

## Other directories

| Path | Contents |
|---|---|
| `intentions.md` | the author's intention, in the author's words; wins every conflict |
| `editorial/` | the author's editorial documents, free-form |
| `cover/<language>/` | cover art; `ebook.jpg` is the ebook cover |
| `companion/<language>/` | material published beside the book, not in it |
| `experiments/` | records of exercises actually run |
| `archive/` | earlier drafts and retired material, kept for provenance |
| `templates/<kind>/<name>/` | the book's own edition templates |
| `state.json` | runtime-owned gates and decisions; never edited by hand |
| `builds/` | regenerated output; git-ignored |

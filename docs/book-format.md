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
  print: {template: nocturne, trim: 6x9, paper: white, bleed: true, ink: color}   # ink: color | black
  ebook: {template: nocturne}
  cover: {template: nocturne, art: horizon, focus: [0.6, 0.6], publisher: kdp}
exercises:
  url: "https://jjdsnt.github.io/books_resources/era/{language}/{id}"
design:
  colors: {cold: "32D9E2"}       # optional overrides of the template palette
```

`ink: black` builds the interior in black ink only — every colour becomes a
grey the theme chose — which is what a black-and-white printing costs less
for; the print check then fails any page that still carries colour.

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
cover:                           # the words of the cover, beyond title and author
  title: [A Era dos, Agentes]    # how the title breaks; default: before its last word
  line: Como a inteligência artificial está aprendendo a trabalhar por nós
  back: |                        # back-cover copy, Markdown
    …
  about: |                       # about the author, Markdown
    …
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

## A second language

`kdp language add <book> <language>` adds it: `languages` in `book.yaml`, a
`meta.yaml` with its own `identifier`, and one stub per section — the
source's frontmatter and no body, which reads as *untranslated*. The
translator fills each section as a candidate version; the frontmatter's
`title`, `toc_title`, `synopsis` and `promise` are translated, `kind` and
`research` are not. What a translation must keep from its source — prompt
ids, exercises, callouts, footnotes, code, URLs, numbers — is measured by
`kdp translation`.

### `glossary.yaml`

The book's bilingual decisions, at its root; optional, and the author's:

```yaml
terms:
  - pt-BR: [agente, agentes]     # every form the term takes
    en: [agent, agents]
    note: fixed by the localisation notes
keep: [Codex, AGENTS.md]         # names never translated
guide: [editorial/07-localizacao.md]   # the book's notes, read by the translator
```

A term used in a source section and absent from its translation is reported;
a kept name must appear the same number of times.

## Cover and art

A cover is art plus words. `art/<id>.<ext>` is a picture of the book — cover
art, an illustration — and `art/<id>.yaml` records how it was made:

```yaml
purpose: cover            # cover | illustration
lettering: none           # none | baked (it carries words) | unchecked (a model was asked for none)
prompt: a planet's edge at dawn, no text, no letters
model: …                  # with provider and seed, when a model made it
derived_from: …           # the art id it was made from
width: 1900
height: 2850
digest: …
```

`kdp art add` writes both, and so does `kdp art generate`, which has a
provider make the picture or repaint one the book has (`--from <id>
--remove-lettering`): the request is shown with its estimate and sent only
with `--yes`. Nothing is replaced, so another attempt is another id. A
provider's keys and endpoints are never kept in a book (`kdp art providers`). Art for a cover carries no lettering: image models misspell, and words
drawn into a picture cannot be corrected or translated. Every word is set by
the cover template from `meta.yaml`, so one picture serves every language.

`editions.cover` names the template, the art (optional: a cover may be
typographic), the `focus` the crop keeps (fractions of the picture's width and
height) and the publisher profile (docs/templates.md). `kdp build --edition
cover` writes the ebook cover and, once the print interior is built, the wrap
sized for its page count. An ebook cover the author supplies as
`cover/<language>/ebook.jpg` wins over the built one.

## Other directories

| Path | Contents |
|---|---|
| `intentions.md` | the author's intention, in the author's words; wins every conflict |
| `editorial/` | the author's editorial documents, free-form |
| `art/` | pictures with their records (above) |
| `cover/<language>/` | a finished cover supplied by the author; `ebook.jpg` is the ebook cover |
| `publishers/<name>.yaml` | the book's own publisher profiles |
| `companion/<language>/` | material published beside the book, not in it |
| `experiments/` | records of exercises actually run |
| `archive/` | earlier drafts and retired material, kept for provenance |
| `templates/<kind>/<name>/` | the book's own edition templates |
| `glossary.yaml` | terms and names decided for every language (above) |
| `versions/<language>/<section>/` | candidate versions, with the text each was based on |
| `state.json` | runtime-owned gates and decisions; never edited by hand |
| `builds/` | regenerated output; git-ignored |

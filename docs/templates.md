# Edition templates

A template is how a book looks in one medium. The book chooses one per edition
in `book.yaml`; changing the design of a book is changing one name. Templates
form a catalogue (`kdp templates`): built-in ones ship in
`src/kdp_studio/templates/<kind>/<name>/`, and a book may add or override one in
`<book>/templates/<kind>/<name>/`.

The renderers emit *semantic* markup: "a concept callout", "a prompt with a QR
code". The template decides what that looks like. The contract below is all a
template must implement.

The two media are not the same object. Copying the print decisions into the
ebook produced the worst defects of the book this tool was built for: dark
grounds that vanish on readers that drop background colours, distinctions made
by colour alone. A template is good in the medium it lives in.

## `template.yaml`

```yaml
name: nocturne
kind: print            # print | ebook
title: Nocturne
description: …
engine: lualatex       # print only
trims:                 # print only: the layouts this template was designed for
  6x9: {paper: [6in, 9in], typeblock: [4.05in, 7.05in], spine_margin: 0.98in, top_margin: 0.86in}
colors: {ink: "12202B", …}   # a book may override them under design.colors
needs_bleed: true      # ink to the edge on some pages
```

A trim a template does not list is refused, never guessed.

## Print contract (LaTeX)

`book.tex.j2` is a Jinja template with LaTeX-safe delimiters: `((* *))` for
blocks, `((( )))` for values, `((= =))` for comments. It receives `title`,
`subtitle`, `tagline`, `author`, `language`, `labels`, `colors`, `trim`,
`bleed` and `colophon` (already LaTeX), and must `\input{body}`.

`body.tex` uses only these:

| Markup | Meaning |
|---|---|
| `\kdppart{label}{title}` | numbered part opening ("Parte I") |
| `\kdpunnumberedpart{label}{title}` | epilogue or appendix opening |
| `\kdpchapter{label}{title}{toc title}` | numbered chapter ("Capítulo 11") |
| `\kdpfrontsection{toc title}{title}` | unnumbered front section |
| `\section`, `\subsection`, `\subsubsection` | headings inside a chapter |
| `kdpcallout` env `{kind}{label}{title}` | callout; `framework` has its title as label and an empty title |
| `kdpexercise` env `{label}{title}` | exercise block |
| `\kdpsublabel{text}` | sub-label inside an exercise |
| `\kdpprompt{label}{id}{display url}{qr path}{body}` | prompt panel; the QR path is empty without a URL |
| `\kdppromptlabel{text}`, `\kdpprompttext{text}`, `\kdppromptsep` | the body of a prompt panel |
| `\kdpbreak` | thematic break |
| `\kdpimage{path}` | image |
| `kdptable` env `{columns}` | table |

Labels arrive in the book's language, in sentence case; the template decides
capitalisation.

## Ebook contract (CSS)

`style.css` styles these classes:

| Class | Element |
|---|---|
| `.part-opening`, `.part-label`, `.part-rule`, `.part-title` | part opening page |
| `.chapter-label`, `.front-label`, `.chapter-title`, `.chapter-rule` | chapter head |
| `.callout`, `.callout-<kind>`, `.callout-head`, `.callout-label`, `.callout-title` | callouts |
| `section.exercise`, `.exercise-label`, `.exercise-title`, `.sublabel` | exercises |
| `.prompt`, `.prompt-head`, `.prompt-label`, `.prompt-link`, `.qr`, `.prompt-url`, `.prompt-hint`, `.prompt-name`, `.prompt-text` | prompts |
| `.title-page`, `.subtitle`, `.tagline`, `.colophon` | title page |
| `.notes`, `hr.break`, `li.toc-part` | notes, breaks, contents |

Never put a background on `body`, and never let a distinction depend on colour
alone.

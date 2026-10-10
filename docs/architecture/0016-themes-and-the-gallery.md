# ADR 0016: Themes, and a gallery that shows them on the same text

Status: accepted (2026-10-10).

## Context

The catalogue held one design, and the control room listed it as a name and
a description. The author asked for something else: a gallery of themes
applied to a lorem ipsum text, to browse layout options. A design is chosen
by looking at it.

## Decision

- **A theme is a name the catalogue holds across media**: `print/<name>`,
  `ebook/<name>`, `cover/<name>`. Nothing new in the format; the catalogue
  already keyed templates by kind and name (ADR 0004).
- **Two more themes** beside Nocturne, different on purpose: **Folio** (one
  serif family, the centre line, a burgundy accent, no ink to the edge) and
  **Signal** (a bold sans for what orients, heavy rules, part openings in the
  accent colour). Both implement the whole contract in the three media.
- **A specimen** ships with the tool (`specimen/`): a short book of lorem
  ipsum with a part, two chapters, callouts, a framework, a list, a footnote
  and an exercise with its prompt. Its labels are printed in the language the
  author is looking at.
- **The gallery renders each theme over the specimen** (`gallery.py`): the
  print pages as pictures, tagged by what they show (part opening, chapter
  opening, callouts, exercise), the cover and the wrap, and the ebook itself.
  Renders are a cache outside any book, keyed by the theme's files, the
  specimen and the language, so a template that changes is rendered again.
- **Taking a theme is one command**, `set_theme` (`kdp theme <book> <name>`,
  the button in the gallery): only the template names inside the `editions`
  block of `book.yaml` change, every other character stays, and it is a commit
  with its reason. A theme without a medium the book declares leaves that
  edition as it was; a print theme without the book's trim is refused.

## Consequences

- A book's `design.colors` overrides are by role (`cold`, `warm`…): they
  follow the book into another theme, where they may not suit.
- The palette's role names come from Nocturne and read oddly in a red theme.
- The gallery shows the specimen, not the author's book: after taking a theme
  the editions are built again to see it on the real text.

## Validation

The three themes rendered over the specimen in en and pt-BR and looked at,
pages and covers; the first Folio render left a callout's label alone at the
foot of a page, fixed in the two new templates. The gallery opened in a
headless browser on a copy of *A Era dos Agentes*.

# ADR 0017: Black ink, the person's own catalogue, and a designer that builds what it draws

Status: accepted (2026-10-10). Extends ADR 0016.

## Context

The author, looking at the gallery: the ebook was one small frame at the end
of a strip of print pages; an interior without colour is cheaper to print and
could not be seen or asked for; ready-made templates exist on the web (the
Overleaf gallery) and might be used where their licence allows; and the agent
responsible for layout should know it may look for references, inside and
outside, and its creations should be catalogued in the gallery.

## Decision

- **The gallery has two media.** Print — cover, part opening, chapter
  opening, callouts, exercise, the wrap — in colour or in black ink; and
  Ebook — the cover and the specimen's own documents (part opening, chapter
  with callouts, exercise with prompt), on a colour screen or in grey as
  e-ink shows them.
- **`ink: black` under `editions.print`.** Every colour of the palette
  becomes a grey: the one the template chose (`mono:` in its manifest), else
  the colour's luminance. Left to the printer, a colour file printed in black
  and white gets greys nobody designed. The print check rasterises each page
  and counts those where any pixel is not a grey: with `ink: black` one such
  page fails; otherwise the count is reported with what it costs.
- **A third layer in the catalogue: the person's own**
  (`$XDG_DATA_HOME/kdp-studio/templates/`), between the built-in themes and
  a book's. It serves all their books. Taking a theme from it copies the
  theme into the book, in the same commit: a book builds from what it holds.
- **The designer** (`agents/designer.py`) draws a theme from the author's
  brief. Its references are *internal* — the theme it starts from, whose
  blocks it is shown, and the descriptions of the others, to differ from
  them — and *external*, a web address the author gives: it opens the page,
  takes the design, and records the address, the licence the page states and
  what it took (`inspired_by` in the manifest, shown in the gallery). Code is
  copied only under a licence that allows adaptation; with none stated, or a
  non-commercial or no-derivatives one, ideas only. Most of the Overleaf book
  gallery states no licence (looked at 2026-10-10), so this is the usual case.
- **It answers with blocks; the tool assembles and builds.** Fonts, part
  opening, chapter head, section head, palette, what the ebook adds, the
  cover's palette and faces. Blocks that load packages, read files or run
  code are refused; fonts must be installed here; then the specimen is built
  with the theme. A theme that does not build is sent back with the error,
  and one that still does not is never catalogued. Importing a web template
  as it is was not done: such a template does not implement the contract
  (callouts, exercises, prompts with QR codes), so it would have to be
  rewritten anyway, and its licence would then govern a book for sale.
- **The assistant knows this**: it reads the themes, proposes `set_theme` or
  `design_theme` (with the address to look at), and takes the author to the
  gallery.

## Consequences

- A designed theme is LaTeX written by a model and run by LuaLaTeX on this
  machine. The refusals are a list of words, not a sandbox.
- "Ideas only" is the designer's word and its record; nothing measures it.
- The cover is always in colour; `ink` is about the interior.

## Validation

The real model drew `novela` over Folio from a brief and an Overleaf address
in 2m10s: it built at the first attempt with no overfull box, recorded the
page's licence ("Other (as stated in the work)") and the LPPL of the class it
uses, and took ideas only, saying why (the reference is a manuscript format,
not a book design). Looked at: large right-hung numerals, a vermilion accent;
one callout label is left alone at the foot of a page.

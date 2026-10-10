# Edition templates

A template is how a book looks in one medium. The book chooses one per edition
in `book.yaml`; changing the design of a book is changing one name. Templates
form a catalogue (`kdp templates`): built-in ones ship in
`src/kdp_studio/templates/<kind>/<name>/`, and a book may add or override one in
`<book>/templates/<kind>/<name>/`.

A **theme** is a name the catalogue holds in more than one medium —
`print/folio`, `ebook/folio`, `cover/folio` — so a book changes its whole look
with `kdp theme <book> <name>`. Built in: `nocturne`, `folio`, `signal`. The
control room shows each one applied to the same specimen text
(`src/kdp_studio/specimen/`); a new template appears there by existing.

The catalogue has three layers, a later one replacing the same name: built-in,
the person's own (`$XDG_DATA_HOME/kdp-studio/templates/<kind>/<name>/`, for all
their books), and the book's. A theme taken from the person's own is copied
into the book. `kdp theme <book> <name> --design --brief "…" [--reference URL]`
has the designer draw one: it joins the person's catalogue only if the
specimen builds with it, and its manifest says what it was drawn from
(`designed_by`, `brief`, `based_on`, and `inspired_by` with each address
looked at, its licence and what was taken).

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
kind: print            # print | ebook | cover
title: Nocturne
description: …
engine: lualatex       # print only
trims:                 # print only: the layouts this template was designed for
  6x9: {paper: [6in, 9in], typeblock: [4.05in, 7.05in], spine_margin: 0.98in, top_margin: 0.86in}
colors: {ink: "12202B", …}   # a book may override them under design.colors
needs_bleed: true      # ink to the edge on some pages
mono: {cold: "707070"} # print only, optional: the grey a colour takes in black ink
```

A trim a template does not list is refused, never guessed. Colours are named
by role, not by hue: `cold` is the accent of the narrative and `warm` the
accent of exercises, `deep` the heads, `shade` the ground of an exercise.

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

## Cover contract (LaTeX)

A cover template (`templates/cover/<name>/`) sets the *words* of a cover over
art that carries none (docs/book-format.md, "Cover and art"). One design gives
the ebook front and the print wrap. `cover.tex.j2` uses the same delimiters as
the print template and typesets one page; it receives:

| Value | Meaning |
|---|---|
| `sheet.width`, `sheet.height` | the page, in inches: the ebook front, or bleed + back + spine + front + bleed |
| `s` | the trim width over 6in: multiply type sizes and distances by it |
| `margin` | how far words stay from the trim |
| `at.<place>` | ready coordinates, in inches from the lower-left corner: `corner`, `art`, `author`, `title`, `line`, `spine`, `back` |
| `art` | the picture for this sheet (already cropped, scrim baked in), or empty |
| `front.art_width`, `front.art_height`, `front.text_width` | the front panel |
| `title_lines`, `title`, `subtitle`, `tagline`, `author`, `line` | the words; the last title line is the one to stress |
| `spine` | absent on the ebook; `spine.text` says whether the spine is thick enough for text, `spine.length` and `spine.band` bound it |
| `back` | absent on the ebook; `back.width`, `back.text` and `back.about` (already LaTeX) |
| `colors`, `labels` | as in the print template |

The back-cover text must be typeset in a box whose height the template writes
to the log as `KDP-COVER back-text-height=<dimension>`: the cover check uses it
to say whether the text reaches the barcode. Nothing may be drawn with
transparency; the template's `scrim` (pairs of distance from the top and
opacity of the ground) and `edge_fade` are baked into the picture instead.

A template knows nothing of a publisher: sizes arrive computed.

## Publisher profiles

What a publisher or printer asks of a cover is data, not code:
`src/kdp_studio/publishers/<name>.yaml`, and a book's own in
`<book>/publishers/<name>.yaml`, chosen by `editions.cover.publisher`
(default `kdp`).

```yaml
title: Amazon KDP — paperback and Kindle
bleed: 0.125                                   # inches, on the three outer edges
spine: {base: 0, per_page: {white: 0.002252, cream: 0.0025}}
spine_text: {min_pages: 100, margin: 0.0625}
barcode: {size: [2.0, 1.2], from_spine: 0.25, from_foot: 0.25}
safe: 0.125                                    # words to the trim, at least
dpi: 300
ebook: {pixels: [1600, 2560], max_megabytes: 50}
```

The wrap is then the book's trim (from the print edition), its page count and
this profile: `2 × bleed + 2 × trim width + spine` by `trim height + 2 × bleed`.
A profile describes a paperback wrap; a case-bound cover, with its turn-ins
and hinges, needs more than these figures and is not covered yet.

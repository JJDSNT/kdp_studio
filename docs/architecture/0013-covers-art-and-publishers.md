# ADR 0013: Covers — art without lettering, words set by code, sizes from a publisher profile

Status: accepted (2026-10-10).

## Context

The book needs four covers: ebook and print wrap, in two languages. Its
existing cover was drawn whole by an image model, lettering included; such
lettering is sometimes misspelt and can be neither corrected nor translated.
The author keeps a structure for pictures in Cine Toaster and asked that KDP
Studio have its own, similar one, with a tool to write on the cover; and
noted that a cover's dimensions depend on the book's size and on the
publisher's standard.

## Decision

- **A cover is art plus words, kept apart.** The art is a picture of the book
  with no lettering. Every word — title, subtitle, author, tagline, the line
  at the foot, the spine, the back-cover copy — is set by a **cover template**
  (a third kind in the catalogue, ADR 0004) from `meta.yaml`, in LuaLaTeX,
  with the book's fonts, as vector text. One picture serves every language.
- **Art is a record** (`art/<id>.<ext>` + `art/<id>.yaml`): purpose, prompt,
  model, provider, seed, what it was derived from, whether it carries
  lettering, size and digest. Nothing is replaced; another attempt is another
  id. From Cine Toaster: layered catalogues, provenance beside the file,
  versions kept, engines as external programs.
- **Sizes are data.** A publisher profile (`publishers/<name>.yaml`, the
  book's own included) gives bleed, spine per page and paper, when the spine
  may carry text, where the barcode goes, the ebook's pixels. The wrap is the
  print edition's trim, the built interior's page count and that profile. No
  figure of one publisher is in the code that lays out a cover.
- **One design, two files**: the ebook cover (embedded by the ebook build
  unless the author supplies one) and the print wrap, which exists only once
  the interior is built.
- **Measured** (`checks/cover.py`): ebook pixels, colour and weight; the
  wrap's size against the interior *as it is now* — a wrap built for another
  page count fails; fonts embedded; spine text only when allowed; the
  back-cover text's typeset height against the barcode; art resolution;
  declared lettering; whether the text was frozen first (docs/origin, §11).
  The scrim over the art is baked into the picture, so the print file has no
  transparency.

## Consequences

- Generating art is not here yet: a provider adapter (as Cine Toaster's
  ComfyUI and Qwen ones) that records what it made is the next step. Until
  then art is made elsewhere and registered with `kdp art add`.
- A profile describes a paperback wrap; a case-bound cover is not covered.
- "No lettering" is declared in the record, not detected.

## Validation

The sample book builds a typographic cover (ebook 1600 × 2560; wrap 12.293" ×
9.25" for 17 pages). On a copy of *A Era dos Agentes*, with a stand-in picture
drawn by code: the Portuguese wrap for 156 pages (spine 0.3513", text on the
spine) and the English one for 77 (no spine text), both ebook covers, every
check passing but the freeze warning. Looked at: the first render showed
`<built-in method copy of dict…>` where the back-cover text belongs — a
template variable named `copy` — which no log reported.

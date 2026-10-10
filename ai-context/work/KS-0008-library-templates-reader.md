---
id: KS-0008
title: The control room opens other books, shows the templates and reads the ebook
type: work
status: done
owner: project
created_at: 2026-10-10
updated_at: 2026-10-10
---

# What and why

The author, looking at the control room: it works with one book only, the
edition templates are nowhere to be seen, and there is no way to read the
ebook. ADR 0014.

# Done

- `Studio`: a library and an open book (`books`, `open`, `reconcile` once per
  book), `catalogue` (templates and publishers with what the book uses),
  `epub_spine` / `epub_file` (the built EPUB read out of its archive).
- `/api/library`, `POST /api/open`, `/api/templates` (now the catalogue),
  `/api/epub`, `/epub/<language>/<file>`.
- `kdp serve` takes a book or a directory of books, and `--library`.
- Views: Library (the book's title in the header leads there), Templates,
  Reader (device widths, previous/next, the reading order as a list).
- The assistant shares the runtime's Studio and keeps one conversation per
  book.

- The menu follows the work (the author's suggestion): four stages in the
  header — Plan & write, Review, Produce, Publish — each with its views in a
  row under it; Gates (with the number waiting) and Jobs stay beside them
  because they cut across every stage. Publish has a Readiness page per
  language, read from records that already exist: translation, the freeze
  gate, each edition built and measured, the publish decision.

# Validation

75 tests pass (a second book opened, the catalogue, the EPUB read page by
page); flake8 clean; the frontend builds. The three views opened in a
headless browser on a copy of *A Era dos Agentes* with `--library ~/books`.

# Looked at and not adopted

`JJDSNT/pipeline-de-publicacao` (the author's earlier pipeline, 2025): ODT →
Markdown through pandoc, then HTML, EPUB, LaTeX and FODT, with a manifest
ordering chapters into parts, for the book *Liderando a Transformação
Digital*. Its EPUB, LaTeX and EPUBCheck parts are superseded here. Worth
bringing when ingestion (roadmap 10) is built: the pandoc ODT conversion with
its heading fix, the ordering of numbered files into parts, its list of
front and back matter (half title, dedication, epigraph, acknowledgements,
glossary, about the author) — and that book itself, as the first existing
manuscript to ingest. No public KDP upload interface was found (2026-10-10):
what exists on GitHub prepares files or drives the browser.

# Remaining

- Choosing a template from the interface (today: one name in `book.yaml`).
- Starting a new book from the Library (today: `kdp new`).
- The reader shows one document at a time, not pages; night and sepia modes.
- An OPDS feed over the same library (roadmap, later).

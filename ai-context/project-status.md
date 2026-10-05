---
id: CTX-STATUS
title: Project status
type: status
status: active
owner: project
created_at: 2026-10-04
updated_at: 2026-10-04
---

# Project status

**Phase:** milestone 1 delivered — the book stands on its own in KDP Studio.

## Delivered

- Book format, schema 1 (docs/book-format.md, ADR 0003): `book.yaml`,
  per-language `meta.yaml`, sections with frontmatter, callouts, exercises,
  prompts, editorial comments.
- Edition template catalogue with a semantic contract (docs/templates.md,
  ADR 0004); first templates: `nocturne` print and ebook.
- Builds: print interior with LuaLaTeX (bleed, QR codes), EPUB 3 (nav in the
  spine, NCX, split titles, link check).
- Checks: KDP print measured from the PDF (size, pages, gutter by page count,
  margins, fonts, blank pages with folios, full-bleed pages, overfull and
  underfull); EPUB structure and reader traps.
- Human gates in `state.json`, with digests, revisions, a cross-process lock,
  git commits per decision; agents cannot decide.
- Fidelity auditor (ADR 0005): reader's words with declared normalisations,
  fact inventory, exact digests, PDF comparison by page and across the book.
- CLI `kdp`: doctor, status, templates, build, check, gate, compare.
- *A Era dos Agentes* migrated to `~/books/a-era-dos-agentes` (git repository,
  original untouched): 25 sections, fidelity audit clean, 156 pages, every
  measured KDP check passing.

## Next action

Milestone 2 (roadmap): the control room and the version model (ADR 0006),
then the agents (milestone 3).

## Risks and gaps

- The legacy exercise exporter does not read the new layout; until
  `kdp companion` exists the public `books_resources` must not be regenerated
  from the migrated book.
- Transparency in the PDF is not measured; EPUBCheck is not installed here.
- The book has no ebook cover at 1600 × 2560 yet (`cover/pt-BR/art.jpeg` is
  1024 × 1536).
- The fact inventory's proper-name pattern is heuristic: it can over-report,
  never silently pass a changed number, URL or code span.

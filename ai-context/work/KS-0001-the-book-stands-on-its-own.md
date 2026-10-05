---
id: KS-0001
title: The book stands on its own — format, migration, builds, checks, gates, fidelity
type: work
status: done
owner: project
created_at: 2026-10-04
updated_at: 2026-10-04
---

# What and why

The author asked for a tool in the shape of Cine Toaster, for books, and to
continue *A Era dos Agentes* with it. The first prototype (a Next.js chat in
front of a LangGraph agent holding the book in graph state) was discarded: it
made the conversation the authority over the book.

# Done

- Repository restructured as a Python package with the `kdp` CLI (Cine Toaster
  layout: `ai-context/`, `docs/architecture/`, AGENTS.md).
- Format, templates, builds, checks, gates, fidelity — see project-status.md.
- `tools/migrate_era_legacy.py`: one-off migration, audited per section before
  anything is written; report kept in the book (`migration-report.json`).
- Sample book in `examples/`; 22 tests.

# Decisions

ADRs 0001–0006. Notably: workflow state is records, LangGraph runs agents
(after Cine Toaster's measured spike); fidelity is never asked of a model.

# Validation

- `uv run pytest`: 22 passed. `uv run flake8 src tests tools`: clean.
- Migration: 25/25 sections pass the fidelity audit. The auditor caught a real
  bug first (the character class missed "Á", leaving four "NA PRÁTICA"
  callouts unconverted).
- The legacy pipeline, re-run on the current manuscript, gives 156 pages; the
  new build gives 156 pages, 149 identical page texts, and whole-book text
  differences limited to: the colophon's small caps, and `**Netlify**`,
  `**Ollama**`, `**LangGraph**` — printed with literal asterisks by the legacy
  generator, correctly bold now.
- `kdp check` on the migrated book: 12 measured print checks pass (gutter
  0.951" against 0.5" required at 156 pages; 9 full-bleed part openings);
  EPUB structure passes; warnings: no ebook cover, EPUBCheck not installed.
- Pages rasterised and inspected: part openings, chapter openings, callouts,
  framework box, exercise and prompt panel with QR.

# Remaining

See roadmap milestones 2+. Companion export is the first gap the book feels.

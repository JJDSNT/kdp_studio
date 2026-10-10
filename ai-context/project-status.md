---
id: CTX-STATUS
title: Project status
type: status
status: active
owner: project
created_at: 2026-10-04
updated_at: 2026-10-10
---

# Project status

**Phase:** milestones 1 and 2 delivered, 3 under way, and a second language
brought forward — the book stands on its own, the author works on it in the
control room with the assistant, and it can be translated section by section.

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

- Milestone 2 (ADR 0006, ADR 0007): `kdp serve` control room (book, section
  read/edit/versions/history, version comparison with fidelity, gates,
  editions with measured checks, page proofs, documents); candidate versions
  and byte-for-byte editing with git commits; the single command boundary
  (`commands.py`) with the agent's narrower set; the editorial assistant
  (LangGraph CoAgent through CopilotKit v2, model through the Claude Code CLI
  or the API).

- Milestone 3, first half: `style.py` (catalogue, coverage, the book's
  `style.yaml`), `linters.py` (LanguageTool, Vale), `tools.py` (pinned,
  verified, per-user installs), `continuity.py`, `jobs.py`, `agents/voice.py`;
  Style, Continuity and Jobs views; the assistant can read style findings and
  start the voice reviser. On *A Era dos Agentes*: 35 register/form findings
  (23 infinitive enclises — the open item T3), EPUBCheck 5.4 with 0 errors and
  0 warnings, 21 recurring passages.

- The chapter loop (ADR 0010): chapter gates and review status, `reorder` /
  `kdp move` with the references a move breaks, the reviser by instruction
  (`revise_section`), the approved pilot chapter as the voice of every agent;
  the assistant proposes revisions and moves and asks first. Verified in a
  headless browser on a copy of the book with the real model.

- From an idea to chapters (ADR 0011): `kdp new`; researcher (web, dossier,
  dated source ledger, not-found), architect (plan with synopsis and promise,
  adopted by the author), writer (chapter to its promise as a candidate);
  add/remove sections and parts; the assistant runs the whole flow, asking
  first. Real end to end on a new book. The book lock is re-entrant (a nested
  command deadlocked on its own flock).

- A second language (ADR 0012): `add_language` (meta.yaml and a stub per
  section), the translator (a candidate version per section, adaptations
  declared), the book's `glossary.yaml`, the translation measured against its
  source (structure, prompt ids, code, URLs, numbers, glossary terms), and
  stale translations when the source changes. `kdp language add`, `glossary`,
  `translate`, `translation`; the Translation view; the assistant runs it.
  Verified with the real model on a copy of *A Era dos Agentes*: `en` added,
  glossary drafted, chapter 4 translated, the English print and ebook built
  and measured.

## Next action

On *A Era dos Agentes* itself, the author's acts: `kdp language add … en`,
read the glossary, read one translated chapter, then the rest. In the tool:
the companion (`kdp companion`, with the `/en/` pages the QR codes point to)
and the cover per language, which the four KDP products need; then
NILC-Metrix and spaCy as engines and the rest of milestone 3.

## Risks and gaps

- The legacy exercise exporter does not read the new layout; until
  `kdp companion` exists the public `books_resources` must not be regenerated
  from the migrated book.
- Transparency in the PDF is not measured.
- A translated language has no cover and no companion pages yet: the English
  ebook builds without a cover, and its QR codes point to `/en/` addresses
  that do not exist until the companion is generated.
- Translation checks cannot see a number written out in words, and the
  English style catalogue has few register rules.
- The book has no ebook cover at 1600 × 2560 yet (`cover/pt-BR/art.jpeg` is
  1024 × 1536).
- The fact inventory's proper-name pattern is heuristic: it can over-report,
  never silently pass a changed number, URL or code span.

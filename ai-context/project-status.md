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

- Covers (ADR 0013): art as records without lettering (`art/`, `kdp art`),
  the `nocturne` cover template setting every word from `meta.yaml`, publisher
  profiles for the sizes (`publishers/kdp.yaml`, a book's own), the ebook cover
  and the print wrap from one design, and the cover check (a wrap built for
  another page count fails). Verified on the sample book and on a copy of
  *A Era dos Agentes* in both languages, with a stand-in picture.

- The control room opens other books (a library and one open book, ADR
  0014), shows the template catalogue and the publisher profiles, and reads
  the built ebook at a device's width.

- Art providers (ADR 0015): `kdp art generate` plans a picture (prompt with
  "no lettering", size, seed, estimate), sends it only on a yes, and records
  what comes back; ComfyUI and Qwen Image Edit on RunPod. Tested with scripted
  endpoints only — no real job has been sent.

- Themes and the gallery (ADR 0016): three themes across print, ebook and
  cover — Nocturne, Folio, Signal — rendered over a lorem ipsum specimen and
  shown side by side in the control room; `set_theme` / `kdp theme` takes one.

- Black ink, the person's catalogue and the designer (ADR 0017): the gallery
  shows print (colour or black ink) and ebook (screen or e-ink);
  `editions.print.ink: black` builds the interior in greys and the check
  fails a page with colour; a designer agent draws a theme from a brief and
  from references, recording the licence of what it looked at, and the theme
  joins the gallery only if the specimen builds with it.

- The critic (ADR 0018): an agent shown a theme's rendered pages judges
  character and craft; one look after a theme is drawn, then the author
  decides whether the designer answers it. Themes revised and removed.

- Agents as manifests (ADR 0019): thirteen more agents — interviewer,
  fact-checker, technical reviewer, experimenter, continuity reviser,
  intention guardian, ingestor, diagnostician, mapper, KDP packager, marketer,
  art director, reader of the translation — each a manifest that reads the
  book and hands back a report or edits; a meta-agent that designs new ones
  and tries each before cataloguing it.

- One flow on LangGraph (ADR 0020): draft, check, land, hold. Every agent
  runs on it — researcher, architect, writer, revisers, translator, designer
  and the manifest agents — each with named checks; after work lands the
  author can always have it critiqued and redone, from Jobs or the chat; a
  failed check never lands; a held flow survives a restart.

## Next action

On *A Era dos Agentes* itself, the author's acts: `kdp language add … en`,
read the glossary, read one translated chapter, then the rest; and the cover
art — configure a provider (`kdp art providers`), register the present cover
as `lettering: baked`, and repaint it without its words, or generate a new
one. In the tool: the companion (`kdp companion`), then NILC-Metrix and spaCy
and the rest of milestone 3.

## Risks and gaps

- The legacy exercise exporter does not read the new layout; until
  `kdp companion` exists the public `books_resources` must not be regenerated
  from the migrated book.
- Transparency in the PDF is not measured.
- A translated language has no companion pages yet: its QR codes point to
  `/en/` addresses that do not exist until the companion is generated.
- The book's only cover art has its words drawn in by a model and is 1024 ×
  1536; the cover template needs art without lettering, larger.
- Art generation has never run against a real endpoint from here, a generated
  picture is about 167 dpi on a 6 × 9 cover, and "no lettering" is declared by
  a person, not detected.
- Translation checks cannot see a number written out in words, and the
  English style catalogue has few register rules.
- The fact inventory's proper-name pattern is heuristic: it can over-report,
  never silently pass a changed number, URL or code span.

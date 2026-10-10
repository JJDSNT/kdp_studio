---
id: CTX-ROADMAP
title: Roadmap
type: roadmap
status: active
owner: project
created_at: 2026-10-04
updated_at: 2026-10-10
---

# Roadmap

The order follows the origin specification (§12): the deterministic parts
first, because writing a whole book before knowing it compiles and validates
is how *A Era dos Agentes* started, and it cost dearly.

1. **The book stands on its own** — format, migration, builds, measured
   checks, gates, fidelity. *Delivered.*
2. **Control room, versions and the assistant** — *Delivered.* React + Vite
   over the commands; candidate versions, word diff with the fidelity report,
   adoption as a git commit, byte-for-byte editing; the editorial assistant as
   a CopilotKit CoAgent (ADR 0007).
3. **Specialised agents** — started (2026-10-04): the vice catalogue as checks
   with coverage, the book's `style.yaml`, open engines (LanguageTool, Vale,
   EPUBCheck) via `kdp tools`, the continuity map, background jobs, and the
   **voice reviser** answering with edits (ADR 0009). Next in this milestone:
   - NILC-Metrix as an engine (density and complexity for a beginner reader;
     the book's R4) and spaCy `pt_core_news_lg` to make register rules precise
     (pronominal vs impersonal "se");
   - the continuity reviser as an agent over the repetition map (deliberate
     template vs seam), the interviewer (`intentions.md`), the intention
     guardian at every automatic gate, the writer.
4. **Companion** — *next: the four KDP products need it per language.*
   `kdp companion`: prompt pages, `pedido.txt`, QR targets and
   the start page generated from the manuscript, replacing the legacy
   exporter; link check; one repository for several books.
5. **Visual inspection** — rasterise the page types (part and chapter
   openings, contents, each callout, first and last page of each part) into
   contact sheets; a vision-capable agent and the author look at them.
6. **Research and fact-checking** — a sources ledger (URL, claim, opened at,
   result); a researcher and a separate fact-checker; "not found" is a valid
   answer; the sources gate.
7. **Writing-vice catalogue as checks** — the catalogue of §9 as automatic
   checks, recorded as practices with the check that enforces each (Cine
   Toaster's `enforced_by`), so the tool reports what still depends on a
   person remembering.
8. **Localisation** — *brought forward and delivered (2026-10-10, ADR 0012):*
   a language joins the book, the translator proposes each section as a
   candidate, the glossary is the book's, and the translation is measured
   against its source and goes stale when the source changes. Remaining:
   register rules for English in the style catalogue, a chapter gate per
   translated language.
9. **Cover and illustrations** — *the cover is delivered (2026-10-10, ADR
   0013):* art as records without lettering, every word set by a cover
   template from `meta.yaml`, sizes from a publisher profile and the book's
   trim and page count, the ebook cover and the print wrap from one design,
   measured; and art providers (ADR 0015: ComfyUI and Qwen Image Edit on
   RunPod, planned and priced before sent, lettering repainted out of an
   existing picture). Remaining: a first real run; an enlarging provider for
   300 dpi; an Art view; illustrations placed in the text; case-bound wraps.
10. **Ingestion, diagnosis and mapping** (modes B and C) — any existing
    material (the first to try: the author's ODT book in
    `JJDSNT/pipeline-de-publicacao`, whose pandoc conversion and ordering of
    chapters into parts are the starting point, KS-0008), catalogued and mapped (keep, revise, rewrite, move, discard,
    preserve) against the intention; mode C at 100% fidelity.
11. **KDP package and publishing** — metadata, categories, keywords,
    description, the publish gate, shown on the Readiness page; a manual
    upload package, since no public upload interface was found (browser
    automation exists and is brittle; not a path to depend on).
12. **Marketing** — positioning, sales copy, launch calendar.

13. **Fiction** (not the current focus; the author's suggestion) — from Cine
    Toaster: a cast of characters as book records (name, voice, traits,
    relationships, arc) with drift checks across chapters (the eye colour
    that changes in chapter 14 is the literary "face that drifts between
    shots"); an emotion catalogue (Cine Toaster's `emotion_assets`) and
    dialogue modes for the writer and reviser; dramatic cores and plot lines,
    with a map of where each character appears.

Later (noted 2026-10-04, at the author's request — not now):

- **Interface localisation.** Not a Portuguese interface: localisation support,
  with the person choosing the interface language (strings out of the
  components into per-language catalogues, starting with en and pt-BR). The
  interface language is independent of the book's language.

- **A gallery of themes** (the author, 2026-10-10: the Templates view, a
  list of names and descriptions, was not what he had in mind). Every template
  of the catalogue applied to the same sample text — a chapter opening, a
  callout, an exercise, a prompt, a part opening, in print and as an ebook,
  with the cover — shown side by side as pictures, so a design is chosen by
  looking, and applied to the book from there. It needs more than one theme to
  be worth browsing: new templates come with it.

- **An OPDS catalogue.** The built ebooks served over OPDS (from `kdp serve`,
  over the library it already knows — ADR 0014 — or a small server of its own), so the author reads each new build on a
  reader or phone without downloading files by hand. One feed per book,
  an entry per language, updated at each build.

Housekeeping: LanguageTool 6.8 (2026-05-05) is out; the pin is 6.6.

More templates join the catalogue whenever a book needs one.

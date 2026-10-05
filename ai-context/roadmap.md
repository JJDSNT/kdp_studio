---
id: CTX-ROADMAP
title: Roadmap
type: roadmap
status: active
owner: project
created_at: 2026-10-04
updated_at: 2026-10-04
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
3. **Specialised agents** — the assistant delegating to agents with declared
   tasks and scopes, each producing candidate versions or records:
   interviewer (`intentions.md`), architect, writer, voice reviser (with the
   vice catalogue), continuity reviser (whole book at once), the intention
   guardian at every automatic gate. Long tasks run as jobs, not chat turns.
4. **Companion** — `kdp companion`: prompt pages, `pedido.txt`, QR targets and
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
8. **Localisation** — `en` edition: glossary, stable exercise ids, the voice
   reviser of the target language, labels from the locale.
9. **Cover** — ebook cover and the print wrap cover computed from the frozen
   page count (spine), with cover templates in the catalogue; art and
   typography as separate steps.
10. **Ingestion, diagnosis and mapping** (modes B and C) — any existing
    material, catalogued and mapped (keep, revise, rewrite, move, discard,
    preserve) against the intention; mode C at 100% fidelity.
11. **KDP package and publishing** — metadata, categories, keywords,
    description, the publish gate; manual upload package when no integration
    exists.
12. **Marketing** — positioning, sales copy, launch calendar.

More templates join the catalogue whenever a book needs one.

# ADR 0008: Mature open tools are resources; the catalogue stays ours

Status: accepted (2026-10-04).

## Context

The author asked to lean on open, generic, robust solutions — and on ones with
real Brazilian Portuguese support — instead of rewriting what they already do
well.

Surveyed for pt-BR (2026-10-04):

| Tool | Origin | State | Decision |
|---|---|---|---|
| LanguageTool 6.6, pt-BR module | community | active, LGPL-2.1 | **adopted**: grammar, spelling, AO90 |
| Vale 3.24 | community | active, MIT | **adopted**: prose rules in YAML, the book's own styles |
| EPUBCheck 5.4 | W3C | active, BSD-3 | **adopted**: the reference EPUB validator |
| NILC-Metrix | NILC/USP | active, AGPL-3.0 | next: ~200 complexity metrics for pt-BR (density for a beginner reader) |
| spaCy `pt_core_news_lg` 3.8 | Explosion | active, MIT (model CC BY-SA) | next: POS and lemmas to make register rules precise |
| VERO (hunspell pt_BR) | LibreOffice | active, LGPL/MPL | not needed while LanguageTool covers spelling |
| CoGrOO | USP | last commit 2017 | not adopted |

## Decision

- **The catalogue is ours; engines are resources.** What the book must follow
  (practices, the book's decisions, approved exceptions) lives in the built-in
  catalogue and the book's `style.yaml`. Engines run under it and their
  alerts join the same report, mapped to file and line.
- **Engines see only the reader's text.** Prompts to agents and code are
  frozen literals written for a machine; they are never linted.
- **`kdp tools install <name>`** fetches a pinned release from its official
  source into `~/.local/share/kdp-studio/tools/`, verifies its checksum (the
  published one, or one pinned at the first verified download when the project
  publishes none), and touches nothing else. No `sudo`.
- Copyleft tools run as separate programs and are never vendored (Cine
  Toaster's ADR 0011).
- Engine defaults that fight the book are switched off per book: Vale's
  English spelling style is used only for English books; LanguageTool rules
  that contradict the voice guide go in `disabled_rules`, and the book's names
  and terms in `words`.

---
id: KS-0006
title: A second language — add_language, the translator, the glossary, measured translation
type: work
status: done
owner: project
created_at: 2026-10-10
updated_at: 2026-10-10
---

# What and why

The author's goal is the book in Portuguese and English, print and ebook, on
KDP. Localisation was milestone 8; it was brought forward because everything
it stands on (per-language manuscript, builds, checks, labels, candidate
versions) was already delivered. ADR 0012.

# Done

- `translation.py`: `add_language`, `glossary` (`glossary.yaml`),
  `compare_translation`, `section_states` (untranslated, translated, stale,
  unrecorded), `report`, `confirm_translation`, `write_glossary`.
- `agents/translator.py`: `translate_section`, `translate_book`,
  `translate_meta`, `propose_glossary`; job kinds `translate_section`,
  `translate_book`, `add_language`, `propose_glossary`.
- Commands `add_language`, `confirm_translation` (a person's), `write_glossary`
  (creates; replacing is a person's).
- CLI: `kdp language add`, `kdp glossary`, `kdp translate`, `kdp translation`.
- Control room: the Translation view, the translation state in the book's
  contents, the measurements against the source in the version comparison;
  `/api/translation`. Assistant: the `translation` read and the proposals
  `add_language`, `propose_glossary`, `translate_section`, `translate_book`.
- `structure.add_section` / `add_part` write every language; a structure
  change is validated in every language.

# Decisions

- Stubs rather than missing files: a half-translated language loads and
  builds, and "untranslated" is a state, not an error.
- Differences in facts warn instead of failing: an adaptation may convert a
  unit or localise an address on purpose. Structure fails.
- The source digest travels in the candidate's task, so no new record is
  needed for the common path; only the author's confirmation is new state.
- An ordinal is its number ("dia 14" / "the 14th"): found on the real chapter.

# Validation

- 69 tests pass; flake8 clean; the frontend builds.
- Real model on a copy of *A Era dos Agentes*: see ADR 0012. The original
  book was not touched.
- The Translation view opened in a headless browser on that copy.

# Remaining

- On the book itself (the author's acts): add `en`, read the glossary, read
  one translated chapter, then translate the rest and review each.
- English register rules in `style/en.yaml` as the edition meets them.
- A chapter gate per translated language; the nested findings table in the
  Translation view is cramped.
- Companion pages (`/en/` addresses the QR codes point to) and covers per
  language are milestones 4 and 9.

---
id: KS-0007
title: Covers — art records, the cover template, publisher profiles, the cover check
type: work
status: done
owner: project
created_at: 2026-10-10
updated_at: 2026-10-10
---

# What and why

The four KDP products need a cover each. The author asked for KDP Studio's
own structure for covers and illustrations (after Cine Toaster's), with words
set by code because models misspell, and sizes that follow the book and the
publisher. ADR 0013.

# Done

- `art.py`: `art/<id>` with its record; `kdp art add/list`; `/api/art`.
- `cover.py`: publisher profiles (`publishers/kdp.yaml`, book overrides),
  wrap geometry, art cropped to each panel around a focus with the scrim
  baked in, `build_cover` (ebook JPEG, print wrap PDF, a preview to look at),
  `cover.json`.
- `templates/cover/nocturne/`; `catalog` knows the `cover` kind.
- `checks/cover.py`; `run_checks` and the `build`/`check` commands take
  `cover`; `kdp build` builds print, cover, ebook in that order; the ebook
  embeds the built cover when the author supplied none.
- Editions view shows the cover pictures; the assistant may build and check
  the cover.
- The sample book has a typographic cover.

# Decisions

- LuaLaTeX rather than drawing text on a bitmap: vector text in the print
  file, the interior's fonts, real letter spacing.
- The cover is an entry under `editions` so build, check, the Editions view
  and the last-report machinery apply unchanged.
- The wrap is refused by the check, not by the build, when the text is not
  frozen: a proof before freezing is useful, a silent stale spine is not.

# Validation

- 74 tests pass (geometry, a book's own profile, art records, a built cover
  measured, a stale wrap refused); flake8 clean; the frontend builds.
- Rendered and looked at: sample book; a copy of *A Era dos Agentes* in
  pt-BR and en with a stand-in picture. The original book was not touched.

# Remaining

- An image provider adapter that generates lettering-free art and writes its
  record; illustrations placed in the text with their records checked.
- The book's real art without lettering, at 300 dpi (its current
  `cover/pt-BR/art.jpeg` is 1024 × 1536 with the words drawn in).
- Case-bound wraps; an ISBN/price line; the author's photograph.

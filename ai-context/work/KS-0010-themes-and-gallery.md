---
id: KS-0010
title: Two new themes (Folio, Signal) and the gallery over a specimen text
type: work
status: done
owner: project
created_at: 2026-10-10
updated_at: 2026-10-10
---

# Done

- `templates/{print,ebook,cover}/{folio,signal}/`.
- `specimen/`: the lorem ipsum book every theme is shown on.
- `gallery.py`: `themes`, `build` (cached renders), `apply_theme`; the
  `set_theme` command; `kdp theme`; `/api/gallery`, `POST /api/gallery/build`,
  `/gallery/<key>/…`.
- The Themes view (Produce) replaces the list of templates: per theme, the
  cover, four kinds of page, the ebook live, the wrap; click to enlarge;
  "Use this theme". Publisher profiles stay below.

# Validation

82 tests pass (themes across media, the command on inline and block
`editions`, every theme rendered and its pages tagged); flake8 clean; the
frontend builds. Looked at: every theme's pages and covers; the view itself.

# Remaining

- Nocturne keeps a callout that may leave its label alone at the foot of a
  page (changing it would move the pages of *A Era dos Agentes*: the
  author's call).
- Seeing a theme on the author's own chapter before taking it; palette role
  names; more trims than 6 × 9; choosing media one by one.

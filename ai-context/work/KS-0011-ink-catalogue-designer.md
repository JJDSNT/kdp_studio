---
id: KS-0011
title: The gallery in two media, black ink, the person's catalogue, the designer
type: work
status: done
owner: project
created_at: 2026-10-10
updated_at: 2026-10-10
---

# Done

- Gallery: Print and Ebook modes; black ink and e-ink toggles; renders keyed
  by ink; stale renders pruned; overfull and underfull of the specimen kept.
- `build.print_colors` / `grey`, `editions.print.ink`, `mono:` in a print
  manifest; `checks.kdp_print.colour_pages` and the `ink` finding;
  `premium-color` paper in the KDP profile.
- `catalog.user_root()` as a layer ("yours"); `set_theme` carries such a theme
  into the book.
- `agents/designer.py`: `design_theme`, `assemble`, `base_blocks`,
  `installed_fonts`; job kind `design_theme`; `kdp theme <book> <name>
  --design --brief … [--based-on …] [--reference URL]`; the form in the
  gallery; provenance shown per theme.
- Assistant: the `themes` read, the `set_theme` and `design_theme` proposals,
  a paragraph on design in its instructions.

# Validation

86 tests pass (greys, a black interior measured, a designed theme built
before it is catalogued and carried into the book, a block that runs code or
names a missing font never catalogued); flake8 clean; the frontend builds.
Real model: ADR 0017.

# Remaining

- `ink: black` is written in book.yaml by hand; no command or button sets it.
- A callout may still leave its label alone at the foot of a page.
- A designed theme cannot be revised by instruction, nor removed from the
  catalogue, from the tool; trims other than 6 × 9.

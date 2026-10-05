---
id: KS-0004
title: The chapter loop, commanded through the assistant
type: work
status: done
owner: project
created_at: 2026-10-04
updated_at: 2026-10-04
---

# What and why

The author: a book is simpler than a film; the work is revising chapter by
chapter and reordering; the voice, once chosen (possibly on a pilot chapter),
applies to the whole book; almost everything is commanded through the AI.

# Done

- `structure.py`: moves of sections and parts, `contents` block rewritten in
  place, impact (renumbering, references by number whose target changed).
- `agents/edits.py` (shared by every text agent), `agents/reviser.py`
  (`revise_section` by instruction and scope); the voice reviser on the
  shared core; the approved voice pilot in every agent's context.
- Gates: `chapter` per section, `voice` on a pilot or on the guide;
  `approve_chapter`; review status in the overview, the book table and the TOC.
- Assistant: `revise_section` and `reorder` proposals, both confirmed; it is
  told the author's way of working.
- Control room: review badges and progress, "Approve chapter", an instruction
  box for the reviser, the manual editor moved last; rewritten paragraphs
  shown whole in the comparison; a favicon.
- Jobs are stored per book and location.

# Validation

- 51 tests pass; flake8 clean; the frontend builds.
- Headless browser on a copy of *A Era dos Agentes*, real model: the chapter 8
  opening revised from a chat instruction (job, candidate, the reviser listing
  what it removed and moved); chapter 13 moved before 12 after "Sim", with the
  assistant warning of a narrative dependency the code cannot see; chapter 9
  approved and shown as approved.

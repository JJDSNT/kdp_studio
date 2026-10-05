# ADR 0010: The chapter loop, commanded through the assistant

Status: accepted (2026-10-04).

## Context

The author's own workflow, stated plainly: a book is simpler than a film. The
work is revising chapter by chapter and reordering chapters; the voice, once
chosen, is applied to the whole book; changes are commanded through the AI
far more than typed by hand.

## Decision

- **Each chapter carries its review**: a `chapter` gate per section records
  that the author approved it *as it reads now*; when the text moves, the
  book shows "changed since approval". `approve_chapter` opens and decides
  that gate in one act, and only a person runs it.
- **Reordering is a command** (`reorder`, `kdp move`): a section before/after
  another or into a part, or a part before/after another. It rewrites only the
  `contents` block of `book.yaml`, commits with its reason, and reports which
  chapters were renumbered and every "capítulo N" in the prose whose target
  changed. The assistant proposes it and asks first.
- **Changing text is an instruction to the reviser** (`revise_section`): the
  author's words, a scope, the book's intention and voice as context; the
  reviser answers with edits (ADR 0009) and the result is a candidate version.
  The assistant prefers this to writing a version itself.
- **The voice is chosen once and applied to every chapter.** The voice gate
  may be judged on a pilot chapter (the specification's gate 3) or on the
  voice guide; the latest approved pilot is given to every agent, on every
  chapter, as the reference of the book's voice.
- **Editing by hand stays, but last.** The byte-for-byte editor is a tab, not
  the way of working; nothing new is invested in it.

# ADR 0001: A book lives outside the repository, and its files are authoritative

Status: accepted (2026-10-04).

## Context

The tool exists to produce a real book, *A Era dos Agentes*, and must stay
useful for any other. Cine Toaster, the same author's filmmaking tool, proved
the model: the production is an external directory the tool opens.

## Decision

- A book is a directory the author owns, usually its own (private) git
  repository. KDP Studio never creates one inside its checkout; the only
  book-shaped directory here is `examples/sample-book`.
- The book's files are the source of truth. Builds are regenerated and
  git-ignored; deleting them loses nothing.
- Authored files are never rewritten by KDP Studio. What it decides lives in
  `state.json` beside them.

## Consequences

A book is readable, versionable and editable without KDP Studio. Every command
takes a book path.

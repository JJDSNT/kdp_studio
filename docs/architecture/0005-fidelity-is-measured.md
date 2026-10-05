# ADR 0005: Fidelity is measured by machines, never judged by a model

Status: accepted (2026-10-04).

## Context

"Did anything change?" is the question an LLM answers worst: a model that
"fixed" a date in passing will also report that nothing changed. The origin
specification (§5.19, §7.1) makes the fidelity auditor deterministic.

## Decision

- **Manuscript:** exact bytes (`digest`) where a passage must not change;
  otherwise the reader's words compared after a *declared, versioned* list of
  normalisations, each counted in the report. A list that has to grow for a
  text to pass is a warning, not a fix.
- **Fact inventory:** numbers, dates, URLs, code and proper names of both
  texts are compared; anything that appears, disappears or changes is
  reported, even when the new value is right.
- **Editions:** PDF and EPUB are compared by extracted text, page by page and
  across the book — equivalence after typesetting, not bytes.

## Consequences

The auditor ran first on the migration of *A Era dos Agentes*: it caught a
real bug (four "NA PRÁTICA" callouts silently left unconverted) before
anything was written. Page by page, the new pipeline reproduced the legacy
PDF, and its only text differences were corrections.

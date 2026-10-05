# ADR 0003: One book format — Markdown with three constructs, structure in YAML

Status: accepted (2026-10-04).

## Context

The legacy manuscript encoded structure in prose: "## Capítulo 11 — …",
"> **CONCEITO — Nome**", "### Experimente — …". The generators recognised them
with regular expressions, in Portuguese, and printed whatever they did not
recognise (`**Netlify**` reached the PDF with its asterisks). A translation
would have needed new regular expressions.

## Decision

- Structure (order, parts, editions) is language-neutral YAML in `book.yaml`;
  what changes with the language lives in `manuscript/<language>/meta.yaml`.
- Each section is a Markdown file with a small frontmatter; numbers and labels
  are generated in the edition's language.
- Three constructs extend CommonMark: callouts (`> [!kind]`), exercises
  (`::: exercise`) and prompts (`> [!prompt] ID`). Raw HTML is refused; HTML
  comments are editorial notes that never reach an edition.
- Section ids are file names, identical across languages.
- The schema is English; content stays in its language.

## Consequences

The format reads well on GitHub, parses with a standard parser
(markdown-it-py), and a translated book needs no new code. Existing books are
migrated once, with a fidelity audit proving the words did not change.

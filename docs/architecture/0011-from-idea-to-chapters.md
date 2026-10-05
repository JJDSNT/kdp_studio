# ADR 0011: From an idea to chapters — research, plan, writer; the book gains and loses chapters

Status: accepted (2026-10-04).

## Context

The author's whole flow: an idea; research; a draft of the content; divided
into chapters; written chapter by chapter; reviewed chapter by chapter, with
the book gaining, losing and reordering chapters along the way.

## Decision

- **`kdp new`** starts a book from an idea: `book.yaml` with no contents, the
  idea as the first `intentions.md`, a git repository. The assistant then
  interviews the author (for whom, from where to where, what the book is not,
  what the reader takes away) and writes `intentions.md` with their words,
  after their yes. The intention is never derived from a topic.
- **The researcher** searches the web and opens what it cites (through the
  Claude Code CLI's WebSearch/WebFetch with the author's login, or the API's
  server tools). Its dossier goes to `research/<slug>.md` — findings with
  sources and confidence, and what was *not* found — and every source to the
  ledger `research/sources.yaml` with the date it was opened.
- **The architect** proposes parts and chapters; each chapter has a `synopsis`
  and a `promise` (what the reader can do after it), and names its research.
  The plan is a candidate in the book's state; adopting it is the author's act
  and creates the chapters as stubs. Once a book has chapters, the plan is
  advice: chapters are added (`add_section`), removed (`remove_section`, into
  `archive/removed/`), and moved one by one.
- **The writer** writes one chapter to its promise, given the whole plan (so it
  does not take another chapter's material), the end of the previous chapter,
  the research it names, the intention, the approved voice and the vices to
  avoid. The frontmatter is kept byte for byte; the body is a candidate
  version. What it could not ground goes into `to_check` and HTML comments.
- The model may read the web only when researching; no agent is ever given a
  file, shell or edit tool.

## Validation

A book created from an idea with the real model: research (10 sources opened,
12 findings, the not-found stated with reasons: an unreadable PDF, a 403, a
different species in the English sources), a 6-chapter plan with promises and
named gaps, adopted, and chapter 1 drafted (2,544 words; the writer stated
which numbers were its own estimate rather than a source's).

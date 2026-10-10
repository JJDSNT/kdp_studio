# ADR 0012: A second language — the translator proposes, code measures, the source is tracked

Status: accepted (2026-10-10).

## Context

The author wants the same book in Portuguese and English, in print and as an
ebook. The format already keeps one directory per language with section ids
shared across them (ADR 0003), builds and checks already run per language, and
labels come from the locale. What was missing: a way for a language to *join*
a book, an agent that adapts the text (docs/origin, §5.13: "translate and
ship" is the anti-pattern), and an answer to the two questions a translation
raises that a model must not answer — did everything that had to survive
survive, and does the translation still correspond to the source?

## Decision

- **A language joins through one command**, `add_language`: `book.yaml` gains
  it (only the `languages` block is rewritten), `manuscript/<language>/meta.yaml`
  is created with its own ebook identifier, and every section gets a stub —
  the source's frontmatter, no body. A stub is "untranslated", so the book
  loads, builds and reports from the first minute. Files the author already
  put there are left alone. `add_section` and `add_part` now cover every
  language of the book.
- **The translator works section by section and answers with a candidate
  version** (ADR 0006) in the target language: the translated frontmatter
  (title, contents title, synopsis, promise) and body, the adaptations it made
  with why, and the terms it met outside the glossary. It reads the intention,
  the voice, the glossary, the book's own localisation notes, the titles
  already chosen in the target language and how the previous section ends
  there. The author reads, adopts or sends back, as with any text. The
  translator of `meta.yaml` writes only at the creation of the language; from
  then on the file is the author's.
- **The glossary is the book's** (`glossary.yaml`): terms with their forms per
  language, names never translated, and the localisation notes to read. The
  translator may draft it once; it is never overwritten by an agent.
- **What must survive is measured by code** (`translation.py`), per section:
  prompt ids in order, exercises, callouts by kind, footnotes, images, tables
  and code blocks (a difference fails); headings, inline code, URLs, numbers
  with separators normalised per language, editorial comments, length ratio,
  paragraphs left identical, glossary terms and kept names (a difference
  warns, because an adaptation may be deliberate). Whether it reads well is
  never measured: it is the author's.
- **A translation remembers its source.** Each candidate records the digest
  of the source it was made from; when the source changes, the section shows
  as `stale`. The author either translates again (the translator is given
  what stands, to keep what still corresponds) or confirms that it still
  corresponds (`confirm_translation`, a person's act, kept in `state.json`).
  A translation made by hand is `unrecorded` until confirmed.
- **Order of work, said to the assistant too**: glossary, one chapter read
  by the author in the target language, then the rest. Chapter gates remain
  about the source; `freeze` of a language is the approval of its text.

## Consequences

- Voice review, style checks, builds and KDP checks apply to the new language
  with no new code; the style catalogue of a language grows when an edition
  meets its vices.
- Not done here: the companion pages and the cover per language (roadmap 4
  and 9), and a per-chapter gate in a translated language.

## Validation

On a copy of *A Era dos Agentes* with the real model: `en` added in 21 s
(title, eight part titles and the copyright page translated, with the
translator's reasons); a glossary of 97 terms and 62 kept names drafted from
the book and its `editorial/07-localizacao.md` in 90 s; chapter 4 translated
in 42 s (1,212 words for 1,093; structure, prompt id, code and URLs
identical; one glossary term flagged; four adaptations declared, among them
the mnemonic of the exercise code). The English print interior and ebook
build; every measured KDP check passes and EPUBCheck reports 0 errors. Pages
rasterised and looked at: chapter label, "Try it", the prompt panel with the
`/en/` address.

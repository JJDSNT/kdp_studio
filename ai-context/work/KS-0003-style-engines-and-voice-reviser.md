---
id: KS-0003
title: The vice catalogue as checks, open engines, jobs, and the voice reviser
type: work
status: done
owner: project
created_at: 2026-10-04
updated_at: 2026-10-04
---

# What and why

Milestone 3 starts where the specification starts the agents: the writing
vices as automatic checks (§9), then a reviser of voice (§5.6) that can be
trusted not to wander. The author asked, along the way, that book-specific
decisions stay with the book ("prática, nunca exercício" is this book's), and
that mature open tools — with Brazilian support — be used as resources.

# Done

- Catalogue (`style/pt-BR.yaml`, `style/en.yaml`) with coverage; the book's
  `style.yaml` (decisions, approved exceptions, refrains, engines, glossary).
- Engines: LanguageTool (local server, pt-BR), Vale; EPUBCheck in the ebook
  checks. `kdp tools install` with pinned, verified releases (ADR 0008).
- Continuity map: recurring passages across sections, grouped.
- Jobs; the voice reviser answering with edits applied by KDP Studio
  (ADR 0009); CLI `style`, `continuity`, `revise`, `tools`; Style, Continuity
  and Jobs views; the assistant reads style and starts the reviser after asking.
- In the book repository: `style.yaml` committed (from editorial/05).

# Validation

- 41 tests pass; flake8 clean; the frontend builds.
- On *A Era dos Agentes*: 15/22 practices enforced; 35 findings; the approved
  exception of chapter 3 respected; EPUBCheck 0 errors, 0 warnings.
- LanguageTool on two chapters: real hints (comma after "Na prática", a
  number-agreement doubt) and expected noise (names → the book's `words`;
  "depois de → após" contradicts the voice guide → `disabled_rules`).
  Vale's English spelling flagged 1,444 Portuguese words → base style limited
  to English books.
- Voice reviser with the real model: chapter 6, 5 enclises → 5 edits applied,
  0 remaining, no fact changed, 13 s; chapter 7 from the control room in a
  headless browser: job ran, 3 edits, version compared, no console errors.

# Remaining

- `se-impessoal` cannot tell "o que se encaixa" (pronominal) from an
  impersonal "se"; spaCy POS would.
- The book's `style.yaml` does not enable LanguageTool yet: that, its
  `disabled_rules` and `words`, are the author's choices.

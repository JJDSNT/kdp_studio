# ADR 0018: A critic that looks at the pages; the designer answers only when asked

Status: accepted (2026-10-10). Extends ADR 0017.

## Context

The designer never saw what it drew, and code can say a theme builds, not
whether it is any good. The author asked for a visual reviewer with critical
and artistic sense: a critic of the work.

## Decision

- **The model may be shown pictures** (`Model.ask(..., images=…)`): they travel
  inside the message. No agent is given a file tool for it.
- **The critic** (`agents/critic.py`) is shown a theme's rendered pages — the
  cover, a part opening, a chapter opening, callouts, an exercise, then a
  chapter and an exercise in black ink — and judges character first (a point
  of view, or a competent default; one idea carried through, or several; what
  is borrowed and from where), then craft. Each problem is a `defect`, a
  `weakness` or `taste`, with where it is and a fix the designer can act on.
  It does not praise by default. Its criticism is kept
  (`$XDG_DATA_HOME/kdp-studio/critiques/`) and shown beside the theme.
- **Criticism is advice, and the loop waits for a person.** After a theme is
  drawn the critic looks once, and the work stops. Drawing again
  (`revise_theme`: the author's instruction, or the last criticism) happens
  when the author asks. The designer can answer the critic by itself
  (`rounds`) only when told to: the first run of that loop took eight minutes
  unattended, and the author asked, rightly, why it had gone on without them.
- **A theme the designer drew can be revised and removed**: its answers are
  kept (`design.json`), and a revision that does not build leaves the theme as
  it was.

## What the first run showed

`novela`, real models, one automatic round, 7m51s: the numerals grew from a
timid 58 pt to a Bookman Demi that carries the page, the part opening took the
chapter's order, the cover took the interior's paper and accent, and two
stranded labels were gone — and the revision set the footnote mark full size
on the baseline, a new defect the second criticism caught. The critic also
asked for what the designer cannot do: the cover's composition and the print
callouts are the template's, outside the designer's blocks. The critic
reported an overfull line the log does not confirm: what it sees is a
judgement, not a measurement.

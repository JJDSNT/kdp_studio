# ADR 0020: One flow for an agent's work, on LangGraph; critique and redo are always there

Status: accepted (2026-10-10). Revises ADR 0002 where it kept LangGraph to the
chat assistant in practice, and ADR 0018's hand-written loop.

## Context

ADR 0002 said LangGraph runs the agents; only the assistant did. Every other
agent was a Python function, and where one needed a loop — the designer
rebuilding until the specimen compiled, then answering its critic — the loop
was written by hand, inside the agent. That put in each agent what belongs to
none: retries, review, waiting for a person. The author's point: a manifest
gives the direction; flow is what the framework we already carry is for; and
being able to critique and redo, always, is the part worth keeping. The
caution ADR 0002 took from Cine Toaster — a paid, hours-long production whose
resumed nodes resubmitted work — is another scenario, and is not a reason to
leave the framework unused here.

## Decision

- **One graph** (`agents/flow.py`), the same for every agent on it:
  `draft → check → land → hold`, with `check` sending a failed answer back to
  `draft` a bounded number of times, and `hold` an **interrupt** from which the
  author chooses `critique` (a `review` node, then back to `hold`), `redo`
  (back to `draft`, in their words or answering the last criticism) or `done`.
- **The parts are separate things.** Direction is the manifest or the agent's
  prompt. *Checks* are deterministic and named (`edits_apply`,
  `facts_unchanged`, `report_complete`, the designer's `specimen_builds`); a
  manifest declares them. *Landing* is a command. *Review* is another agent:
  the critic of themes for a theme, a critic of the work — told the role,
  shown the same material and the answer — for a manifest agent.
- **Nothing is redone unasked.** The work lands and the flow waits. A job in
  that state is `waiting`; the Jobs view shows the three choices. A caller
  with nobody to ask (the command line, a test) scripts the answers.
- **What lands is in the book.** The interrupt is alone in its node, so
  resuming re-runs nothing that writes; the wait itself is a checkpoint (see
  below), disposable without losing a report, a version or a theme.
- **A failed check never lands.** An agent whose edits do not apply, or move
  a fact under a wording scope, is told why and answers again; with no answer
  left the work fails and nothing is written.

## Every agent is on it

The researcher (`sources_cited`), the architect (`plan_complete`), the writer
(`manuscript_format`), the reviser and the voice reviser (`edits_apply`,
`facts_unchanged`), the translator (`structure_kept`: what a translation may
not lose, measured before it lands, three answers at most), the designer
(`specimen_builds`) and every manifest agent. Each is four things given to
the flow — how the model is asked, its named checks, how the answer lands, who
reviews it — and none of them owns a loop. `translate_book` runs the
translator's flow section by section, with nobody held.

## The wait survives a restart

A job's flow is checkpointed on disk beside the job store (`flows.sqlite`,
LangGraph's SQLite checkpointer). A job kind on the flow is declared by a
function that only *builds* the work from the payload, so a runtime that
restarted builds it again and resumes the graph at its hold. What a result
needs travels in the graph's state. The assistant can answer a held job from
the chat (`answer_job`), after asking.

## Validation

Scripted models: an answer that fails its check goes back and, failing again,
never lands; a job waits, is critiqued, redone answering the criticism, and
closed; a job answered after the runtime that held it is gone. Real model, on
a copy of *A Era dos Agentes*: the KDP packager and its reviewer in 2m27s;
the translator on chapter 1 in 28 s, eighteen measurements passing before the
version was recorded.

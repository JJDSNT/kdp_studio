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
- **What lands is in the book; the wait is not.** Checkpoints are in memory.
  The interrupt is alone in its node, so resuming re-runs nothing that
  writes. A runtime that stops forgets a held flow and reports the job done:
  its reports, versions and themes are already records.
- **A failed check never lands.** An agent whose edits do not apply, or move
  a fact under a wording scope, is told why and answers again; with no answer
  left the work fails and nothing is written.

## Not yet on the flow

The researcher, architect, writer, the two revisers and the translator are
still plain functions run as jobs. Each has a check that would sit in the
graph as it is (the translator's measurements, the reviser's fidelity audit)
and would gain critique and redo by moving.

## Validation

Scripted models: an answer that fails its check goes back and, failing again,
never lands; a job waits, is critiqued, redone answering the criticism, and
closed. Real model: the KDP packager on a copy of *A Era dos Agentes*, then
its reviewer, on the graph, in 2m27s.

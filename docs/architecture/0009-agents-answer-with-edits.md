# ADR 0009: Production agents answer with edits; scope is enforced by construction

Status: accepted (2026-10-04).

## Context

A reviser asked to rewrite a chapter "changing only the register" will, now
and then, also improve a date. The fidelity auditor catches it after the fact;
it is better if it cannot happen.

## Decision

- A production agent that changes text (first: the voice reviser) answers
  with **edits**: an exact passage, its replacement, the practice it fixes and
  why. KDP Studio applies them itself. Everything outside the edits stays byte
  for byte.
- An edit is refused when its passage is not found exactly once, overlaps
  another edit, or touches what must never change: the frontmatter, a prompt
  to an agent, code.
- The result is a candidate version (ADR 0006) with the task recorded — the
  findings, the applied and refused edits, what the agent chose to skip and
  why — and audited for fidelity like any other.
- Agent work runs as a **job** (`jobs.py`): operational state outside the
  book, progress visible, results written only when complete, a job left
  running by a stopped runtime marked `interrupted`.

## Consequences

The agent may still choose a poor rewording; the author sees it, word by word,
before anything changes. It cannot reach outside the passages it named.

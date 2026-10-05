# ADR 0006: Text versions are candidates; a person's edit is written byte for byte

Status: accepted (2026-10-04); implemented in milestone 2 (`versions.py`, the control room).

## Context

The author asked for good versioning and editing of the text. Cine Toaster
has the model: generated alternatives are *takes*, kept side by side, chosen
with a reason, never discarded; and a person's edit to the screenplay is
written byte for byte after checking the file is still the one they opened.

## Decision

- **A rewrite by an agent is a candidate version** of a section, never an
  in-place edit. It carries the task it answered, the declared scope, the
  agent and the instruction version. The author compares it with the current
  text (word diff plus the fidelity report) and adopts it, or not, with a
  reason. Nothing is discarded.
- **Adopting a version is a command**: it writes the section and commits it in
  the book's git repository with the reason, so the history answers "why does
  this chapter read like this?".
- **A person's edit** (the editor in the control room) is written byte for
  byte, refused if the file changed since it was opened.
- The fidelity auditor runs on every candidate: a change outside the declared
  scope is a violation even when it is an improvement.

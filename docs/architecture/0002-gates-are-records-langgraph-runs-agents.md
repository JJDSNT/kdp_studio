# ADR 0002: Gates and workflow state are records in the book; LangGraph runs the agents

Status: accepted (2026-10-04).

## Context

The origin specification (docs/origin, §1) proposes LangGraph for the whole
pipeline: long, resumable, full of human gates. Cine Toaster measured exactly
that question (its ADR 0017) on a paid production workflow and found:

- resuming after the checkpoint store was lost failed; a new run recovered
  only because the nodes re-read the production records;
- an interrupted node re-runs from its start, so a gate opened in a node was
  opened again on every resume, and a retry re-submitted paid work;
- LangGraph was excellent as the agent behind the chat: context from the
  interface, shared state, interrupts rendered in CopilotKit.

A book takes weeks and must survive the loss of any cache.

## Decision

1. **Gates, decisions and where the book stands are records in the book**
   (`state.json`, git history). Advancing is idempotent because it reads those
   records. The specification's rule holds: no edge skips a gate, and a gate
   that gets no answer waits; it never times out into a default.
2. **LangGraph runs the agents** (coordinator, researcher, writer, revisers,
   translator, cover…), as an optional extra behind the agent adapter
   boundary. Its checkpoints are disposable operational state.
3. **An agent acts only through commands**, recorded with an agent actor, and
   **never decides a human gate**: it prepares the decision.
4. **CopilotKit (v2) over AG-UI** carries the agents to the interface, with
   what the author is looking at sent as context.
5. **The model sits behind a model adapter**: the Claude Code CLI with the
   author's own login first (no key stored), an API key otherwise. Small
   models, including local ones, serve extraction and classification.

## Consequences

The pipeline is a set of commands and checks that any caller can drive; the
agents are one caller. A subgraph that is genuinely open deliberation (an
editorial board debating a proposal) may use another framework inside one
node, as the specification allows.

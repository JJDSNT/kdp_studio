---
id: KS-0002
title: Control room, text versions and the assistant as a CoAgent
type: work
status: done
owner: project
created_at: 2026-10-04
updated_at: 2026-10-04
---

# What and why

The author asked for good versioning and editing of the text, and for
CopilotKit with LangGraph agents (CoAgents). Both land on the same surface: a
control room where the author reads, edits, compares and decides, beside an
assistant that sees the same screen.

# Done

- `history.py` (one commit per write, only the touched paths), `versions.py`
  (candidates, word diff, fidelity, scope violations, adopt/reject, byte-for-byte
  save), `commands.py` (single write boundary, agent subset), `checks/run.py`,
  `proofs.py`, `server.py` (`kdp serve`).
- `assistant/`: model adapters (Claude Code CLI, Claude API with streaming,
  explicit effort and server-side fallback), reads, the LangGraph graph
  (reads, runs, proposals behind an interrupt, navigation as shared state),
  the host (agent thread + supervised Copilot Runtime sidecar).
- `frontend/`: React + Vite control room; CopilotKit v2 panel loaded on demand.
- Makefile; `kdp doctor` reports the control room, the assistant and the CLI.
- ADR 0007; ADR 0006 marked implemented.

# Validation

- 33 tests pass (versions, command boundary, assistant graph with a scripted
  model); flake8 clean; the frontend typechecks and builds.
- End to end on a copy of *A Era dos Agentes*, real model through the Claude
  Code CLI:
  - a question about the chapter on screen: the agent read that section by
    itself (page context arrived) and answered correctly in ~10 s;
  - "make one sentence leaner, wording only": the interrupt arrived; on yes a
    candidate was recorded as an agent, committed, and the screen moved to the
    comparison; the fidelity report shows exactly that sentence changed, no
    fact, no violation;
  - in a headless browser: the chat answered, the confirmation card appeared,
    "Sim" opened the gate as the agent and the screen followed; no console
    errors.
- Fixed on the way: FastAPI could not resolve `Request` under postponed
  annotations (proxy and commands endpoints); the assistant described a
  proposal as done before the yes.

# Remaining

- Long agent work (drafting a chapter, a whole-book continuity read) should
  run as jobs with progress, not inside a chat turn.
- The page does not refresh by itself when the agent writes without moving the
  screen (it refreshes on navigation).

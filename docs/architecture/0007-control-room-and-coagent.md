# ADR 0007: The control room is React served by Python; the assistant is a CopilotKit CoAgent

Status: accepted (2026-10-04).

## Decision

- **`kdp serve <book>`** runs a local FastAPI runtime (the `studio` extra)
  over one book: queries (`/api/book`, `/api/section`, `/api/version`,
  `/api/editions`, `/api/proofs`, documents) and one write endpoint,
  `POST /api/commands`, which always acts as the person at this machine.
- **The interface is React + TypeScript + Vite** (`frontend/`), built into the
  Python package. No Next.js: the Python runtime is the server, and Node is a
  build tool — except for the optional Copilot Runtime below.
- **The assistant is a CopilotKit (v2) CoAgent** over AG-UI. The LangGraph
  graph runs in the Python process (`ag-ui-langgraph`); the Copilot Runtime is
  one bundled Node file, supervised and restarted, proxied at
  `/api/copilotkit`, telemetry off, inspector off. CopilotKit is loaded only
  when the panel opens.
- **Shared state is navigation only.** The page sends what the author sees
  (`useAgentContext`); the agent may move the screen (`navigate` in its
  state). Anything that writes into the book goes through an interrupt
  (`useInterrupt`) and then a command with an agent actor.
- **The model is an adapter.** `claude-cli` (the author's Claude Code login,
  no key stored) is the default; `claude-api` (SDK, streaming, explicit
  effort, server-side fallback) serves any other use.

This is the path Cine Toaster measured (its ADRs 0017 and 0018), adapted to a
book.

## Consequences

- An agent is one more caller of the commands; it never gains a path the
  author does not have, and has fewer (`commands.AGENT_COMMANDS`).
- Conversations are disposable (in-memory checkpoints); the book is not.
- `make ui` is needed once per clone for the interface; `kdp doctor` says so.

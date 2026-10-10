---
id: KS-0014
title: One flow on LangGraph: draft, check, land, hold; critique and redo for every agent on it
type: work
status: done
owner: project
created_at: 2026-10-10
updated_at: 2026-10-10
---

# Done

- `agents/flow.py`: the graph, `Flow` (start, answer), scripted answers.
- `jobs`: the `waiting` state, `HELD`, `answer`; `POST /api/jobs/answer`; the
  Jobs view's Critique / Redo / Close.
- Designer: `ThemeWork` on the flow (the hand-written loop is gone).
- Manifest agents: `ManifestWork`, named `CHECKS`, `checks:` and `attempts:`
  in a manifest, a critic of the work as reviewer.
- `add_report` never reuses a file name.

# Validation

95 tests pass; flake8 clean; the frontend builds. Real model: ADR 0020.

# Remaining

Move the researcher, architect, writer, revisers and translator onto the flow;
let the assistant answer a held job from the chat; show a job's reviews in the
Jobs view beyond the last summary.

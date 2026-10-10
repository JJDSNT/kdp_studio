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

- Second pass: the researcher, architect, writer, reviser, voice reviser and
  translator on the flow (`SimpleWork`), each with a named check; job kinds
  declared with `flow_kind`; checkpoints on disk (`flows.sqlite`) and work
  rebuilt from the job so a held flow survives a restart; the assistant's
  `answer_job`; reviews listed in the Jobs view.

# Validation

97 tests pass; flake8 clean; the frontend builds. Real model: ADR 0020.

# Remaining

- `add_language`, `propose_glossary`, `translate_book`, `critique_theme`,
  `generate_art` and `create_agent` are jobs without a hold: none is a single
  answer one would redo in place.
- The checks added here refuse what used to pass: a plan naming research
  that does not exist, a chapter with raw HTML, a translation that drops a
  callout. That is the point, and it changed three test fixtures.
- A held job keeps its wait until closed: nothing prunes old ones.

---
id: KS-0013
title: Agents as manifests, thirteen agents, the meta-agent; a critic that knows who owns what
type: work
status: done
owner: project
created_at: 2026-10-10
updated_at: 2026-10-10
---

# Done

- `agents/manifest.py`: readers, `parse`, `manifests`, `knowledge`, `run`; job
  `run_agent`; command `add_report`; `reports/` listed under Documents.
- `agent_manifests/*.yaml` (13) and `knowledge/kdp-listing.md`.
- `agents/meta.py`: `create_agent` (parse, trial, catalogue), `remove_agent`;
  job `create_agent`.
- Critic: `owner` per problem; only the designer's problems count and are
  sent to it.
- `kdp agent list|show|run|create|remove`; `/api/agents`; the Agents view;
  the assistant's `agents` read and `run_agent` / `create_agent` proposals.

# Validation

93 tests pass; flake8 clean; the frontend builds. Real model: ADR 0019.

# Remaining

- Findings of a report are not tracked as open or done.
- The intention guardian is run on request, not at every gate.
- The experimenter writes a protocol; nothing records an actual run.
- Ingestion of Word, ODT and PDF into Markdown.
- The designer's reach (cover composition, callouts) is still the template's.

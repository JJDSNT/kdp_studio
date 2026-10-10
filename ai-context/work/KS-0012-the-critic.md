---
id: KS-0012
title: The critic, pictures to the model, themes revised and removed
type: work
status: done
owner: project
created_at: 2026-10-10
updated_at: 2026-10-10
---

# Done

`Model.ask(images=…)` in both adapters; `agents/critic.py` (`critique`,
`critiques`, `latest`, `as_instruction`; job `critique_theme`);
`designer.revise_theme`, `remove_theme`, `design.json`, `look` (one criticism,
then stop) and `rounds` (opt-in); `kdp theme … --critique / --revise / --remove
/ --no-critic`; the criticism and its buttons in the gallery; the assistant's
`critique_theme` and `revise_theme`.

# Validation

87 tests pass; flake8 clean; the frontend builds. Real models on `novela`:
ADR 0018.

# Remaining

- The designer's blocks do not reach the cover's composition, the print
  callouts and exercises, lists, running heads: the critic asks for changes
  there that nobody can make from the tool.
- The critic sees print pages only, not the ebook as rendered.
- A criticism costs about 90 s and a drawing about 2 min with the CLI model.

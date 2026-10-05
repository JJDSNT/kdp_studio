---
id: KS-0005
title: From an idea to chapters — research, plan, writer, chapters gained and lost
type: work
status: done
owner: project
created_at: 2026-10-04
updated_at: 2026-10-04
---

# Done

`kdp new`; `agents/researcher.py`, `agents/architect.py`, `agents/writer.py`;
`structure.add_section/add_part/remove_section`; commands `add_section`,
`remove_section`, `add_part`, `adopt_plan`, `write_intentions`; model adapters
with `web=True`; assistant proposals for the whole flow; Research and Plan
views, the chapter plan box and "Write this chapter"; synopsis/promise in the
format; re-entrant book lock.

# Validation

- 56 tests pass (a scripted flow from `kdp new` to an adopted written chapter;
  gaining and losing chapters); flake8 clean; the frontend builds.
- Real model, new book "Comida na Varanda": research 2m54s (10 sources, 12
  findings, 4 honest not-found), plan + adoption + chapter 1 in 3m00s.
- Found and fixed: a deadlock (nested flock), archiving before reading the
  old numbering, numbering written into planned titles.

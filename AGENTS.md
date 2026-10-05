# KDP Studio development

Before changing the book format, gates, builds, checks, agents or integrations,
read:

- `ai-context/README.md`, then `ai-context/project-status.md`
- `ai-context/roadmap.md`
- `docs/architecture/` (accepted decisions)
- `docs/book-format.md` and `docs/templates.md`
- `docs/origin/editorial-system-spec.pt-BR.md` — the specification this tool
  implements, written from the production of *A Era dos Agentes*

Every non-trivial change has a record in `ai-context/work/` (what, why, done,
remaining, decisions, validation), updated during the work. Keep
`ai-context/project-status.md` current. Everything in `ai-context/`, the code,
comments and repository documentation is in English; a book's content stays in
its language.

## Invariants

- A book lives outside this repository; its files are authoritative. Builds
  are disposable.
- KDP Studio never rewrites a file the author wrote. Decisions go to the
  book's `state.json` (and its git history).
- Every mutation goes through one command, whoever calls it.
- Gates are records. No path skips one; an agent never decides one.
- Fidelity is measured by code, never judged by a model.
- Checks report measured values; a check that could not run says so.
- The book format is language-neutral; labels are generated per language.
- Nothing is specific to one book. *A Era dos Agentes* is the first user, not
  a special case.
- Development context (`ai-context/`, this file) is never production context
  for the agents that work on a book.

## Validation

```bash
uv sync --all-extras
make ui                      # the control room and the Copilot Runtime (Node 20+)
uv run pytest
uv run flake8 src tests tools
uv run kdp build examples/sample-book && uv run kdp check examples/sample-book
```

Building print needs LuaLaTeX and Ghostscript (`uv run kdp doctor`). When a
change touches rendering or a template, rasterise the pages that change and
look at them: a log without errors has hidden a missing chapter label before.

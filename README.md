# KDP Studio

**An open production environment for books, from idea to Amazon KDP.**

KDP Studio is a workspace for producing a book with specialised AI agents and a
human who decides: research, writing, review, translation, typesetting, ebook,
cover, validation and the publishing package, around one manuscript that the
author owns.

## Install and run

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). Typesetting the
print edition needs LuaLaTeX and Ghostscript; `kdp doctor` says what is
missing on your machine and the exact line that installs it.

```bash
git clone https://github.com/JJDSNT/kdp_studio.git
cd kdp_studio
uv sync --extra build
uv run kdp doctor
```

Then build and check the sample book:

```bash
uv run kdp status examples/sample-book
uv run kdp build  examples/sample-book     # print interior (PDF) and ebook (EPUB)
uv run kdp check  examples/sample-book     # KDP requirements, measured
```

The sample fails one check on purpose: it has 17 pages and KDP prints from 24.
The check says so, with the measured value beside the requirement.

| Command | What it does |
|---|---|
| `kdp doctor` | what works here, and how to fix what does not |
| `kdp status <book>` | structure, words, editions and gates at a glance |
| `kdp templates` | the edition template catalogue |
| `kdp build <book>` | the print interior and the ebook, for every language |
| `kdp check <book>` | measured verdicts against KDP and EPUB requirements |
| `kdp gate open/approve/changes/reject` | human gates, recorded in the book |
| `kdp compare <before> <after>` | fidelity: did the words change? (Markdown or PDF) |

## Why this exists

KDP Studio is being built to finish a specific book: **A Era dos Agentes**, by
Jaime Dias, a 156-page introduction to agentic AI in Brazilian Portuguese, with
an English edition to come. Its specification
([docs/origin](docs/origin/editorial-system-spec.pt-BR.md)) was written from that
production, and its catalogues of failures are field observations, not
hypotheses.

That is the method. A capability is added when the book needs it, and the
concepts built first are the ones the book could not do without:

- **the author's intention as a first-class file**, because the book was once
  rewritten twice when its documents said what to cover but not what it was
  for;
- **human gates as records**, because an approval belongs to the version that
  was judged, and a later version does not inherit it;
- **fidelity checked by machines**, because "did anything change?" is not a
  question to ask a model: a reviser that silently "fixes" a date must be
  caught even when the new date is right;
- **measured validation**, because a chapter label once vanished from the
  page without a single error in the log.

**The book is not in this repository.** A book is an external directory that
KDP Studio opens, reads, and writes decisions into. Nothing about the tool is
specific to one book; the sample in `examples/` is the only book-shaped
directory here.

## A book

```
my-book/
├── book.yaml               identity, languages, contents, editions
├── intentions.md           what the book is for, in the author's words
├── editorial/              the author's editorial documents
├── manuscript/
│   └── pt-BR/
│       ├── meta.yaml       title, part titles, labels, colophon
│       └── 01-*.md         one Markdown file per section
├── cover/  assets/  companion/  experiments/  archive/
├── state.json              runtime-owned: gates and decisions
└── builds/                 disposable: regenerated, never edited
```

The manuscript is Markdown with three book constructs: callouts
(`> [!concept] Title`), exercises (`::: exercise Title`) and prompts with a QR
code (`> [!prompt] EX-04-01`). Numbers and labels ("Chapter 11", "CONCEPT")
are generated, in each language. See [docs/book-format.md](docs/book-format.md).

KDP Studio never rewrites a file the author wrote. Its decisions go to
`state.json`, and when the book is a git repository each one is a commit with
its actor and reason.

## Edition templates

How a book looks is a template chosen by name in `book.yaml`, one for print and
one for the ebook. Templates form a catalogue; a book can add its own. The two
formats are not the same object: each template is built for the medium it lives
in. See [docs/templates.md](docs/templates.md).

| Template | Kind | |
|---|---|---|
| `nocturne` | print | night-blue part openings, cyan narrative accent, amber exercises; Pagella and Adventor |
| `nocturne` | ebook | the same identity rebuilt for readers: no dark grounds, labels as well as colours |

## Architecture

```
 CLI │ control room (planned) │ agents (planned)
                  │
        commands │ queries
                  │
            Book Core
 book │ sections │ editions │ gates │ decisions
                  │
              Adapters
 typesetting (LuaLaTeX) │ ebook │ checks │ models │ UI protocols
```

- The filesystem book is authoritative. Caches and builds are disposable.
- Every mutation goes through one command, whoever calls it: CLI, interface or
  agent.
- Production workflows and gates are records in the book, not orchestration
  state ([ADR 0002](docs/architecture/0002-gates-are-records-langgraph-runs-agents.md)).
- Agents run on **LangGraph**, behind a model adapter, and reach the interface
  through **CopilotKit** over AG-UI. An agent acts only through commands and
  never decides a gate.

Development context lives in [`ai-context/`](ai-context/README.md); accepted
decisions in [`docs/architecture/`](docs/architecture/).

## Status

The first milestone is delivered: the book format, the migration of *A Era dos
Agentes* with a fidelity audit, the print and ebook builds, measured KDP and
EPUB checks, human gates and the fidelity auditor. The control room, the agents
and the rest of the pipeline are on the [roadmap](ai-context/roadmap.md).

## License

The code license will be decided before distribution. A book's manuscript,
translations and assets belong to their authors and are never part of this
repository.

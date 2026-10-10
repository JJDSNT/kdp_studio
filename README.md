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
| `kdp style <book>` | the writing-vice catalogue, checked (with LanguageTool and Vale when configured) |
| `kdp continuity <book>` | passages that recur across sections, read at once |
| `kdp revise <book> <section>` | the voice reviser: a candidate version fixing register and form |
| `kdp move <book> <section> --before/--after/--into … -m why` | reorder, with the references the move breaks |
| `kdp new <dir> --title … --author … --idea …` | start a book from an idea |
| `kdp build <book> --edition cover` | the ebook cover and the print wrap, sized from the trim, the page count and the publisher's profile |
| `kdp art add/list <book>` | the book's pictures, each with how it was made |
| `kdp language add <book> <language>` | a second language: its `meta.yaml` translated and a stub per section |
| `kdp glossary <book> <language>` | the book's bilingual glossary; drafted by the translator when it has none |
| `kdp translate <book> <language> [section]` | the translator: one section, or every pending one, as candidate versions |
| `kdp translation <book>` | a translated language measured against its source, and what went stale |
| `kdp tools [install <name>]` | open tools used as resources: Vale, LanguageTool, EPUBCheck |
| `kdp serve <book or directory of books> [--assistant] [--library dir]` | the control room in the browser: the open book, the others it can open, the assistant |

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

## The control room

```bash
uv sync --all-extras && make ui          # once: Python extras, then the interface (Node 20+)
uv run kdp serve ~/books/my-book --assistant
```

A local interface over the same commands as the CLI:

- **the book**: structure, words, candidate versions, waiting gates;
- **a section**: the text as the ebook renders it, an editor that saves
  byte for byte (refused if the file changed since it was opened), its
  versions and its git history;
- **a version**: a candidate rewrite beside the current text, only the changed
  paragraphs, with the fidelity report — and Adopt or Reject, with a reason;
- **gates**, decided with their rationale; **editions**, built and measured;
  **pages**, the print interior rasterised to look at.

**The assistant** is a LangGraph agent served to the page through CopilotKit
(a CoAgent). It knows what you are looking at, reads the book when it needs
to, and can take your screen to a chapter or a version. When it wants to write
something into the book — a candidate version, a gate to open — it asks first,
in the chat; on your yes it acts as an agent, and the history says so. It never
decides a gate and never adopts a version. The model is your own Claude Code
login by default (`claude -p`, no key stored); `KDP_MODEL=claude-api` uses the
API instead.

## From an idea to a book

```bash
uv run kdp new ~/books/my-book --title "My Book" --author "Me" --idea "What it is for, in my words"
uv run kdp serve ~/books/my-book --assistant
```

Then, mostly in conversation with the assistant:

1. **Intention** — it interviews you and writes `intentions.md` with your words.
2. **Research** — the researcher searches the web, opens every source it
   cites, and records a dossier and a dated ledger of sources, including what
   it could *not* find.
3. **Plan** — the architect proposes parts and chapters, each with what it
   covers and what the reader can do after it; you adopt the plan and the
   chapters exist.
4. **Writing** — the writer drafts one chapter at a time, to its promise, as a
   candidate version.
5. **Review** — chapter by chapter, below; chapters are added, removed and
   moved whenever the book needs it
   ([ADR 0011](docs/architecture/0011-from-idea-to-chapters.md)).

## Working chapter by chapter

The loop the tool is built around: open a chapter, ask for changes in words,
read the candidate, adopt it or ask again, approve the chapter; move chapters
when the order is wrong. Mostly through the assistant:

- *"Revise a abertura deste capítulo: entre direto na cena."* — the reviser
  works in the background and leaves a candidate version; the comparison
  shows only what changed, rewritten paragraphs whole, with the fidelity
  report and the reviser's own account of what it removed or moved.
- *"Mova o capítulo 13 para antes do 12."* — after your yes, the order changes
  in `book.yaml` and the assistant lists every "capítulo N" in the prose that
  now points elsewhere.
- **Approve chapter** records the chapter as it reads now; the book shows
  which chapters are approved, not reviewed, or changed since approval.

The voice is chosen once — on a pilot chapter or on the voice guide — and
from then on every agent writes every chapter in it
([ADR 0010](docs/architecture/0010-chapter-loop-commanded-by-ai.md)).

## Style, continuity and the first agent

The writing-vice catalogue of the specification is a set of checks. Each
practice says whether a check enforces it; the report lists, by name, what
still depends on a reader. A book adds its own decisions in `style.yaml` —
*A Era dos Agentes* says "prática, nunca exercício", with the one approved
exception of chapter 3 — and the thesis phrases that must never become a
refrain.

Mature open tools do the rest, as resources: LanguageTool (with its Brazilian
Portuguese module), Vale, EPUBCheck — installed for the user only with
`kdp tools install` ([ADR 0008](docs/architecture/0008-open-tools-as-resources.md)).

The **voice reviser** is the first production agent. It reads a section, its
findings and the book's voice guide, and answers with exact edits that KDP
Studio applies itself — so nothing outside them can change — as a candidate
version the author compares and adopts or not
([ADR 0009](docs/architecture/0009-agents-answer-with-edits.md)). It runs as a
background job; the assistant can start it, after asking.

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
 CLI │ control room │ assistant (LangGraph, via CopilotKit)
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

Two milestones are delivered. The first: the book format, the migration of *A
Era dos Agentes* with a fidelity audit, the print and ebook builds, measured
KDP and EPUB checks, human gates and the fidelity auditor. The second: the
control room, text versions and byte-for-byte editing, and the editorial
assistant as a CopilotKit CoAgent. Since then: style checks and the voice
reviser, the chapter loop, the path from an idea to written chapters, and a
second language (the translator, the glossary, a translation measured against
its source), and the cover (words set by code over art without lettering,
sized per publisher). The companion and the rest of the pipeline are on the
[roadmap](ai-context/roadmap.md).

## License

The code license will be decided before distribution. A book's manuscript,
translations and assets belong to their authors and are never part of this
repository.

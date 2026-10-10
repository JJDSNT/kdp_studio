# ADR 0014: A library, and one open book

Status: accepted (2026-10-10). Amends ADR 0007, which served exactly one book.

## Context

An author has more than one book. `kdp serve <book>` could show only the one
it was started on; seeing another meant stopping the runtime. Books still
live outside this repository, each in its own directory (ADR 0001).

## Decision

- The runtime has a **library** — a directory whose sub-directories with a
  `book.yaml` are books (by default, the directory beside the book it was
  started on; `--library`, or `kdp serve <directory of books>`) — and **one
  open book**. `GET /api/library` lists them; `POST /api/open` opens another.
- Opening a book changes no book, so it is not a command and leaves no
  record. Every query and command still acts on the open book; the assistant
  shares the runtime's Studio, so it follows; a conversation belongs to the
  book it was held in.
- A job already running goes on with the book it was started on. Jobs are
  reconciled once per book and runtime, so coming back to a book does not
  mark its running job interrupted.
- One open book per runtime, not one per browser tab: this is one person's
  local tool. Two books side by side are two runtimes on two ports.

## Also here

The control room gained two views that only read: **Templates** (the edition
template catalogue and the publisher profiles, with what the open book uses)
and **Reader** (the built EPUB's own files, served out of the archive in
reading order, at a phone's, an e-reader's or a tablet's width; the e-reader
is shown in grey). The reader does not replace a device: a real reader picks
the font and may drop colours.

# ADR 0015: Art providers — planned, shown, then sent; the picture enters as a record

Status: accepted (2026-10-10). Completes ADR 0013.

## Context

Art had to be made elsewhere and registered by hand. The author's pictures
are made on RunPod serverless endpoints (ComfyUI; Qwen Image Edit), as in
Cine Toaster. Generation is slow, paid, and runs on someone else's machine;
and the picture the book has today carries lettering a model drew.

## Decision

- **A provider is an adapter** (`providers/`), narrow on purpose: its id,
  whether it *generates* from words or *edits* a picture, the settings it
  still misses, an estimate, and `run`. Two exist: `comfyui` (the author's own
  workflow in API format, patched by node type) and `qwen-edit`.
- **Planned, shown, then sent.** `art.plan` fixes everything before anything
  leaves: the final prompt, the negative prompt, the size (the cover's
  proportion, or the source's), the seed, the estimate and, for a cover, the
  resolution that size gives on paper. The CLI sends only with `--yes`; the
  assistant asks with the price in the question.
- **"No lettering" is said to every model** and never trusted: a generated
  picture is recorded `lettering: unchecked`, and the cover check warns until
  a person has looked and written `none`.
- **Taking lettering out** of a picture the book has is an edit
  (`--from <id> --remove-lettering`): the result is another id, derived from
  the first; nothing is replaced.
- **Paid work is not sent twice**: the request is recorded with its digest
  before it is sent, and a different pending request is refused (Cine
  Toaster's state file). That state is operational, outside the book.
- **Settings never live in a book.** Keys and endpoint ids come from the
  environment or `$XDG_CONFIG_HOME/kdp-studio/providers.env`, and are never
  printed; `kdp art providers` and `kdp doctor` name what is missing.
- The picture enters the book through the `add_art` command (so does `kdp art
  add`), with prompt, model, provider, seed, source, seconds and cost.

## Consequences

- A model makes pictures of about 1,500 px on the long side: roughly 167 dpi
  on a 6 × 9 cover. The plan and the cover check say so; enlarging is a
  provider yet to be written.
- KDP Studio creates no endpoint and holds no workflow of its own: the
  infrastructure and the graph are the author's.

## Validation

Scripted endpoints only: the patched graph, the record written, lettering
repainted out as a derived picture, a second request refused while one is
pending. **No real job was sent**: no endpoint is configured on this machine,
and sending is paid work the author starts.

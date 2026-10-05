# ADR 0004: Edition templates are a catalogue behind a semantic contract

Status: accepted (2026-10-04).

## Decision

Renderers emit semantic markup ("concept callout", "prompt with QR"); a
template decides how it looks, one per medium. Templates are directories with
a `template.yaml`, listed by `kdp templates`; built-in ones ship with KDP
Studio, and a book can add or override one. The contract is documented in
docs/templates.md and is the only thing a template implements.

Print and ebook templates are separate objects, each good in its medium.
A print template declares the trims it was laid out for; any other trim is
refused rather than guessed.

The first template, `nocturne`, is the design of *A Era dos Agentes*, ported
from its `estilo.tex` with the fixes it had learned (the vanishing chapter
label, the QR module size, bleed only on the outer edges).

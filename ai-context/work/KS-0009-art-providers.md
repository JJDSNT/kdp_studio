---
id: KS-0009
title: Art providers — ComfyUI and Qwen Image Edit on RunPod, planned before sent
type: work
status: done
owner: project
created_at: 2026-10-10
updated_at: 2026-10-10
---

# Done

- `providers/`: the `ArtProvider` protocol, settings from the environment or
  `providers.env`, `runpod.py` (submit, poll, a state file against sending
  twice), `comfyui.py`, `qwen_edit.py`.
- `art.plan` / `art.generate`, the `generate_art` job kind, the `add_art`
  command (the CLI's `art add` now goes through it), `lettering: unchecked`.
- `kdp art generate` (plan shown; `--yes` sends), `kdp art providers`;
  optional lines in `kdp doctor`; the assistant's `generate_art` proposal,
  with the estimate in its question.

# Validation

79 tests pass with scripted endpoints; flake8 clean. Not run against a real
endpoint: none is configured here and the work is paid (ADR 0015).

# Remaining

- A first real run by the author: `providers.env`, a ComfyUI workflow in API
  format for the models on their endpoint, then `kdp art generate … --yes`.
- An enlarging provider, to reach 300 dpi on paper.
- An Art view in the control room (today: `kdp art list`, and the cover in
  Editions); detecting lettering with OCR instead of a person's look.

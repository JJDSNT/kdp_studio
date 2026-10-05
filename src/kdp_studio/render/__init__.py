"""Rendering the manuscript into an edition's source.

Both renderers walk the same tree and emit *semantic* markup: they say "this
is a concept callout" or "this is a prompt with a QR code", never what it
looks like. The look belongs to the edition template (docs/templates.md), which
is what lets a book change its whole design by changing one name in book.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
         (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def roman(number: int) -> str:
    out = []
    for value, letters in ROMAN:
        while number >= value:
            out.append(letters)
            number -= value
    return "".join(out)


@dataclass
class RenderContext:
    language: str
    labels: dict
    #: The public address of an exercise's prompt page, or "" if the book has none.
    prompt_url: Callable[[str], str] = lambda exercise_id: ""
    #: Where the QR code image for an exercise is, relative to the edition source.
    qr_path: Callable[[str, str], str] = lambda exercise_id, url: ""
    #: Exercise ids seen while rendering, for reports and the companion export.
    exercises: list[str] = field(default_factory=list)

    def label(self, key: str) -> str:
        return str(self.labels.get(key, key))

    def callout_label(self, kind: str) -> str:
        return str((self.labels.get("callouts") or {}).get(kind, kind))

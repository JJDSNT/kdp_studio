"""Continuity across the whole book, read at once (docs/origin, §5.7).

A repetition between chapter 4 and chapter 17 only shows to someone who read
both. This is the deterministic half of the continuity reviser: it finds
passages that recur in *different* sections -- the same run of words, after
light normalisation -- and how far apart they are. Whether a repetition is a
deliberate callback or a seam is the author's (or an agent's) judgement; the
map is what makes it possible to judge.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .book import Book
from .style import units

#: A shared run shorter than this is ordinary language.
MIN_WORDS = 7


@dataclass
class Occurrence:
    section: str
    number: int
    excerpt: str


def _words(text: str) -> list[tuple[str, int, int]]:
    """Normalised words with their spans in the original text."""

    out = []
    for match in re.finditer(r"\w+", text):
        word = unicodedata.normalize("NFKD", match.group(0).lower())
        out.append(("".join(c for c in word if not unicodedata.combining(c)), match.start(), match.end()))
    return out


def repetitions(book: Book, language: str, min_words: int = MIN_WORDS) -> list[dict[str, Any]]:
    sections = book.sections(language)
    index: dict[tuple[str, ...], list[tuple[int, str, int, int]]] = {}
    texts: list[list[str]] = []
    for position, section in enumerate(sections):
        paragraphs = [u.text for u in units(section.body)]
        texts.append(paragraphs)
        for p_index, paragraph in enumerate(paragraphs):
            words = _words(paragraph)
            for i in range(len(words) - min_words + 1):
                key = tuple(w for w, _, _ in words[i:i + min_words])
                index.setdefault(key, []).append((position, section.id, p_index, words[i][1]))

    # Shingles that occur in more than one section, merged into passages.
    shared: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    for key, places in index.items():
        sections_seen = {p[0] for p in places}
        if len(sections_seen) < 2:
            continue
        first = places[0]
        for other in places[1:]:
            if other[0] == first[0]:
                continue
            shared.setdefault((first[0], other[0]), []).append((first[2], other[2], first[3]))

    found = []
    seen: set[tuple[int, int, int, int]] = set()
    for (a, b), hits in shared.items():
        for p_a, p_b, _ in hits:
            if (a, p_a, b, p_b) in seen:
                continue
            seen.add((a, p_a, b, p_b))
            passage = _longest_common(texts[a][p_a], texts[b][p_b])
            if len(passage.split()) < min_words:
                continue
            sa, sb = sections[a], sections[b]
            found.append({
                "passage": passage,
                "words": len(passage.split()),
                "distance": abs(b - a),
                "occurrences": [
                    {"section": sa.id, "number": sa.number, "title": sa.title, "paragraph": texts[a][p_a][:240]},
                    {"section": sb.id, "number": sb.number, "title": sb.title, "paragraph": texts[b][p_b][:240]},
                ],
            })
    return _grouped(found)


def _grouped(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per recurring passage, with every section it appears in.

    A passage repeated in ten sections is one finding (often a deliberate
    template line), not forty-five pairs.
    """

    groups: dict[str, dict[str, Any]] = {}
    for pair in sorted(pairs, key=lambda r: -r["words"]):
        key = " ".join(w for w, _, _ in _words(pair["passage"]))
        # A shorter passage contained in a longer one already found joins it.
        home = next((k for k in groups if key in k), key)
        group = groups.setdefault(home, {"passage": pair["passage"], "words": pair["words"], "occurrences": []})
        for occurrence in pair["occurrences"]:
            if all(o["section"] != occurrence["section"] for o in group["occurrences"]):
                group["occurrences"].append(occurrence)
    out = []
    for group in groups.values():
        numbers = [o["number"] for o in group["occurrences"] if o["number"]]
        group["occurrences"].sort(key=lambda o: o["number"])
        group["sections"] = len(group["occurrences"])
        group["span"] = (max(numbers) - min(numbers)) if len(numbers) > 1 else 0
        out.append(group)
    out.sort(key=lambda g: (-g["sections"] * g["words"], -g["span"]))
    return out


def _longest_common(a: str, b: str) -> str:
    """The longest run of words two paragraphs share, in a's wording."""

    wa, wb = _words(a), _words(b)
    keys_b = [w for w, _, _ in wb]
    best = (0, 0, 0)
    positions: dict[str, list[int]] = {}
    for j, word in enumerate(keys_b):
        positions.setdefault(word, []).append(j)
    for i, (word, _, _) in enumerate(wa):
        for j in positions.get(word, []):
            length = 0
            while i + length < len(wa) and j + length < len(wb) and wa[i + length][0] == wb[j + length][0]:
                length += 1
            if length > best[0]:
                best = (length, i, j)
    length, i, _ = best
    if not length:
        return ""
    return a[wa[i][1]:wa[i + length - 1][2]]

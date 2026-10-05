"""Reordering the book: moving a section or a part, and what the move breaks.

The order lives in `book.yaml` under `contents`, which the author owns. A move
rewrites that block only -- every other line of the file, comments included,
stays as it was -- and is committed with its reason. Chapter numbers are
generated, so they follow the new order by themselves; what does not follow is
prose that names a chapter by number ("como vimos no capítulo 9"). The move
reports each such reference whose target changed, so it can be fixed in the
same breath.
"""

from __future__ import annotations

import copy
import re
from typing import Any

import yaml

from .book import BOOK_FILENAME, Book, load_book
from .errors import NotFoundError, ValidationError
from .history import commit
from .state import Actor, book_lock
from .style import section_line, units


def _flatten(contents: list[Any]) -> list[str]:
    out = []
    for item in contents:
        out.extend(item.get("sections") or [] if isinstance(item, dict) else [item])
    return out


def _remove_section(contents: list[Any], section: str) -> None:
    for item in contents:
        if isinstance(item, dict) and section in (item.get("sections") or []):
            item["sections"].remove(section)
            return
        if item == section:
            contents.remove(item)
            return
    raise NotFoundError(f"No section {section!r} in the contents")


def _locate(contents: list[Any], section: str) -> tuple[list[Any], int]:
    """The list holding the section, and its index there."""

    for item in contents:
        if isinstance(item, dict) and section in (item.get("sections") or []):
            return item["sections"], item["sections"].index(section)
    if section in contents:
        return contents, contents.index(section)
    raise NotFoundError(f"No section {section!r} in the contents")


def _part_index(contents: list[Any], part: str) -> int:
    for index, item in enumerate(contents):
        if isinstance(item, dict) and str(item.get("part")) == str(part):
            return index
    raise NotFoundError(f"No part {part!r} in the contents")


def moved(book: Book, *, section: str = "", part: str = "", before: str = "", after: str = "",
          into: str = "") -> list[Any]:
    """The contents after one move, without writing anything.

    Move a `section` `before`/`after` another section, or to the end of the
    part `into`; or move a `part` `before`/`after` another part.
    """

    contents = copy.deepcopy(book.manifest["contents"])
    if bool(section) == bool(part):
        raise ValidationError("Move either a section or a part")
    if sum(bool(x) for x in (before, after, into)) != 1:
        raise ValidationError("Say where: before, after, or into (a part)")
    if part:
        if into:
            raise ValidationError("A part moves before or after another part")
        item = contents.pop(_part_index(contents, part))
        anchor = _part_index(contents, before or after)
        contents.insert(anchor if before else anchor + 1, item)
        return contents
    if section in (before, after):
        raise ValidationError("A section cannot move relative to itself")
    _remove_section(contents, section)
    if into:
        target = contents[_part_index(contents, into)]
        target.setdefault("sections", []).append(section)
    else:
        holder, index = _locate(contents, before or after)
        holder.insert(index if before else index + 1, section)
    return contents


def _numbers(book: Book, language: str) -> dict[str, int]:
    return {s.id: s.number for s in book.sections(language) if s.number}


def impact(before: Book, after: Book, language: str) -> dict[str, Any]:
    from .labels import labels

    chapter = str(labels(language, after.meta(language).get("labels")).get("chapter", "chapter")).lower()
    old, new = _numbers(before, language), _numbers(after, language)
    renumbered = {s: {"from": old[s], "to": new[s]} for s in new if s in old and old[s] != new[s]}
    by_old = {number: section for section, number in old.items()}
    references = []
    for section in after.sections(language):
        for unit in units(section.body):
            for match in re.finditer(r"\bcap[ií]tulos? (\d+)\b|\bchapters? (\d+)\b", unit.text, re.IGNORECASE):
                number = int(match.group(1) or match.group(2))
                target = by_old.get(number)
                if target and new.get(target) != number:
                    references.append({"section": section.id, "line": section_line(section, unit),
                                       "says": match.group(0), "meant": target,
                                       "now": f"{chapter} {new.get(target)}" if new.get(target) else "(unnumbered)"})
    return {"renumbered": renumbered, "references": references}


def write_contents(book: Book, contents: list[Any], *, actor: Actor, reason: str) -> dict[str, Any]:
    """Replace the contents block of book.yaml, keep every other line, commit."""

    if not reason.strip():
        raise ValidationError("A change of order says why")
    path = book.root / BOOK_FILENAME
    with book_lock(book.root):
        text = path.read_text("utf-8")
        lines = text.splitlines(keepends=True)
        start = next((i for i, line in enumerate(lines) if line.startswith("contents:")), None)
        if start is None:
            raise ValidationError("book.yaml has no top-level contents block")
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i].strip() and not lines[i].startswith((" ", "-", "#"))), len(lines))
        block = yaml.safe_dump({"contents": contents}, allow_unicode=True, sort_keys=False, width=100)
        path.write_text("".join(lines[:start]) + block + "".join(lines[end:]), encoding="utf-8")
        try:
            after = load_book(book.root)
            after.contents(book.source_language)
        except Exception:
            path.write_text(text, encoding="utf-8")
            raise
        commit(book.root, [path], f"Reorder the book: {reason}", actor)
    return {lang: impact(book, after, lang) for lang in after.languages}


def move(book: Book, *, actor: Actor, reason: str, **where: str) -> dict[str, Any]:
    contents = moved(book, **where)
    result = write_contents(book, contents, actor=actor, reason=reason)
    return {"contents": contents, "impact": result}

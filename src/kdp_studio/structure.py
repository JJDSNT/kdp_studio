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


def impact(old: dict[str, int], after: Book, language: str) -> dict[str, Any]:
    """What changed between the numbering `old` and the book `after`."""

    from .labels import labels

    chapter = str(labels(language, after.meta(language).get("labels")).get("chapter", "chapter")).lower()
    new = _numbers(after, language)
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


def write_contents(book: Book, contents: list[Any], *, actor: Actor, reason: str,
                   also: tuple = (), prepare=None) -> dict[str, Any]:
    """Replace the contents block of book.yaml, keep every other line, commit.

    `prepare`, when given, runs after the old numbering is read and before the
    new contents are written (moving files out, say), and returns more paths
    to commit.
    """

    if not reason.strip():
        raise ValidationError("A change of order says why")
    path = book.root / BOOK_FILENAME
    with book_lock(book.root):
        old = {language: _numbers(book, language) for language in book.languages}
        if prepare is not None:
            also = (*also, *prepare())
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
            for language in after.languages:
                after.contents(language)
        except Exception:
            path.write_text(text, encoding="utf-8")
            raise
        commit(book.root, [path, *also], f"Structure: {reason}", actor)
    return {lang: impact(old.get(lang, {}), after, lang) for lang in after.languages}


def move(book: Book, *, actor: Actor, reason: str, **where: str) -> dict[str, Any]:
    contents = moved(book, **where)
    result = write_contents(book, contents, actor=actor, reason=reason)
    return {"contents": contents, "impact": result}


def slug(title: str) -> str:
    import unicodedata

    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")[:60] or "section"


def _stub(title: str, kind: str, synopsis: str, promise: str, research: list[str] | None = None) -> str:
    front: dict[str, Any] = {"title": title}
    if kind != "chapter":
        front["kind"] = kind
    if synopsis:
        front["synopsis"] = synopsis
    if promise:
        front["promise"] = promise
    if research:
        front["research"] = list(research)
    return "---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=100).strip() + "\n---\n"


def add_section(book: Book, *, title: str, actor: Actor, reason: str, synopsis: str = "", promise: str = "",
                kind: str = "chapter", before: str = "", after: str = "", into: str = "") -> dict[str, Any]:
    """A new section, as a stub the writer fills: frontmatter with its plan, no body yet."""

    if not title.strip():
        raise ValidationError("A new section needs a title")
    section_id = slug(title)
    taken = set(_flatten(book.manifest["contents"]))
    base, n = section_id, 2
    while section_id in taken or (book.manuscript_dir(book.source_language) / f"{section_id}.md").exists():
        section_id, n = f"{base}-{n}", n + 1
    contents = copy.deepcopy(book.manifest["contents"])
    if before or after:
        holder, index = _locate(contents, before or after)
        holder.insert(index if before else index + 1, section_id)
    elif into:
        contents[_part_index(contents, into)].setdefault("sections", []).append(section_id)
    else:
        contents.append(section_id)
    # Every language gets the stub: a translated language shows it as untranslated.
    paths = [book.manuscript_dir(language) / f"{section_id}.md" for language in book.languages]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_stub(title.strip(), kind, synopsis.strip(), promise.strip()), encoding="utf-8")
    try:
        impact_by_language = write_contents(book, contents, actor=actor, reason=f"add “{title.strip()}”: {reason}",
                                            also=tuple(paths))
    except Exception:
        for path in paths:
            path.unlink(missing_ok=True)
        raise
    return {"section": section_id, "impact": impact_by_language}


def add_part(book: Book, *, part: str, title: str, actor: Actor, reason: str, kind: str = "part",
             before: str = "", after: str = "") -> dict[str, Any]:
    """A new part (its title goes to every language's meta.yaml)."""

    contents = copy.deepcopy(book.manifest["contents"])
    if any(isinstance(i, dict) and str(i.get("part")) == str(part) for i in contents):
        raise ValidationError(f"Part {part!r} already exists")
    item: dict[str, Any] = {"part": int(part) if str(part).isdigit() else part, "sections": []}
    if kind != "part":
        item["kind"] = kind
    anchor = before or after
    index = (_part_index(contents, anchor) + (0 if before else 1)) if anchor else len(contents)
    contents.insert(index, item)
    # Every language needs the title to be read at all; the others carry the
    # source's until it is translated (the translation report says so).
    meta_paths = []
    for language in book.languages:
        meta_path = book.manuscript_dir(language) / "meta.yaml"
        meta = yaml.safe_load(meta_path.read_text("utf-8")) if meta_path.is_file() else {}
        meta = meta or {}
        meta.setdefault("parts", {})[item["part"]] = title
        meta_path.write_text(yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")
        meta_paths.append(meta_path)
    write_contents(book, contents, actor=actor, reason=f"add part “{title}”: {reason}", also=tuple(meta_paths))
    return {"part": item["part"]}


def remove_section(book: Book, *, section: str, actor: Actor, reason: str) -> dict[str, Any]:
    """Out of the book, not deleted: every language's file goes to archive/removed/."""

    from .state import now

    contents = copy.deepcopy(book.manifest["contents"])
    _remove_section(contents, section)
    stamp = now()[:10]
    moved_files: list = []

    def archive() -> list:
        for language in book.languages:
            source = book.manuscript_dir(language) / f"{section}.md"
            if source.is_file():
                target = book.root / "archive" / "removed" / language / f"{stamp}-{section}.md"
                target.parent.mkdir(parents=True, exist_ok=True)
                source.rename(target)
                moved_files.extend([source, target])
        return moved_files

    impact_by_language = write_contents(book, contents, actor=actor, reason=f"remove {section}: {reason}",
                                        prepare=archive)
    return {"section": section, "archived": [str(p.relative_to(book.root)) for p in moved_files[1::2]],
            "impact": impact_by_language}

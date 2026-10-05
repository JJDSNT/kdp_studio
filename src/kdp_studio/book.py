"""Reading a book from disk (docs/book-format.md).

A book is a directory the author owns. KDP Studio reads it where it lies and
never keeps a second copy: `book.yaml` declares identity, structure and
editions; `manuscript/<language>/` holds one Markdown file per section; and
`manuscript/<language>/meta.yaml` holds what changes with the language (title,
part titles, labels, sales copy).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import BookFormatError, NotFoundError

BOOK_FILENAME = "book.yaml"
SCHEMA_VERSION = 1
SECTION_KINDS = {"front", "chapter", "back"}
PART_KINDS = {"part", "epilogue", "appendix"}

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.S)


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text
    data = yaml.safe_load(match.group(1)) or {}
    if not isinstance(data, dict):
        raise BookFormatError("Section frontmatter must be a mapping")
    return data, text[match.end():]


@dataclass(frozen=True)
class Section:
    id: str
    language: str
    path: Path
    kind: str
    title: str
    toc_title: str
    body: str
    #: Chapter number across the whole book, or 0 when unnumbered.
    number: int = 0

    @property
    def words(self) -> int:
        text = re.sub(r"<!--.*?-->", "", self.body, flags=re.S)
        return len(re.findall(r"\w+", text))


@dataclass(frozen=True)
class Part:
    id: str
    kind: str
    title: str
    #: Roman-numbered parts count 1, 2, 3...; unnumbered parts are 0.
    number: int
    sections: tuple[Section, ...]


#: One entry of the reading order: a section on its own, or a part.
Entry = Section | Part


@dataclass
class Book:
    root: Path
    manifest: dict[str, Any]
    _meta: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return str(self.manifest["id"])

    @property
    def author(self) -> str:
        return str(self.manifest.get("author", ""))

    @property
    def source_language(self) -> str:
        return str(self.manifest["source_language"])

    @property
    def languages(self) -> list[str]:
        return list(self.manifest.get("languages") or [self.source_language])

    @property
    def editions(self) -> dict[str, dict[str, Any]]:
        return dict(self.manifest.get("editions") or {})

    def manuscript_dir(self, language: str) -> Path:
        return self.root / "manuscript" / language

    def meta(self, language: str) -> dict[str, Any]:
        if language not in self._meta:
            path = self.manuscript_dir(language) / "meta.yaml"
            if not path.is_file():
                raise BookFormatError(f"Missing {path.relative_to(self.root)}", language=language)
            data = yaml.safe_load(path.read_text("utf-8")) or {}
            if not isinstance(data, dict):
                raise BookFormatError(f"{path.relative_to(self.root)} must be a mapping")
            self._meta[language] = data
        return self._meta[language]

    def title(self, language: str) -> str:
        return str(self.meta(language).get("title", self.id))

    def _check_language(self, language: str) -> None:
        if language not in self.languages:
            raise NotFoundError(f"The book has no language {language!r}", languages=self.languages)

    def _section(self, section_id: str, language: str, number: int) -> Section:
        path = self.manuscript_dir(language) / f"{section_id}.md"
        if not path.is_file():
            raise BookFormatError(
                f"Section {section_id!r} is in the contents but {path.relative_to(self.root)} is missing",
                section=section_id,
                language=language,
            )
        front, body = split_frontmatter(path.read_text("utf-8"))
        kind = str(front.get("kind", "chapter"))
        if kind not in SECTION_KINDS:
            raise BookFormatError(f"{path.name}: unknown kind {kind!r}", allowed=sorted(SECTION_KINDS))
        title = str(front.get("title") or "").strip()
        if not title:
            raise BookFormatError(f"{path.name}: the frontmatter needs a title")
        return Section(
            id=section_id,
            language=language,
            path=path,
            kind=kind,
            title=title,
            toc_title=str(front.get("toc_title") or title),
            body=body,
            number=number if kind == "chapter" else 0,
        )

    def contents(self, language: str) -> list[Entry]:
        """The reading order, with chapters and parts numbered."""

        self._check_language(language)
        part_titles = self.meta(language).get("parts") or {}
        entries: list[Entry] = []
        chapter = part_number = 0

        def section(section_id: str) -> Section:
            nonlocal chapter
            preview = self._section(section_id, language, 0)
            if preview.kind == "chapter":
                chapter += 1
                return self._section(section_id, language, chapter)
            return preview

        for item in self.manifest.get("contents") or []:
            if isinstance(item, str):
                entries.append(section(item))
                continue
            if not isinstance(item, dict) or "part" not in item:
                raise BookFormatError(f"Contents entry not understood: {item!r}")
            part_id = str(item["part"])
            kind = str(item.get("kind", "part"))
            if kind not in PART_KINDS:
                raise BookFormatError(f"Part {part_id!r}: unknown kind {kind!r}", allowed=sorted(PART_KINDS))
            if kind == "part":
                part_number += 1
            title = part_titles.get(part_id, part_titles.get(_int_or_none(part_id)))
            if not title:
                raise BookFormatError(
                    f"Part {part_id!r} has no title in manuscript/{language}/meta.yaml",
                    part=part_id,
                    language=language,
                )
            sections = tuple(section(str(s)) for s in item.get("sections") or [])
            entries.append(Part(part_id, kind, str(title), part_number if kind == "part" else 0, sections))
        return entries

    def sections(self, language: str) -> list[Section]:
        flat: list[Section] = []
        for entry in self.contents(language):
            flat.extend(entry.sections if isinstance(entry, Part) else [entry])
        return flat


def _int_or_none(value: str) -> int | None:
    return int(value) if value.isdigit() else None


def find_book_root(path: Path) -> Path:
    path = path.resolve()
    for candidate in (path, *path.parents):
        if (candidate / BOOK_FILENAME).is_file():
            return candidate
    raise NotFoundError(f"No {BOOK_FILENAME} in {path} or above it")


def load_book(path: Path | str) -> Book:
    root = find_book_root(Path(path))
    manifest = yaml.safe_load((root / BOOK_FILENAME).read_text("utf-8")) or {}
    if not isinstance(manifest, dict):
        raise BookFormatError(f"{BOOK_FILENAME} must be a mapping")
    schema = manifest.get("schema")
    if schema != SCHEMA_VERSION:
        raise BookFormatError(
            f"{BOOK_FILENAME} declares schema {schema!r}; this KDP Studio reads schema {SCHEMA_VERSION}"
        )
    for key in ("id", "source_language", "contents"):
        if not manifest.get(key):
            raise BookFormatError(f"{BOOK_FILENAME} needs {key!r}")
    return Book(root=root, manifest=manifest)

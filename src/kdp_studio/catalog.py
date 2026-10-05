"""The edition template catalogue (docs/templates.md).

A template is a directory with a ``template.yaml``. Built-in templates ship
with KDP Studio; a book may add its own, or override a built-in one, under
``<book>/templates/<kind>/<name>/``. The book chooses one per edition in
book.yaml, so changing the whole design of a book is changing one name.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from .errors import NotFoundError

KINDS = ("print", "ebook")


@dataclass(frozen=True)
class Template:
    name: str
    kind: str
    path: Path
    meta: dict[str, Any]
    source: str

    @property
    def title(self) -> str:
        return str(self.meta.get("title", self.name))

    @property
    def description(self) -> str:
        return " ".join(str(self.meta.get("description", "")).split())


def _builtin_root() -> Path:
    return Path(str(resources.files(__package__).joinpath("templates")))


def _scan(root: Path, source: str) -> list[Template]:
    found = []
    for kind in KINDS:
        base = root / kind
        if not base.is_dir():
            continue
        for directory in sorted(base.iterdir()):
            manifest = directory / "template.yaml"
            if manifest.is_file():
                meta = yaml.safe_load(manifest.read_text("utf-8")) or {}
                found.append(Template(directory.name, kind, directory, meta, source))
    return found


def catalog(book_root: Path | None = None) -> list[Template]:
    by_key = {(t.kind, t.name): t for t in _scan(_builtin_root(), "built-in")}
    if book_root is not None:
        by_key.update({(t.kind, t.name): t for t in _scan(book_root / "templates", "book")})
    return sorted(by_key.values(), key=lambda t: (t.kind, t.name))


def get(kind: str, name: str, book_root: Path | None = None) -> Template:
    for template in catalog(book_root):
        if template.kind == kind and template.name == name:
            return template
    names = [t.name for t in catalog(book_root) if t.kind == kind]
    raise NotFoundError(f"No {kind} template named {name!r}", available=names)

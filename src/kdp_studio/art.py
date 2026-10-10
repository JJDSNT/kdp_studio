"""Art: the pictures a book owns -- cover art, illustrations -- as records.

A picture lives in `<book>/art/<id>.<ext>` beside a record `<id>.yaml` that
says where it came from: what it is for, the prompt and the model when a
model made it, the seed, what it was derived from, and whether it carries
lettering. Nothing is replaced: another attempt is another id, so the book
keeps every picture it once used and can say how each was made (the pattern
of Cine Toaster's takes).

Lettering matters because image models misspell. A cover's words are set by
the cover template from `meta.yaml`; art declared `lettering: baked` is
reported by the cover check, because its words cannot be corrected or
translated.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from .book import Book
from .errors import NotFoundError, ToolUnavailableError, ValidationError
from .fidelity import digest
from .history import commit
from .state import Actor, book_lock, now

FOLDER = "art"
SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")
PURPOSES = ("cover", "illustration")
LETTERING = ("none", "baked")
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,60}")


def pixels(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image
    except ImportError as error:  # pragma: no cover - depends on the extra
        raise ToolUnavailableError("Pictures need the build extra: uv sync --extra build") from error
    with Image.open(path) as image:
        return image.size


def _picture(book: Book, art_id: str) -> Path | None:
    folder = book.root / FOLDER
    return next((folder / f"{art_id}{suffix}" for suffix in SUFFIXES if (folder / f"{art_id}{suffix}").is_file()),
                None)


def get(book: Book, art_id: str) -> dict[str, Any]:
    """A picture with its record; a picture the author dropped in by hand has an empty one."""

    path = _picture(book, art_id)
    if path is None:
        raise NotFoundError(f"No art {art_id!r} in {FOLDER}/", available=[a["id"] for a in records(book)])
    record_path = path.with_suffix(".yaml")
    record = (yaml.safe_load(record_path.read_text("utf-8")) or {}) if record_path.is_file() else {}
    width, height = pixels(path)
    current = digest(path.read_bytes())
    return {**record, "id": art_id, "path": str(path.relative_to(book.root)), "width": width, "height": height,
            "digest": current, "recorded": record_path.is_file(),
            # The picture was changed after its record was written: the record no longer describes it.
            "changed_since": bool(record.get("digest")) and record["digest"] != current}


def records(book: Book) -> list[dict[str, Any]]:
    folder = book.root / FOLDER
    if not folder.is_dir():
        return []
    ids = sorted({p.stem for p in folder.iterdir() if p.suffix.lower() in SUFFIXES})
    return [get(book, art_id) for art_id in ids]


def add(book: Book, source: Path, art_id: str, *, actor: Actor, purpose: str = "illustration", prompt: str = "",
        model: str = "", provider: str = "", seed: int | None = None, derived_from: str = "",
        lettering: str = "none", notes: str = "") -> dict[str, Any]:
    """Bring a picture into the book, with how it was made."""

    if not _ID.fullmatch(art_id):
        raise ValidationError(f"{art_id!r} is not an art id (lowercase letters, digits and hyphens)")
    if purpose not in PURPOSES:
        raise ValidationError(f"Unknown purpose {purpose!r}", allowed=list(PURPOSES))
    if lettering not in LETTERING:
        raise ValidationError(f"Unknown lettering {lettering!r}", allowed=list(LETTERING))
    source = Path(source).expanduser()
    if not source.is_file() or source.suffix.lower() not in SUFFIXES:
        raise ValidationError(f"{source} is not a picture ({', '.join(SUFFIXES)})")
    if _picture(book, art_id) is not None:
        raise ValidationError(f"Art {art_id!r} exists; nothing is replaced — give this picture another id")
    if derived_from and _picture(book, derived_from) is None:
        raise NotFoundError(f"No art {derived_from!r} to derive from")
    folder = book.root / FOLDER
    target = folder / f"{art_id}{source.suffix.lower()}"
    with book_lock(book.root):
        folder.mkdir(exist_ok=True)
        shutil.copyfile(source, target)
        width, height = pixels(target)
        record: dict[str, Any] = {"purpose": purpose, "lettering": lettering, "width": width, "height": height,
                                  "digest": digest(target.read_bytes()), "added_at": now(),
                                  "added_by": actor.public_dict()}
        made = {"prompt": prompt.strip(), "model": model, "provider": provider, "seed": seed,
                "derived_from": derived_from, "notes": notes.strip()}
        record.update({key: value for key, value in made.items() if value not in ("", None)})
        record_path = target.with_suffix(".yaml")
        record_path.write_text(yaml.safe_dump(record, allow_unicode=True, sort_keys=False, width=100),
                               encoding="utf-8")
        commit(book.root, [target, record_path], f"Art {art_id}: {purpose}"
               + (f", made with {model}" if model else ""), actor)
    return get(book, art_id)

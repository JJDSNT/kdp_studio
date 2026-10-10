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
from .jobs import Progress, kind, store_path
from .fidelity import digest
from .history import commit
from .state import Actor, book_lock, now

FOLDER = "art"
SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")
PURPOSES = ("cover", "illustration")
#: none: looked at, no words in it. baked: it carries words. unchecked: a model
#: was asked for none and nobody has looked yet.
LETTERING = ("none", "baked", "unchecked")
#: Said to every model that makes a picture for a book: the words are set by code.
NO_LETTERING = ("No text, no letters, no words, no numbers, no typography, no captions, no logos, no watermark "
                "and no signature anywhere in the image.")
NEGATIVE = "text, letters, words, numbers, typography, caption, title, logo, watermark, signature"
REMOVE_LETTERING = ("Remove every piece of text and lettering from the image and repaint what was behind it so "
                    "the picture continues naturally. ")
KEEP = ("Keep the exact composition, framing, colours, light and every other element unchanged; add nothing. "
        + NO_LETTERING)
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
        lettering: str = "none", notes: str = "", provenance: dict[str, Any] | None = None) -> dict[str, Any]:
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
        if provenance:
            record["provenance"] = provenance
        record_path = target.with_suffix(".yaml")
        record_path.write_text(yaml.safe_dump(record, allow_unicode=True, sort_keys=False, width=100),
                               encoding="utf-8")
        commit(book.root, [target, record_path], f"Art {art_id}: {purpose}"
               + (f", made with {model}" if model else ""), actor)
    return get(book, art_id)


# -------------------------------------------------------------- generating

def _rounded(width: float, height: float, longest: int) -> tuple[int, int]:
    """A size in multiples of 32 at this proportion, its longest side at most `longest`."""

    scale = longest / max(width, height)
    return max(32, round(width * scale / 32) * 32), max(32, round(height * scale / 32) * 32)


def _cover_shape(book: Book) -> tuple[float, float]:
    """The proportion cover art needs: the print front with its bleed, else the ebook front."""

    from .cover import print_trim, publisher

    rules = publisher(book)
    declared = print_trim(book)
    if declared:
        (trim_w, trim_h), _ = declared
        return trim_w + rules.bleed, trim_h + 2 * rules.bleed
    return float(rules.ebook_pixels[0]), float(rules.ebook_pixels[1])


def plan(book: Book, art_id: str, *, prompt: str = "", provider: str = "", purpose: str = "cover",
         derived_from: str = "", remove_lettering: bool = False, seed: int | None = None,
         size: tuple[int, int] | None = None) -> dict[str, Any]:
    """Everything that would be sent to a provider, and what it should cost. Nothing is sent."""

    import random

    from . import providers

    if not _ID.fullmatch(art_id):
        raise ValidationError(f"{art_id!r} is not an art id (lowercase letters, digits and hyphens)")
    if _picture(book, art_id) is not None:
        raise ValidationError(f"Art {art_id!r} exists; nothing is replaced — give this picture another id")
    if purpose not in PURPOSES:
        raise ValidationError(f"Unknown purpose {purpose!r}", allowed=list(PURPOSES))
    chosen = providers.get(provider or ("qwen-edit" if derived_from else "comfyui"))
    source = get(book, derived_from) if derived_from else None
    if chosen.mode == "edit" and source is None:
        raise ValidationError(f"{chosen.id} repaints a picture: say which with `derived_from`")
    if chosen.mode == "generate" and source is not None:
        raise ValidationError(f"{chosen.id} makes a picture from words; to repaint {derived_from} use an editing provider")
    if remove_lettering and source is None:
        raise ValidationError("Removing lettering needs the picture to remove it from (`derived_from`)")
    if not prompt.strip() and not remove_lettering:
        raise ValidationError("A picture needs a prompt: what it shows")
    if size is None:
        shape = (source["width"], source["height"]) if source else \
            _cover_shape(book) if purpose == "cover" else (4.0, 3.0)
        size = _rounded(shape[0], shape[1], chosen.max_side)
    words = " ".join(prompt.split())
    if chosen.mode == "edit":
        final = (REMOVE_LETTERING if remove_lettering else "") + (words + " " if words else "") + KEEP
    else:
        final = f"{words} {NO_LETTERING}"
    found: dict[str, Any] = {
        "id": art_id, "purpose": purpose, "provider": chosen.id, "model": chosen.model, "mode": chosen.mode,
        "request": words, "prompt": final, "negative": NEGATIVE, "width": size[0], "height": size[1],
        "seed": seed if seed is not None else random.randrange(2 ** 31), "derived_from": derived_from,
        "remove_lettering": remove_lettering, "estimate_usd": chosen.estimate_usd(), "missing": chosen.missing(),
    }
    if purpose == "cover" and book.editions.get("print"):
        # What this size gives on paper; the cover check will say the same of the picture itself.
        found["print_dpi"] = round(size[0] / _cover_shape(book)[0])
    return found


def generate(book: Book, planned: dict[str, Any], *, actor: Actor, provider=None,
             progress=lambda message: None) -> dict[str, Any]:
    """Send a planned request, and bring what comes back into the book with its record."""

    from . import providers
    from .commands import dispatch

    chosen = provider or providers.get(planned["provider"])
    if chosen.missing():
        raise providers.ProviderNotConfigured(f"{chosen.id} is not configured: " + ", ".join(chosen.missing())
                                              + f" (environment, or {providers.config_file()})")
    work = store_path(book).parent / "art"
    source = book.root / get(book, planned["derived_from"])["path"] if planned.get("derived_from") else None
    request = providers.ArtRequest(planned["prompt"], planned["negative"], planned["width"], planned["height"],
                                   planned["seed"], source)
    progress(f"Sent to {chosen.id}: {planned['width']} × {planned['height']} px, about ${planned['estimate_usd']}")
    result = chosen.run(request, work / f"{planned['id']}.png", work / f"{planned['id']}.job.json")
    progress(f"Received after {result.seconds:.0f} s: recording it in the book")
    found = dispatch(book, "add_art", {
        "file": str(result.path), "id": planned["id"], "purpose": planned["purpose"], "prompt": planned["prompt"],
        "model": result.model, "provider": result.provider, "seed": result.seed,
        "derived_from": planned.get("derived_from", ""),
        # Asked for none; a person has to look before it is declared so.
        "lettering": "unchecked",
        "provenance": {**result.provenance, "seconds": result.seconds, "cost_usd": result.cost_usd,
                       "request": planned.get("request", ""), "negative": planned["negative"]},
    }, actor)
    result.path.unlink(missing_ok=True)
    return {**found, "seconds": result.seconds, "cost_usd": result.cost_usd,
            "summary": f"art/{planned['id']} made by {result.model} in {result.seconds:.0f} s "
                       f"(${result.cost_usd:.3f}). Look at it: it was asked to carry no lettering."}


@kind("generate_art", "Art: a picture made or repainted by a provider, recorded in the book with how it was made")
def generate_art_job(book: Book, payload: dict[str, Any], actor: Actor, progress: Progress) -> dict[str, Any]:
    size = tuple(payload["size"]) if payload.get("size") else None
    planned = plan(book, payload["id"], prompt=payload.get("prompt", ""), provider=payload.get("provider", ""),
                   purpose=payload.get("purpose", "cover"), derived_from=payload.get("derived_from", ""),
                   remove_lettering=bool(payload.get("remove_lettering")), seed=payload.get("seed"), size=size)
    return generate(book, planned, actor=actor, progress=progress)

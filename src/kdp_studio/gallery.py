"""The gallery of themes: every design applied to the same specimen text.

A *theme* is a name the catalogue holds for more than one medium -- the print
interior, the ebook, the cover -- so that a book changes its whole look by
one word. To choose one a person has to see it, so each theme is built over
the same short book of lorem ipsum (`specimen/`) and shown as pictures: the
contents, a part opening, a chapter opening, callouts, an exercise with its
prompt, the cover, and the ebook itself.

The renders are a cache (`$XDG_CACHE_HOME/kdp-studio/gallery/`), keyed by the
theme's files, the specimen and the language of the labels: deleting it loses
nothing, and a template that changes is rendered again.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from importlib import resources
from pathlib import Path
from typing import Any

from . import catalog
from .book import BOOK_FILENAME, Book, load_book
from .errors import NotFoundError, ToolUnavailableError, ValidationError
from .history import commit
from .state import Actor, book_lock

KINDS = ("print", "ebook", "cover")
#: A page is shown for what it demonstrates; the specimen's own words find it.
ROLES = {"part": "ordorerum", "chapter": "deinitiisrerum", "callouts": "tresquaestiones", "exercise": "exercitiumbreve"}
SHOWN = ("part", "chapter", "callouts", "exercise")
RESOLUTION = 100


def _specimen() -> Path:
    return Path(str(resources.files(__package__).joinpath("specimen")))


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "kdp-studio" / "gallery"


def themes(book_root: Path | None = None) -> list[dict[str, Any]]:
    """Every theme of the catalogue, with the media it covers."""

    by_name: dict[str, dict[str, Any]] = {}
    for template in catalog.catalog(book_root):
        if template.kind not in KINDS:
            continue
        theme = by_name.setdefault(template.name, {"name": template.name, "title": template.title, "kinds": {},
                                                   "source": template.source})
        theme["kinds"][template.kind] = {"description": template.description, "source": template.source,
                                         "fonts": list(template.meta.get("fonts") or []),
                                         "colors": dict(template.meta.get("colors") or {}),
                                         "origin": str(template.meta.get("origin", ""))}
        if template.kind == "print":
            theme["title"] = template.title
    return sorted(by_name.values(), key=lambda t: t["name"])


def key(theme: str, language: str, book_root: Path | None = None) -> str:
    """What a render depends on: the theme's files, the specimen, the labels' language."""

    hasher = hashlib.sha256(f"5:{theme}:{language}".encode())
    folders = [_specimen()] + [catalog.get(kind, theme, book_root).path for kind in KINDS
                               if any(t.kind == kind and t.name == theme for t in catalog.catalog(book_root))]
    for folder in folders:
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            hasher.update(str(path.relative_to(folder)).encode() + b"\0" + path.read_bytes())
    return f"{theme}-{language}-{hasher.hexdigest()[:12]}"


def built(theme: str, language: str, book_root: Path | None = None) -> dict[str, Any] | None:
    path = cache_dir() / key(theme, language, book_root) / "gallery.json"
    return json.loads(path.read_text("utf-8")) if path.is_file() else None


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def build(theme: str, language: str, book_root: Path | None = None) -> dict[str, Any]:
    """Render the specimen in one theme: print pages, the cover, the ebook."""

    from .build import build_ebook, build_print
    from .cover import build_cover

    available = {t.kind for t in catalog.catalog(book_root) if t.name == theme and t.kind in KINDS}
    if not available:
        raise NotFoundError(f"No theme named {theme!r}", available=[t["name"] for t in themes(book_root)])
    name = key(theme, language, book_root)
    out = cache_dir() / name
    work = out.with_name(name + ".work")
    for folder in (out, work):
        if folder.exists():
            shutil.rmtree(folder)
    shutil.copytree(_specimen(), work)
    (work / "manuscript" / "text").rename(work / "manuscript" / language)
    if book_root is not None and (book_root / "templates").is_dir():
        shutil.copytree(book_root / "templates", work / "templates")  # the book's own themes
    manifest = (work / BOOK_FILENAME).read_text("utf-8").replace("source_language: text", f"source_language: {language}")
    manifest = manifest.replace("languages: [text]", f"languages: [{language}]")
    for kind in KINDS:
        manifest = (manifest.replace(f"  {kind}: {{template: nocturne", f"  {kind}: {{template: {theme}")
                    if kind in available else re.sub(rf"\n  {kind}: \{{[^\n]*", "", manifest))
    (work / BOOK_FILENAME).write_text(manifest, encoding="utf-8")
    book = load_book(work)
    report: dict[str, Any] = {"theme": theme, "language": language, "key": name, "pages": [], "cover": "",
                              "wrap": "", "ebook": []}
    if "print" in available:
        interior = build_print(book, language, bleed=False)
        if not shutil.which("gs"):
            raise ToolUnavailableError("Ghostscript is needed to show pages; `kdp doctor` says how")
        (work / "pages").mkdir()
        subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m", f"-r{RESOLUTION}",
                        "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4", f"-sOutputFile={work}/pages/p%03d.png",
                        str(interior.output)], check=True, capture_output=True)
        from pypdf import PdfReader

        texts = [_squash(page.extract_text() or "") for page in PdfReader(str(interior.output)).pages]
        # The contents name every title, so they are the first page that carries several of them;
        # a role is the first page after it that carries its own words.
        titles = ("ordorerum", "deinitiisrerum", "deusuetexercitatione")
        contents = next((i for i, text in enumerate(texts) if sum(t in text for t in titles) >= 2), -1)
        found = {"contents": contents}
        for role, marker in ROLES.items():
            found[role] = next((i for i in range(contents + 1, len(texts)) if marker in texts[i]), -1)
        roles = {index: role for role, index in found.items() if index >= 0}
        report["pages"] = [{"file": f"pages/p{i + 1:03d}.png", "role": roles.get(i, "")} for i in range(len(texts))]
    if "cover" in available:
        cover = build_cover(book, language)
        shutil.copyfile(work / cover.details["ebook"], work / "cover.jpg")
        report["cover"] = "cover.jpg"
        if cover.details["print"]:
            shutil.copyfile(work / "builds" / language / "cover" / "preview-print.png", work / "wrap.png")
            report["wrap"] = "wrap.png"
    if "ebook" in available:
        ebook = build_ebook(book, language)
        shutil.copyfile(ebook.output, work / "book.epub")
        import zipfile

        with zipfile.ZipFile(work / "book.epub") as archive:
            report["ebook"] = sorted(n.removeprefix("OEBPS/") for n in archive.namelist()
                                     if n.startswith("OEBPS/text-") or n.startswith("OEBPS/part-"))
    shutil.rmtree(work / "builds", ignore_errors=True)
    (work / "gallery.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    work.rename(out)
    return report


def file(name: str, relative: str) -> Path:
    """A picture of a render, by its key; nothing outside the cache is ever served."""

    folder = (cache_dir() / name).resolve()
    path = (folder / relative).resolve()
    if cache_dir().resolve() not in folder.parents or folder not in path.parents or not path.is_file():
        raise NotFoundError(f"No gallery file {relative!r}")
    return path


def epub_file(name: str, relative: str) -> tuple[bytes, str]:
    import mimetypes
    import zipfile

    with zipfile.ZipFile(file(name, "book.epub")) as archive:
        try:
            data = archive.read(f"OEBPS/{relative}")
        except KeyError:
            raise NotFoundError(f"The specimen ebook has no {relative!r}") from None
    kind = "application/xhtml+xml" if relative.endswith(".xhtml") else mimetypes.guess_type(relative)[0]
    return data, kind or "application/octet-stream"


def in_use(book: Book) -> dict[str, str]:
    return {kind: str(settings.get("template", "")) for kind, settings in book.editions.items()}


def apply_theme(book: Book, theme: str, *, actor: Actor, reason: str = "") -> dict[str, Any]:
    """The book takes a theme: each edition it declares, where the theme has that medium.

    Only the template names inside the `editions` block of book.yaml change;
    every other character of the file stays as the author wrote it.
    """

    available = {t.kind for t in catalog.catalog(book.root) if t.name == theme}
    if not available:
        raise NotFoundError(f"No theme named {theme!r}", available=[t["name"] for t in themes(book.root)])
    wanted = [kind for kind in book.editions if kind in available]
    if not wanted:
        raise ValidationError(f"Theme {theme!r} has none of the editions this book declares",
                              editions=sorted(book.editions), theme_has=sorted(available))
    if "print" in wanted:
        trims = catalog.get("print", theme, book.root).meta.get("trims") or {}
        trim = str(book.editions["print"].get("trim", next(iter(trims), "")))
        if trim not in trims:
            raise ValidationError(f"Theme {theme!r} has no print layout for trim {trim!r}", trims=sorted(trims))
    path = book.root / BOOK_FILENAME
    with book_lock(book.root):
        before = path.read_text("utf-8")
        lines = before.splitlines(keepends=True)
        start = next((i for i, line in enumerate(lines) if line.startswith("editions:")), None)
        if start is None:
            raise ValidationError(f"{BOOK_FILENAME} has no top-level editions block")
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i].strip() and not lines[i].startswith((" ", "-", "#"))), len(lines))
        current = ""
        for index in range(start + 1, end):
            head = re.match(r"^ {1,4}([\w-]+):", lines[index])
            if head and not lines[index].lstrip().startswith("template:"):
                current = head.group(1)
            if current in wanted:
                lines[index] = re.sub(r"(\btemplate:\s*)[\"']?[\w-]+[\"']?", rf"\g<1>{theme}", lines[index])
        path.write_text("".join(lines), encoding="utf-8")
        after = in_use(load_book(book.root))
        if any(after.get(kind) != theme for kind in wanted):
            path.write_text(before, encoding="utf-8")
            raise ValidationError(f"Could not set the template of {', '.join(wanted)} in {BOOK_FILENAME}; "
                                  "its editions block is written in a way this command does not read")
        changed = [kind for kind in wanted if in_use(book).get(kind) != theme]
        if changed:
            commit(book.root, [path], f"Design: theme {theme} for {', '.join(changed)}"
                   + (f" — {reason}" if reason else ""), actor)
    return {"theme": theme, "editions": wanted, "changed": changed,
            "left": sorted(kind for kind in book.editions if kind not in available)}

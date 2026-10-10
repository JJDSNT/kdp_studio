"""The control room's runtime: one book, its queries, and the command endpoint.

`kdp serve <book>` runs it on this machine only. The browser reads queries and
sends every change to `POST /api/commands`, as a person. The assistant, when
on, runs in this process and reaches the same commands as an agent; the
Copilot Runtime sidecar is proxied at `/api/copilotkit` so the page talks to a
single origin.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from . import catalog, gates, proofs, versions
from .book import Book, Part, load_book
from .build import build_dir
from .checks.run import last_report
from .commands import dispatch
from .errors import KdpStudioError, NotFoundError, ToolUnavailableError, ValidationError
from .labels import labels as load_labels
from .render import RenderContext
from .render.xhtml import XhtmlRenderer
from .state import Actor, read_state

try:  # the studio extra; FastAPI resolves annotations from module globals
    from fastapi import Request
except ImportError:  # pragma: no cover - reported by create_app
    Request = Any

WEB_ASSETS = Path(__file__).with_name("web_assets")
STATUS = {"validation_failed": 422, "book_format": 422, "not_found": 404, "revision_conflict": 409,
          "tool_unavailable": 503, "build_failed": 500}

#: Documents the author wrote that the room shows read-only.
DOCUMENTS = ("intentions.md", "editorial")


def person() -> Actor:
    name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
    return Actor(name or "author", "human")


class Studio:
    """Queries over the open book. Every call reloads it: the files are the truth.

    A runtime has one book open at a time and a *library*: the directory whose
    books it can open (the open book's neighbours, by default). Opening another
    is not a change to any book; jobs already running go on with theirs.
    """

    def __init__(self, root: Path, library: Path | None = None) -> None:
        self.root = load_book(root).root
        self.library = (Path(library).expanduser().resolve() if library else self.root.parent)
        self._reconciled: set[Path] = set()

    def books(self) -> list[dict[str, Any]]:
        """The books of the library, and the open one wherever it lives."""

        roots = {self.root}
        if self.library.is_dir():
            roots |= {p.parent.resolve() for p in self.library.glob("*/book.yaml")}
        found = []
        for root in sorted(roots, key=lambda p: p.name):
            entry: dict[str, Any] = {"path": str(root), "open": root == self.root}
            try:
                book = load_book(root)
                sections = book.sections(book.source_language)
                entry.update(id=book.id, title=book.title(book.source_language), author=book.author,
                             languages=book.languages, sections=len(sections), words=sum(s.words for s in sections))
            except KdpStudioError as error:
                entry.update(id=root.name, title=root.name, problem=error.message)
            found.append(entry)
        return found

    def open(self, path: str) -> dict[str, Any]:
        wanted = Path(path).expanduser().resolve()
        if str(wanted) not in {b["path"] for b in self.books()}:
            raise NotFoundError(f"No book at {path} in the library {self.library}")
        self.root = load_book(wanted).root
        self.reconcile()
        return {"book": self.book.id, "path": str(self.root)}

    def reconcile(self) -> None:
        """Once per book and runtime: a job this runtime started is still running."""

        from . import jobs

        if self.root not in self._reconciled:
            self._reconciled.add(self.root)
            jobs.reconcile(self.book)

    def catalogue(self) -> dict[str, Any]:
        """Edition templates and publisher profiles, with what this book uses."""

        from .cover import publishers

        book = self.book
        used = {kind: str(settings.get("template", "")) for kind, settings in book.editions.items()}
        chosen = str((book.editions.get("cover") or {}).get("publisher", "kdp"))
        templates = [{"name": t.name, "kind": t.kind, "title": t.title, "description": t.description,
                      "source": t.source, "origin": str(t.meta.get("origin", "")),
                      "fonts": list(t.meta.get("fonts") or []), "colors": dict(t.meta.get("colors") or {}),
                      "trims": sorted(t.meta.get("trims") or {}), "in_use": used.get(t.kind) == t.name}
                     for t in catalog.catalog(book.root)]
        profiles = [{"name": p.name, "title": p.title, "source": p.source, "bleed": p.bleed,
                     "spine_per_page": p.spine_per_page, "spine_text_pages": p.spine_text_pages,
                     "barcode": list(p.barcode_size), "ebook_pixels": list(p.ebook_pixels), "dpi": p.dpi,
                     "in_use": "cover" in book.editions and p.name == chosen}
                    for p in publishers(book.root).values()]
        return {"templates": templates, "publishers": profiles, "editions": book.editions,
                "overrides": (book.manifest.get("design") or {}).get("colors") or {}}

    def gallery(self, language: str, ink: str = "color") -> list[dict[str, Any]]:
        """Every theme, with its render over the specimen when there is one, and what this book uses."""

        from . import gallery

        book = self.book
        used = gallery.in_use(book)
        out = []
        for theme in gallery.themes(book.root):
            render = gallery.built(theme["name"], language, book.root, ink)
            out.append({**theme, "render": render,
                        "used_by": sorted(kind for kind, name in used.items() if name == theme["name"]),
                        "in_use": bool(used) and all(used.get(kind) == theme["name"] for kind in used
                                                     if kind in theme["kinds"]) and any(
                                                         kind in theme["kinds"] for kind in used)})
        return out

    # ------------------------------------------------------------ the ebook, read

    def _epub(self, language: str) -> Path:
        found = sorted(build_dir(self.book, language, "ebook").glob("*.epub"))
        if not found:
            raise NotFoundError(f"The {language} ebook is not built")
        return found[0]

    def epub_spine(self, language: str) -> dict[str, Any]:
        """The reading order of the built ebook, as a reader would follow it."""

        import zipfile
        from xml.etree import ElementTree as ET

        path = self._epub(language)
        opf, xhtml = "{http://www.idpf.org/2007/opf}", "{http://www.w3.org/1999/xhtml}"
        with zipfile.ZipFile(path) as epub:
            package = ET.fromstring(epub.read("OEBPS/content.opf"))
            nav = ET.fromstring(epub.read("OEBPS/nav.xhtml"))
            hrefs = {item.get("id"): item.get("href") for item in package.iter(f"{opf}item")}
            labels = {a.get("href"): "".join(a.itertext()).strip() for a in nav.iter(f"{xhtml}a")}
            # A page the contents do not list (the title page) is named by its own <title>.
            for href in hrefs.values():
                if href and href.endswith(".xhtml") and href not in labels:
                    title = ET.fromstring(epub.read(f"OEBPS/{href}")).find(f"{xhtml}head/{xhtml}title")
                    labels[href] = (title.text or "").strip() if title is not None else ""
        cover = next((item.get("href") for item in package.iter(f"{opf}item")
                      if "cover-image" in (item.get("properties") or "")), "")
        spine = [{"href": hrefs[ref.get("idref")], "title": labels.get(hrefs[ref.get("idref")], "")}
                 for ref in package.iter(f"{opf}itemref") if hrefs.get(ref.get("idref"))]
        return {"file": str(path.relative_to(self.root)), "built_at": path.stat().st_mtime, "cover": cover,
                "spine": spine}

    def epub_file(self, language: str, name: str) -> tuple[bytes, str]:
        import mimetypes
        import zipfile

        with zipfile.ZipFile(self._epub(language)) as epub:
            try:
                data = epub.read(f"OEBPS/{name}")
            except KeyError:
                raise NotFoundError(f"The ebook has no {name!r}") from None
        kind = "application/xhtml+xml" if name.endswith(".xhtml") else mimetypes.guess_type(name)[0]
        return data, kind or "application/octet-stream"

    @property
    def book(self) -> Book:
        return load_book(self.root)

    def overview(self) -> dict[str, Any]:
        book = self.book
        state = read_state(book.root)
        candidates: dict[tuple[str, str], int] = {}
        for entry in state.get("versions", {}).values():
            if entry["state"] == "candidate":
                key = (entry["language"], entry["section"])
                candidates[key] = candidates.get(key, 0) + 1

        reviews = gates.chapter_status(book)
        from .translation import section_states

        translated = {language: section_states(book, language) for language in book.languages
                      if language != book.source_language}

        def section(s, language: str) -> dict[str, Any]:
            return {"type": "section", "id": s.id, "kind": s.kind, "number": s.number, "title": s.title,
                    "toc_title": s.toc_title, "words": s.words, "candidates": candidates.get((language, s.id), 0),
                    "synopsis": s.synopsis, "promise": s.promise,
                    "review": reviews.get(s.id) if language == book.source_language else None,
                    "translation": translated[language][s.id]["state"] if language in translated else None}

        languages = {}
        for language in book.languages:
            entries = []
            for entry in book.contents(language):
                if isinstance(entry, Part):
                    entries.append({"type": "part", "id": entry.id, "kind": entry.kind, "number": entry.number,
                                    "title": entry.title, "sections": [section(s, language) for s in entry.sections]})
                else:
                    entries.append(section(entry, language))
            meta = book.meta(language)
            languages[language] = {"title": meta.get("title", book.id), "subtitle": meta.get("subtitle", ""),
                                   "contents": entries}
        return {
            "id": book.id, "author": book.author, "source_language": book.source_language,
            "languages": languages, "editions": book.editions, "revision": state["revision"],
            "gates": gates.gate_status(book),
        }

    def section(self, language: str, section_id: str) -> dict[str, Any]:
        book = self.book
        found = next((s for s in book.sections(language) if s.id == section_id), None)
        if found is None:
            raise NotFoundError(f"No section {section_id!r} in {language}")
        context = RenderContext(language, load_labels(language, book.meta(language).get("labels")),
                                prompt_url=lambda i: (book.manifest.get("exercises") or {}).get("url", "")
                                .format(language=language, id=i))
        try:
            preview = XhtmlRenderer(context).section(found)
            problem = ""
        except KdpStudioError as error:
            preview, problem = "", error.message
        return {**versions.read_section(book, language, section_id), "title": found.title,
                "number": found.number, "kind": found.kind, "words": found.words, "preview": preview,
                "problem": problem, "versions": versions.list_versions(book, language, section_id)}

    def version(self, version_id: str) -> dict[str, Any]:
        """A version against the current text; a translation also against its source."""

        book = self.book
        found = versions.version_report(book, version_id)
        if found["language"] != book.source_language:
            from .translation import compare_translation, glossary

            source = versions.read_section(book, book.source_language, found["section"])["text"]
            found["translation"] = [f.public_dict() for f in compare_translation(
                source, found["text"], source_language=book.source_language, language=found["language"],
                terms=glossary(book))]
        return found

    def editions(self, language: str) -> dict[str, Any]:
        book = self.book
        out = {}
        for edition, settings in book.editions.items():
            folder = build_dir(book, language, edition)
            built = sorted(folder.glob("*.pdf")) + sorted(folder.glob("*.epub")) + sorted(folder.glob("*-cover-*.jpg"))
            out[edition] = {"settings": settings,
                            # What to look at: the ebook cover, and the wrap as a picture.
                            "images": [p.name for p in (*sorted(folder.glob("*-cover-ebook.jpg")),
                                                        folder / "preview-print.png")
                                       if edition == "cover" and p.is_file()],
                            "built": str(built[0].relative_to(book.root)) if built else "",
                            "built_at": built[0].stat().st_mtime if built else 0,
                            "check": last_report(book, language, edition)}
        return out

    def proofs(self, language: str) -> list[str]:
        return [p.name for p in proofs.proofs(self.book, language)]

    def proof_path(self, language: str, name: str) -> Path:
        path = proofs.interior(self.book, language).parent / "proofs" / name
        if not path.is_file() or path.suffix != ".png" or "/" in name:
            raise NotFoundError(f"No proof {name!r}")
        return path

    def cover_image(self, language: str, name: str) -> Path:
        path = build_dir(self.book, language, "cover") / name
        if "/" in name or path.suffix not in (".jpg", ".png") or not path.is_file():
            raise NotFoundError(f"No cover image {name!r}")
        return path

    def document(self, relative: str) -> dict[str, Any]:
        path = (self.root / relative).resolve()
        allowed = [(self.root / d).resolve() for d in (*DOCUMENTS, "research")]
        if path.suffix != ".md" or not any(path == a or a in path.parents for a in allowed) or not path.is_file():
            raise NotFoundError(f"No document {relative!r}")
        return {"path": relative, "text": path.read_text("utf-8")}

    def document_any(self, relative: str) -> str:
        """A research dossier or editorial document, read-only, inside the book."""

        path = (self.root / relative).resolve()
        if self.root.resolve() not in path.parents or path.suffix != ".md" or not path.is_file():
            raise NotFoundError(f"No document {relative!r}")
        return path.read_text("utf-8")

    def documents(self) -> list[str]:
        found = ["intentions.md"] if (self.root / "intentions.md").is_file() else []
        editorial = self.root / "editorial"
        if editorial.is_dir():
            found += [str(p.relative_to(self.root)) for p in sorted(editorial.rglob("*.md"))]
        research = self.root / "research"
        if research.is_dir():
            found += [str(p.relative_to(self.root)) for p in sorted(research.glob("*.md"))]
        return found

    def ebook_css(self) -> str:
        book = self.book
        name = (book.editions.get("ebook") or {}).get("template", "nocturne")
        return (catalog.get("ebook", name, book.root).path / "style.css").read_text("utf-8")

    def command(self, name: str, payload: dict[str, Any], actor: Actor) -> dict[str, Any]:
        return dispatch(self.book, name, payload, actor)


def create_app(root: Path | Studio, *, copilot_url: str = "", assistant_reason: str = "") -> Any:
    try:
        from fastapi import FastAPI
        from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as error:
        raise ToolUnavailableError("The control room needs the studio extra: uv sync --extra studio") from error

    # The assistant, when on, shares this Studio: opening another book moves both.
    studio = root if isinstance(root, Studio) else Studio(root)
    studio.reconcile()
    app = FastAPI(title="KDP Studio")
    app.state.studio = studio

    @app.exception_handler(KdpStudioError)
    async def domain_error(request, error: KdpStudioError):
        return JSONResponse(error.public_dict(), status_code=STATUS.get(error.code, 400))

    @app.get("/api/info")
    def info():
        return {"book": studio.book.id, "assistant": bool(copilot_url), "assistant_reason": assistant_reason,
                "person": person().public_dict(), "path": str(studio.root), "library": str(studio.library)}

    @app.get("/api/library")
    def library():
        return studio.books()

    @app.post("/api/open")
    async def open_book(request: Request):
        body = await request.json()
        if not isinstance(body, dict) or not body.get("path"):
            raise ValidationError("Opening a book needs its path")
        return studio.open(str(body["path"]))

    @app.get("/api/epub")
    def epub(lang: str):
        return studio.epub_spine(lang)

    @app.get("/epub/{lang}/{name:path}")
    def epub_file(lang: str, name: str):
        data, kind = studio.epub_file(lang, name)
        return Response(data, media_type=kind, headers={"Cache-Control": "no-store"})

    @app.get("/api/book")
    def book():
        return studio.overview()

    @app.get("/api/section")
    def section(lang: str, id: str):
        return studio.section(lang, id)

    @app.get("/api/version")
    def version(id: str):
        return studio.version(id)

    @app.get("/api/versions")
    def all_versions(lang: str | None = None):
        return versions.list_versions(studio.book, lang)

    @app.get("/api/editions")
    def editions(lang: str):
        return studio.editions(lang)

    @app.get("/api/proofs")
    def proof_list(lang: str):
        return studio.proofs(lang)

    @app.get("/proofs/{lang}/{name}")
    def proof(lang: str, name: str):
        return FileResponse(studio.proof_path(lang, name), media_type="image/png")

    @app.get("/covers/{lang}/{name}")
    def cover_image(lang: str, name: str):
        return FileResponse(studio.cover_image(lang, name))

    @app.get("/api/art")
    def art_list():
        from . import art

        return art.records(studio.book)

    @app.get("/api/documents")
    def documents():
        return studio.documents()

    @app.get("/api/document")
    def document(path: str):
        return studio.document(path)

    @app.get("/api/gallery")
    def gallery_list(lang: str, ink: str = "color"):
        return studio.gallery(lang, ink)

    @app.post("/api/gallery/build")
    async def gallery_build(request: Request):
        # A render is a cache, not a change to any book: no command, no record.
        from . import gallery

        body = await request.json()
        if not isinstance(body, dict) or not body.get("theme") or not body.get("language"):
            raise ValidationError("A render needs a theme and a language")
        return gallery.build(str(body["theme"]), str(body["language"]), studio.root, str(body.get("ink") or "color"))

    @app.get("/gallery/{key}/epub/{name:path}")
    def gallery_epub(key: str, name: str):
        from . import gallery

        data, kind = gallery.epub_file(key, name)
        return Response(data, media_type=kind)

    @app.get("/gallery/{key}/{name:path}")
    def gallery_file(key: str, name: str):
        from . import gallery

        return FileResponse(gallery.file(key, name))

    @app.get("/api/templates")
    def templates():
        return studio.catalogue()

    @app.get("/api/style")
    def style(lang: str, section: str | None = None, engines: bool = False):
        from .style import check_style

        return check_style(studio.book, lang, [section] if section else None, engines=engines).public_dict()

    @app.get("/api/translation")
    def translation(lang: str):
        from .translation import report

        return report(studio.book, lang)

    @app.get("/api/continuity")
    def continuity(lang: str):
        from .continuity import repetitions

        return repetitions(studio.book, lang)

    @app.get("/api/plans")
    def plan_list():
        from .agents.architect import plans

        return plans(studio.book)

    @app.get("/api/sources")
    def source_list():
        from .agents.researcher import ledger

        return ledger(studio.book)

    @app.get("/api/jobs")
    def job_list():
        from . import jobs

        return jobs.list_jobs(studio.book)

    @app.get("/ebook.css")
    def ebook_css():
        return PlainTextResponse(studio.ebook_css(), media_type="text/css")

    @app.post("/api/commands")
    async def commands(request: Request):
        body = await request.json()
        if not isinstance(body, dict) or not body.get("command"):
            raise ValidationError("A command needs a name")
        # The browser always acts as the person at this machine; agents reach
        # commands inside the process, with their own actor.
        result = studio.command(str(body["command"]), dict(body.get("payload") or {}), person())
        return {"result": result, "revision": read_state(studio.root)["revision"]}

    if copilot_url:
        import httpx

        client = httpx.AsyncClient(base_url=copilot_url, timeout=None)

        @app.api_route("/api/copilotkit/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
        async def copilotkit(path: str, request: Request):
            hop = {"host", "content-length", "connection", "transfer-encoding"}
            upstream = await client.send(client.build_request(
                request.method, f"/api/copilotkit/{path}", params=request.query_params,
                headers={k: v for k, v in request.headers.items() if k.lower() not in hop},
                content=await request.body()), stream=True)
            return StreamingResponse(upstream.aiter_raw(), status_code=upstream.status_code,
                                     headers={k: v for k, v in upstream.headers.items() if k.lower() not in hop},
                                     background=None)

    app_dir = WEB_ASSETS / "app"
    if app_dir.is_dir():
        app.mount("/", StaticFiles(directory=app_dir, html=True), name="app")
    return app

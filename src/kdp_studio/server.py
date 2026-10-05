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
    """Queries over one book. Every call reloads it: the files are the truth."""

    def __init__(self, root: Path) -> None:
        self.root = load_book(root).root

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

        def section(s, language: str) -> dict[str, Any]:
            return {"type": "section", "id": s.id, "kind": s.kind, "number": s.number, "title": s.title,
                    "toc_title": s.toc_title, "words": s.words, "candidates": candidates.get((language, s.id), 0)}

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

    def editions(self, language: str) -> dict[str, Any]:
        book = self.book
        out = {}
        for edition, settings in book.editions.items():
            folder = build_dir(book, language, edition)
            built = sorted(folder.glob("*.pdf")) + sorted(folder.glob("*.epub"))
            out[edition] = {"settings": settings,
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

    def document(self, relative: str) -> dict[str, Any]:
        path = (self.root / relative).resolve()
        allowed = [(self.root / d).resolve() for d in DOCUMENTS]
        if path.suffix != ".md" or not any(path == a or a in path.parents for a in allowed) or not path.is_file():
            raise NotFoundError(f"No document {relative!r}")
        return {"path": relative, "text": path.read_text("utf-8")}

    def documents(self) -> list[str]:
        found = ["intentions.md"] if (self.root / "intentions.md").is_file() else []
        editorial = self.root / "editorial"
        if editorial.is_dir():
            found += [str(p.relative_to(self.root)) for p in sorted(editorial.rglob("*.md"))]
        return found

    def ebook_css(self) -> str:
        book = self.book
        name = (book.editions.get("ebook") or {}).get("template", "nocturne")
        return (catalog.get("ebook", name, book.root).path / "style.css").read_text("utf-8")

    def command(self, name: str, payload: dict[str, Any], actor: Actor) -> dict[str, Any]:
        return dispatch(self.book, name, payload, actor)


def create_app(root: Path, *, copilot_url: str = "", assistant_reason: str = "") -> Any:
    try:
        from fastapi import FastAPI
        from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as error:
        raise ToolUnavailableError("The control room needs the studio extra: uv sync --extra studio") from error

    studio = Studio(root)
    from . import jobs

    jobs.reconcile(studio.book)
    app = FastAPI(title="KDP Studio")
    app.state.studio = studio

    @app.exception_handler(KdpStudioError)
    async def domain_error(request, error: KdpStudioError):
        return JSONResponse(error.public_dict(), status_code=STATUS.get(error.code, 400))

    @app.get("/api/info")
    def info():
        return {"book": studio.book.id, "assistant": bool(copilot_url), "assistant_reason": assistant_reason,
                "person": person().public_dict()}

    @app.get("/api/book")
    def book():
        return studio.overview()

    @app.get("/api/section")
    def section(lang: str, id: str):
        return studio.section(lang, id)

    @app.get("/api/version")
    def version(id: str):
        return versions.version_report(studio.book, id)

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

    @app.get("/api/documents")
    def documents():
        return studio.documents()

    @app.get("/api/document")
    def document(path: str):
        return studio.document(path)

    @app.get("/api/templates")
    def templates():
        return [{"name": t.name, "kind": t.kind, "title": t.title, "description": t.description, "source": t.source}
                for t in catalog.catalog(studio.root)]

    @app.get("/api/style")
    def style(lang: str, section: str | None = None, engines: bool = False):
        from .style import check_style

        return check_style(studio.book, lang, [section] if section else None, engines=engines).public_dict()

    @app.get("/api/continuity")
    def continuity(lang: str):
        from .continuity import repetitions

        return repetitions(studio.book, lang)

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

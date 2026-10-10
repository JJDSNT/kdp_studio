"""Building editions: the print interior (LuaLaTeX) and the ebook (EPUB 3).

Builds go to ``<book>/builds/<language>/<edition>/`` and are disposable: they
are always regenerated from the manuscript and the template, never edited.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import jinja2

from . import catalog
from .book import Book, Part, Section
from .errors import BuildError, ToolUnavailableError, ValidationError
from .labels import labels as load_labels
from .render import RenderContext
from .render.latex import LatexRenderer, escape
from .render.xhtml import XhtmlRenderer, x


@dataclass
class BuildResult:
    edition: str
    language: str
    output: Path
    template: str
    exercises: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


def edition_settings(book: Book, edition: str) -> dict[str, Any]:
    settings = book.editions.get(edition)
    if not settings:
        raise ValidationError(f"book.yaml declares no {edition!r} edition", editions=sorted(book.editions))
    if not settings.get("template"):
        raise ValidationError(f"The {edition} edition needs a template", edition=edition)
    return dict(settings)


def build_dir(book: Book, language: str, edition: str) -> Path:
    return book.root / "builds" / language / edition


def _context(book: Book, language: str, out: Path, qr_colors: tuple[str, str]) -> RenderContext:
    meta = book.meta(language)
    url_pattern = str((book.manifest.get("exercises") or {}).get("url", ""))

    def prompt_url(exercise_id: str) -> str:
        return url_pattern.format(language=language, id=exercise_id) if url_pattern else ""

    def qr_path(exercise_id: str, url: str) -> str:
        return write_qr(out / "qr" / f"{exercise_id}.png", url, qr_colors)

    return RenderContext(language, load_labels(language, meta.get("labels")), prompt_url, qr_path)


def write_qr(path: Path, url: str, colors: tuple[str, str]) -> str:
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_M
    except ImportError as error:  # pragma: no cover - depends on the extra
        raise ToolUnavailableError("QR codes need the build extra: uv sync --extra build") from error
    path.parent.mkdir(parents=True, exist_ok=True)
    # border=4: the QR standard requires a quiet zone of 4 modules; with less,
    # some readers fail, and nobody knows which reader the book's reader has.
    code = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=12, border=4)
    code.add_data(url)
    code.make(fit=True)
    code.make_image(fill_color=f"#{colors[0]}", back_color=f"#{colors[1]}").save(path)
    return f"qr/{path.name}"


# ------------------------------------------------------------------ print

def _latex_env(template_dir: Path) -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        block_start_string="((*", block_end_string="*))",
        variable_start_string="(((", variable_end_string=")))",
        comment_start_string="((=", comment_end_string="=))",
        undefined=jinja2.StrictUndefined, keep_trailing_newline=True, autoescape=False,
    )
    env.filters["latex"] = escape
    return env


def build_print(book: Book, language: str, *, bleed: bool | None = None, engine_runs: int = 2) -> BuildResult:
    settings = edition_settings(book, "print")
    template = catalog.get("print", settings["template"], book.root)
    trims = template.meta.get("trims") or {}
    trim_name = str(settings.get("trim", next(iter(trims), "")))
    if trim_name not in trims:
        raise ValidationError(f"Template {template.name!r} has no layout for trim {trim_name!r}",
                              trims=sorted(trims))
    if bleed is None:
        bleed = bool(settings.get("bleed", template.meta.get("needs_bleed", False)))
    colors = {**(template.meta.get("colors") or {}), **((book.manifest.get("design") or {}).get("colors") or {})}

    out = build_dir(book, language, "print")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    context = _context(book, language, out, (colors.get("ink", "000000"), colors.get("shade_light", "FFFFFF")))
    renderer = LatexRenderer(context)
    body = "\n\n".join(renderer.entry(entry) for entry in book.contents(language))
    (out / "body.tex").write_text(body + "\n", encoding="utf-8")

    meta = book.meta(language)
    source = _latex_env(template.path).get_template("book.tex.j2").render(
        title=meta.get("title", book.id), subtitle=meta.get("subtitle", ""), tagline=meta.get("tagline", ""),
        author=book.author, language=language, labels=context.labels, colors=colors,
        trim=trims[trim_name], bleed=bleed,
        colophon=renderer.document(str(meta.get("colophon", ""))),
    )
    (out / "book.tex").write_text(source, encoding="utf-8")

    engine = str(template.meta.get("engine", "lualatex"))
    if not shutil.which(engine):
        raise ToolUnavailableError(f"{engine} is not installed; `kdp doctor` says how to install it")
    for _ in range(engine_runs):
        run = subprocess.run([engine, "-interaction=nonstopmode", "-halt-on-error", "book.tex"],
                             cwd=out, capture_output=True, text=True)
        if run.returncode != 0:
            tail = "\n".join(run.stdout.splitlines()[-25:])
            raise BuildError(f"{engine} failed; see {out / 'book.log'}", log_tail=tail)
    name = f"{book.id}-{language}-interior{'-bleed' if bleed else ''}.pdf"
    pdf = out / name
    (out / "book.pdf").rename(pdf)
    log = (out / "book.log").read_text("utf-8", errors="replace")
    return BuildResult("print", language, pdf, template.name, context.exercises, {
        "trim": trim_name,
        "bleed": bleed,
        "paper": settings.get("paper", "white"),
        "overfull": len(re.findall(r"^Overfull \\[hv]box", log, re.M)),
        "underfull": len(re.findall(r"^Underfull \\[hv]box", log, re.M)),
    })


# ------------------------------------------------------------------ ebook

def _page(title: str, body: str, language: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            f'xml:lang="{language}" lang="{language}">\n'
            f'<head><meta charset="utf-8" /><title>{x(title)}</title>'
            '<link rel="stylesheet" type="text/css" href="style.css" /></head>\n'
            f'<body>{body}</body></html>\n')


def build_ebook(book: Book, language: str) -> BuildResult:
    settings = edition_settings(book, "ebook")
    template = catalog.get("ebook", settings["template"], book.root)
    out = build_dir(book, language, "ebook")
    if out.exists():
        shutil.rmtree(out)
    work = out / "OEBPS"
    work.mkdir(parents=True)
    context = _context(book, language, work, ("12202B", "FFFFFF"))
    renderer = XhtmlRenderer(context)
    meta = book.meta(language)
    title = str(meta.get("title", book.id))

    # (href, toc label, xhtml body, is part)
    documents: list[tuple[str, str, str, bool]] = []
    title_page = (f'<section class="title-page"><h1>{x(title)}</h1>'
                  + (f'<p class="subtitle">{x(meta["subtitle"])}</p>' if meta.get("subtitle") else "")
                  + (f'<p class="tagline">{x(meta["tagline"])}</p>' if meta.get("tagline") else "")
                  + f'<p>{x(book.author)}</p></section>'
                  + (f'<section class="colophon">{renderer.document(str(meta["colophon"]))}</section>'
                     if meta.get("colophon") else ""))
    documents.append(("title.xhtml", title, title_page, False))
    index = 0
    for entry in book.contents(language):
        sections: list[Section] = []
        if isinstance(entry, Part):
            index += 1
            documents.append((f"part-{index:02d}.xhtml", renderer.part_label(entry), renderer.part_page(entry), True))
            sections = list(entry.sections)
        else:
            sections = [entry]
        for section in sections:
            index += 1
            documents.append((f"text-{index:02d}-{section.id}.xhtml", renderer.section_label(section),
                              renderer.section(section), False))

    identifier = str(meta.get("identifier") or f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, f'kdp:{book.id}:{language}')}")
    files: dict[str, str] = {
        "style.css": (template.path / "style.css").read_text("utf-8"),
        "nav.xhtml": _nav(documents, context.label("contents"), language),
        "toc.ncx": _ncx(documents, title, identifier, language),
    }
    for href, label, body, _ in documents:
        files[href] = _page(label, body, language)
    cover = _ebook_cover(book, language)
    files["content.opf"] = _opf(documents, meta, book, identifier, language, sorted((work / "qr").glob("*.png"))
                                if (work / "qr").is_dir() else [], cover)
    _check_links(files)

    epub = out / f"{book.id}-{language}.epub"
    with zipfile.ZipFile(epub, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml",
                         '<?xml version="1.0" encoding="utf-8"?><container version="1.0" '
                         'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                         '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml" />'
                         '</rootfiles></container>', compress_type=zipfile.ZIP_DEFLATED)
        for name, content in files.items():
            archive.writestr(f"OEBPS/{name}", content.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        for image in sorted((work / "qr").glob("*.png")) if (work / "qr").is_dir() else []:
            archive.write(image, f"OEBPS/qr/{image.name}", compress_type=zipfile.ZIP_DEFLATED)
        if cover:
            archive.write(cover, f"OEBPS/cover{cover.suffix}", compress_type=zipfile.ZIP_DEFLATED)
    return BuildResult("ebook", language, epub, template.name, context.exercises,
                       {"documents": len(documents), "cover": str(cover.relative_to(book.root)) if cover else ""})


def _ebook_cover(book: Book, language: str) -> Path | None:
    for name in ("ebook.jpg", "ebook.jpeg", "ebook.png"):
        path = book.root / "cover" / language / name
        if path.is_file():
            return path
    # No cover supplied by the author: the one the cover template built, if any.
    built = sorted(build_dir(book, language, "cover").glob("*-cover-ebook.jpg"))
    return built[0] if built else None


def _nav(documents, heading: str, language: str) -> str:
    items, open_part = [], False
    for href, label, _, is_part in documents[1:]:
        if is_part:
            if open_part:
                items.append("</ol></li>")
            items.append(f'<li class="toc-part"><a href="{href}">{x(label)}</a><ol>')
            open_part = True
        else:
            items.append(f'<li><a href="{href}">{x(label)}</a></li>')
    if open_part:
        items.append("</ol></li>")
    body = f'<nav epub:type="toc" id="toc"><h1>{x(heading)}</h1><ol>{"".join(items)}</ol></nav>'
    return _page(heading, body, language)


def _ncx(documents, title: str, identifier: str, language: str) -> str:
    points = "".join(
        f'<navPoint id="n{i}" playOrder="{i + 1}"><navLabel><text>{x(label)}</text></navLabel>'
        f'<content src="{href}" /></navPoint>' for i, (href, label, _, _) in enumerate(documents))
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            f'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="{language}">'
            f'<head><meta name="dtb:uid" content="{x(identifier)}" /></head>'
            f'<docTitle><text>{x(title)}</text></docTitle><navMap>{points}</navMap></ncx>')


def _opf(documents, meta, book: Book, identifier: str, language: str, qr_images, cover: Path | None) -> str:
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    items = [f'<item id="d{i}" href="{href}" media-type="application/xhtml+xml" />'
             for i, (href, _, _, _) in enumerate(documents)]
    items += [f'<item id="qr{i}" href="qr/{p.name}" media-type="image/png" />' for i, p in enumerate(qr_images)]
    cover_meta = ""
    if cover:
        media = "image/png" if cover.suffix == ".png" else "image/jpeg"
        items.append(f'<item id="cover-image" href="cover{cover.suffix}" media-type="{media}" properties="cover-image" />')
        cover_meta = '<meta name="cover" content="cover-image" />'
    # The nav document is in the spine, not only in the manifest: outside the
    # linear reading order many readers never show a contents page.
    spine = ['<itemref idref="d0" />', '<itemref idref="nav" />'] + [
        f'<itemref idref="d{i}" />' for i in range(1, len(documents))]
    # Title and subtitle are separate dc:title elements with title-type: one
    # long dc:title truncates badly in the reader's header.
    subtitle = (f'<dc:title id="t-sub">{x(meta["subtitle"])}</dc:title>'
                '<meta refines="#t-sub" property="title-type">subtitle</meta>') if meta.get("subtitle") else ""
    description = f'<dc:description>{x(str(meta["description"]))}</dc:description>' if meta.get("description") else ""
    return f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id" xml:lang="{language}">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">{x(identifier)}</dc:identifier>
    <dc:title id="t-main">{x(str(meta.get("title", book.id)))}</dc:title>
    <meta refines="#t-main" property="title-type">main</meta>
    {subtitle}
    <dc:creator>{x(book.author)}</dc:creator>
    <dc:language>{language}</dc:language>
    {description}
    <meta property="dcterms:modified">{modified}</meta>
    {cover_meta}
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />
    <item id="css" href="style.css" media-type="text/css" />
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />
    {"".join(items)}
  </manifest>
  <spine toc="ncx">{"".join(spine)}</spine>
</package>'''


def _check_links(files: dict[str, str]) -> None:
    """No broken internal link leaves the build."""

    ids: dict[str, set[str]] = {}
    for name, content in files.items():
        if name.endswith((".xhtml", ".opf", ".ncx")):
            try:
                tree = ET.fromstring(content)
            except ET.ParseError as error:
                raise BuildError(f"{name} is not well-formed XML: {error}") from error
            ids[name] = {node.attrib["id"] for node in tree.iter() if "id" in node.attrib}
    for name, content in files.items():
        if not name.endswith(".xhtml"):
            continue
        for href in re.findall(r'<a href="([^"]+)"', content):
            href = html.unescape(href)
            if ":" in href:
                continue
            target, _, fragment = href.partition("#")
            target = target or name
            if target not in files or (fragment and fragment not in ids.get(target, set())):
                raise BuildError(f"Broken internal link in {name}: {href}")

"""Covers: the ebook front and the print wrap, set by code (docs/templates.md).

A cover is art plus words. The art is a picture of the book (art.py) and
carries no lettering; every word -- title, subtitle, author, tagline, the
spine, the back-cover copy -- is set by the cover template from `meta.yaml`,
with the book's fonts, as vector text. So a title cannot be misspelt by an
image model, and one picture serves every language.

One design gives two files, in `builds/<language>/cover/`:

- the ebook cover, at the pixels the publisher asks, which the ebook build
  embeds;
- the print wrap -- bleed, back, spine, front, bleed -- sized from the
  book's trim and the page count of the built interior. It exists only once
  the interior does, and it is stale as soon as the page count moves
  (docs/origin, §11: freeze the text, count, compute the spine, then the
  cover; never the reverse).

Nothing here is one publisher's: bleed, spine per page and paper, the
barcode's place, the ebook's pixels come from a publisher profile
(`publishers/<name>.yaml`, the book's own included), and the trim from the
print edition. A cover is as large as the book and its printer make it.

The night laid over the art so the words stay readable is baked into the
picture: the print file carries no transparency.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from . import art, catalog
from .book import Book
from .build import BuildResult, _context, _latex_env, build_dir, edition_settings
from .errors import BookFormatError, BuildError, NotFoundError, ToolUnavailableError, ValidationError
from .fidelity import digest
from .render.latex import LatexRenderer

REPORT = "cover.json"
#: The ebook front is typeset on a sheet this wide, at the publisher's proportion.
EBOOK_SHEET_WIDTH = 6.0


@dataclass(frozen=True)
class Publisher:
    """What a publisher or printer asks of a cover (publishers/<name>.yaml)."""

    name: str
    title: str
    bleed: float
    spine_base: float
    spine_per_page: dict[str, float]
    spine_text_pages: int
    spine_text_margin: float
    barcode_size: tuple[float, float]
    barcode_from_spine: float
    barcode_from_foot: float
    safe: float
    dpi: int
    ebook_pixels: tuple[int, int]
    ebook_megabytes: float
    source: str = "built-in"


def publishers(book_root: Path | None = None) -> dict[str, Publisher]:
    """Built-in profiles, then the book's own; a later one replaces the same name."""

    roots = [("built-in", Path(str(resources.files(__package__).joinpath("publishers"))))]
    if book_root is not None:
        roots.append(("book", book_root / "publishers"))
    found: dict[str, Publisher] = {}
    for source, root in roots:
        for path in sorted(root.glob("*.yaml")) if root.is_dir() else []:
            data = yaml.safe_load(path.read_text("utf-8")) or {}
            try:
                found[path.stem] = Publisher(
                    name=path.stem, title=str(data.get("title", path.stem)), bleed=float(data["bleed"]),
                    spine_base=float((data["spine"]).get("base", 0)),
                    spine_per_page={str(k): float(v) for k, v in data["spine"]["per_page"].items()},
                    spine_text_pages=int(data["spine_text"]["min_pages"]),
                    spine_text_margin=float(data["spine_text"]["margin"]),
                    barcode_size=tuple(float(v) for v in data["barcode"]["size"]),
                    barcode_from_spine=float(data["barcode"]["from_spine"]),
                    barcode_from_foot=float(data["barcode"]["from_foot"]),
                    safe=float(data.get("safe", 0.125)), dpi=int(data.get("dpi", 300)),
                    ebook_pixels=tuple(int(v) for v in data["ebook"]["pixels"]),
                    ebook_megabytes=float(data["ebook"].get("max_megabytes", 50)), source=source)
            except (KeyError, TypeError, ValueError) as error:
                raise BookFormatError(f"{path.name}: the publisher profile is incomplete ({error})") from error
    return found


def publisher(book: Book) -> Publisher:
    name = str((book.editions.get("cover") or {}).get("publisher", "kdp"))
    found = publishers(book.root)
    if name not in found:
        raise NotFoundError(f"No publisher profile named {name!r}", available=sorted(found))
    return found[name]


@dataclass(frozen=True)
class Wrap:
    """The print wrap, in inches from the lower-left corner of the sheet."""

    trim: tuple[float, float]
    pages: int
    paper: str
    spine: float
    bleed: float
    barcode: tuple[float, float, float, float]

    @property
    def width(self) -> float:
        return round(2 * self.bleed + 2 * self.trim[0] + self.spine, 4)

    @property
    def height(self) -> float:
        return round(self.trim[1] + 2 * self.bleed, 4)

    @property
    def spine_left(self) -> float:
        return round(self.bleed + self.trim[0], 4)

    @property
    def front_left(self) -> float:
        return round(self.spine_left + self.spine, 4)


def wrap(trim: tuple[float, float], pages: int, paper: str, rules: Publisher) -> Wrap:
    """Bleed, back, spine, front, bleed: the sheet a book of this trim and length needs."""

    if paper not in rules.spine_per_page:
        raise ValidationError(f"{rules.title} has no spine figure for {paper!r} paper",
                              allowed=sorted(rules.spine_per_page))
    spine = round(rules.spine_base + pages * rules.spine_per_page[paper], 4)
    x1 = rules.bleed + trim[0] - rules.barcode_from_spine
    y0 = rules.bleed + rules.barcode_from_foot
    barcode = (round(x1 - rules.barcode_size[0], 4), round(y0, 4), round(x1, 4),
               round(y0 + rules.barcode_size[1], 4))
    return Wrap(trim, pages, paper, spine, rules.bleed, barcode)


def print_trim(book: Book) -> tuple[tuple[float, float], str] | None:
    """The trim and paper of the print edition, when the book has one."""

    settings = book.editions.get("print")
    if not settings:
        return None
    template = catalog.get("print", str(settings.get("template")), book.root)
    trims = template.meta.get("trims") or {}
    name = str(settings.get("trim", next(iter(trims), "")))
    if name not in trims:
        raise ValidationError(f"Template {template.name!r} has no layout for trim {name!r}", trims=sorted(trims))
    width, height = (float(str(v).removesuffix("in")) for v in trims[name]["paper"])
    return (width, height), str(settings.get("paper", "white"))


def interior_pages(book: Book, language: str) -> tuple[int, str] | None:
    """Pages of the built print interior, and its digest; None when it is not built."""

    pdfs = sorted(build_dir(book, language, "print").glob("*.pdf"))
    if not pdfs:
        return None
    from pypdf import PdfReader

    return len(PdfReader(str(pdfs[0])).pages), digest(pdfs[0].read_bytes())


def title_lines(title: str, declared: Any = None) -> list[str]:
    """The title as the cover breaks it; the last line is the one the design stresses."""

    if declared:
        lines = [str(line).strip() for line in (declared if isinstance(declared, list) else [declared])]
        return [line for line in lines if line]
    words = title.split()
    return [" ".join(words[:-1]), words[-1]] if len(words) > 1 else [title]


def _panel_art(source: Path, out: Path, box: tuple[float, float], focus: tuple[float, float], ground: str,
               scrim: list[list[float]], edge_fade: float) -> dict[str, Any]:
    """The art cropped to a panel around its focus, with the scrim baked in."""

    from PIL import Image

    with Image.open(source) as opened:
        image = opened.convert("RGB")
    ratio = box[0] / box[1]
    width, height = image.size
    crop_w, crop_h = (width, round(width / ratio)) if width / height < ratio else (round(height * ratio), height)
    left = min(max(round(focus[0] * width - crop_w / 2), 0), width - crop_w)
    top = min(max(round(focus[1] * height - crop_h / 2), 0), height - crop_h)
    image = image.crop((left, top, left + crop_w, top + crop_h))
    night = Image.new("RGB", image.size, f"#{ground}")

    def opacity(position: float) -> float:
        for (a, value_a), (b, value_b) in zip(scrim, scrim[1:]):
            if a <= position <= b:
                return value_a + (value_b - value_a) * ((position - a) / (b - a) if b > a else 0)
        return 0.0

    if scrim:
        column = Image.new("L", (1, crop_h))
        column.putdata([round(255 * opacity(y / max(crop_h - 1, 1))) for y in range(crop_h)])
        image = Image.composite(night, image, column.resize(image.size))
    if edge_fade > 0:
        reach = max(round(crop_w * edge_fade), 1)
        row = Image.new("L", (crop_w, 1))
        row.putdata([round(255 * max(0.0, 1 - x / reach)) for x in range(crop_w)])
        image = Image.composite(night, image, row.resize(image.size))
    image.save(out, quality=95)
    return {"pixels": [crop_w, crop_h], "dpi": round(crop_w / box[0], 1)}


def _typeset(folder: Path, name: str, source: str, engine: str) -> tuple[Path, str]:
    (folder / f"{name}.tex").write_text(source, encoding="utf-8")
    if not shutil.which(engine):
        raise ToolUnavailableError(f"{engine} is not installed; `kdp doctor` says how to install it")
    run = subprocess.run([engine, "-interaction=nonstopmode", "-halt-on-error", f"{name}.tex"], cwd=folder,
                         capture_output=True, text=True)
    if run.returncode != 0:
        raise BuildError(f"{engine} failed on the cover; see {folder / (name + '.log')}",
                         log_tail="\n".join(run.stdout.splitlines()[-25:]))
    return folder / f"{name}.pdf", (folder / f"{name}.log").read_text("utf-8", errors="replace")


def _raster(pdf: Path, out: Path, device: str, *extra: str) -> None:
    if not shutil.which("gs"):
        raise ToolUnavailableError("Ghostscript is needed to rasterise the cover; `kdp doctor` says how")
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", f"-sDEVICE={device}", "-dTextAlphaBits=4",
                    "-dGraphicsAlphaBits=4", *extra, f"-sOutputFile={out}", str(pdf)], check=True,
                   capture_output=True)


def _at(x: float, y: float) -> str:
    return f"({x:.4f},{y:.4f})"


def build_cover(book: Book, language: str) -> BuildResult:
    settings = edition_settings(book, "cover")
    template = catalog.get("cover", settings["template"], book.root)
    rules = publisher(book)
    meta = book.meta(language)
    words = meta.get("cover") or {}
    if not isinstance(words, dict):
        raise ValidationError(f"manuscript/{language}/meta.yaml: `cover` must be a mapping")
    colors = {**(template.meta.get("colors") or {}), **((book.manifest.get("design") or {}).get("colors") or {})}
    out = build_dir(book, language, "cover")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    context = _context(book, language, out, ("000000", "FFFFFF"))
    renderer = LatexRenderer(context)
    env = _latex_env(template.path)
    engine = str(template.meta.get("engine", "lualatex"))
    title = str(meta.get("title", book.id))
    base_margin = float(template.meta.get("margin", 0.5))
    scrim = [list(map(float, pair)) for pair in template.meta.get("scrim") or []]
    picture = art.get(book, str(settings["art"])) if settings.get("art") else None
    focus = tuple(float(v) for v in (settings.get("focus") or (0.5, 0.5)))
    common = {"labels": context.labels, "colors": colors, "title": title, "author": book.author,
              "title_lines": title_lines(title, words.get("title")), "subtitle": meta.get("subtitle", ""),
              "tagline": meta.get("tagline", ""), "line": str(words.get("line") or "")}
    report: dict[str, Any] = {
        "language": language, "template": template.name, "publisher": rules.name,
        "art": ({k: picture[k] for k in ("id", "digest", "width", "height")}
                | {"lettering": picture.get("lettering", ""), "recorded": picture["recorded"]}) if picture else None,
        "words": {"title_lines": common["title_lines"], "line": bool(common["line"]),
                  "back": bool(words.get("back")), "about": bool(words.get("about"))},
    }

    # ------------------------------------------------------------- ebook
    pixels = rules.ebook_pixels
    width, height = EBOOK_SHEET_WIDTH, round(EBOOK_SHEET_WIDTH * pixels[1] / pixels[0], 4)
    scale = width / 6
    margin = round(base_margin * scale, 4)
    placed = {}
    if picture:
        placed = _panel_art(book.root / picture["path"], out / "art-ebook.jpg", (width, height), focus,
                            colors["night"], scrim, 0.0)
    source = env.get_template("cover.tex.j2").render(
        **common, s=scale, margin=margin, sheet={"width": width, "height": height}, back=None, spine=None,
        art="art-ebook.jpg" if picture else "",
        front={"art_width": width, "art_height": height, "text_width": round(width - 2 * margin, 4)},
        at={"corner": _at(width, height), "art": _at(0, 0), "author": _at(width / 2, height - margin),
            "title": _at(width / 2, height - margin - 0.62 * scale), "line": _at(margin, margin),
            "spine": "", "back": ""})
    pdf, _ = _typeset(out, "ebook", source, engine)
    ebook = out / f"{book.id}-{language}-cover-ebook.jpg"
    _raster(pdf, ebook, "jpeg", "-dJPEGQ=93", f"-g{pixels[0]}x{pixels[1]}", "-dPDFFitPage")
    report["ebook"] = {"file": ebook.name, "art": placed, "pixels": list(pixels)}

    # ------------------------------------------------------------- print
    output = ebook
    report["print"] = None
    declared = print_trim(book)
    interior = interior_pages(book, language) if declared else None
    if declared and interior:
        (trim_w, trim_h), paper = declared
        pages, interior_digest = interior
        sheet = wrap((trim_w, trim_h), pages, paper, rules)
        bleed = rules.bleed
        scale = trim_w / 6
        margin = round(base_margin * scale, 4)
        placed = {}
        if picture:
            placed = _panel_art(book.root / picture["path"], out / "art-print.jpg",
                                (trim_w + bleed, sheet.height), focus, colors["night"], scrim,
                                float(template.meta.get("edge_fade", 0)))
        top, centre = bleed + trim_h, sheet.front_left + trim_w / 2
        spine_text = pages >= rules.spine_text_pages
        back_top = top - margin
        source = env.get_template("cover.tex.j2").render(
            **common, s=scale, margin=margin, sheet={"width": sheet.width, "height": sheet.height},
            art="art-print.jpg" if picture else "",
            front={"art_width": round(trim_w + bleed, 4), "art_height": sheet.height,
                   "text_width": round(trim_w - 2 * margin, 4)},
            spine={"text": spine_text, "length": round(trim_h - 2 * margin, 4),
                   "band": round(max(sheet.spine - 2 * rules.spine_text_margin, 0.01), 4)},
            back={"width": round(trim_w - 2 * margin, 4),
                  "text": renderer.document(str(words.get("back") or meta.get("description") or "")),
                  "about": renderer.document(str(words.get("about") or ""))},
            at={"corner": _at(sheet.width, sheet.height), "art": _at(sheet.front_left, 0),
                "author": _at(centre, top - margin), "title": _at(centre, top - margin - 0.62 * scale),
                "line": _at(sheet.front_left + margin, bleed + margin),
                "spine": _at(sheet.spine_left + sheet.spine / 2, sheet.height / 2),
                "back": _at(bleed + margin, back_top)})
        pdf, log = _typeset(out, "print", source, engine)
        output = out / f"{book.id}-{language}-cover-print.pdf"
        pdf.rename(output)
        _raster(output, out / "preview-print.png", "png16m", "-r60")
        measured = re.search(r"KDP-COVER back-text-height=([\d.]+)pt", log)
        back_bottom = round(back_top - float(measured.group(1)) / 72.27, 4) if measured else None
        report["print"] = {"file": output.name, "wrap": asdict(sheet) | {"width": sheet.width, "height": sheet.height},
                           "interior_digest": interior_digest, "spine_text": spine_text, "art": placed,
                           "back_text_bottom": back_bottom, "margin": margin}
    for scrap in (*out.glob("*.aux"), *out.glob("*.log"), out / "ebook.pdf"):
        scrap.unlink(missing_ok=True)
    (out / REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return BuildResult("cover", language, output, template.name, [], {
        "ebook": str(ebook.relative_to(book.root)),
        "print": str(output.relative_to(book.root)) if report["print"] else "",
        "pages": report["print"]["wrap"]["pages"] if report["print"] else None,
        "spine": report["print"]["wrap"]["spine"] if report["print"] else None,
    })


def built_report(book: Book, language: str) -> dict[str, Any]:
    path = build_dir(book, language, "cover") / REPORT
    if not path.is_file():
        raise NotFoundError(f"The {language} cover is not built")
    return json.loads(path.read_text("utf-8"))


def built_ebook_cover(book: Book, language: str) -> Path | None:
    """The built ebook cover, for the ebook to embed when the author supplied none."""

    found = sorted(build_dir(book, language, "cover").glob("*-cover-ebook.jpg"))
    return found[0] if found else None

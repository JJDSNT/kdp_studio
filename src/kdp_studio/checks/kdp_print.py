"""KDP print interior: measured against KDP's published requirements.

Values are taken from the PDF itself (pypdf for boxes, fonts and text;
Ghostscript's bbox device for where ink actually lands). The requirements are
those verified for "A Era dos Agentes" (docs/origin, §11): black-and-white
interior, paperback.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from . import FAIL, INFO, NOT_CHECKED, PASS, WARN, Finding

POINT = 72.0
BLEED = 0.125
MIN_PAGES, MAX_PAGES, SPINE_TEXT_PAGES = 24, 828, 100
#: Inches of spine per page, by paper (KDP, black-and-white).
SPINE_PER_PAGE = {"white": 0.002252, "cream": 0.0025}
#: (up to N pages, minimum inside margin in inches).
GUTTERS = [(150, 0.375), (300, 0.5), (500, 0.625), (700, 0.75), (828, 0.875)]
MIN_OUTSIDE = 0.25


def required_gutter(pages: int) -> float:
    for limit, gutter in GUTTERS:
        if pages <= limit:
            return gutter
    return GUTTERS[-1][1]


def _bboxes(pdf: Path) -> list[tuple[float, float, float, float] | None]:
    run = subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=bbox", str(pdf)],
                         capture_output=True, text=True)
    boxes: list[tuple[float, float, float, float] | None] = []
    for line in run.stderr.splitlines():
        if line.startswith("%%HiResBoundingBox:"):
            x0, y0, x1, y1 = (float(v) for v in line.split()[1:5])
            boxes.append(None if x1 <= x0 or y1 <= y0 else (x0, y0, x1, y1))
    return boxes


def _font_embedded(font) -> bool:
    font = font.get_object()
    descriptor = font.get("/FontDescriptor")
    if descriptor is None and font.get("/DescendantFonts"):
        descriptor = font["/DescendantFonts"][0].get_object().get("/FontDescriptor")
    if descriptor is None:
        return font.get("/Subtype") == "/Type3"
    descriptor = descriptor.get_object()
    return any(key in descriptor for key in ("/FontFile", "/FontFile2", "/FontFile3"))


def check_print(pdf: Path, *, trim: tuple[float, float], bleed: bool, paper: str = "white",
                log: Path | None = None) -> list[Finding]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf))
    pages = reader.pages
    count = len(pages)
    findings: list[Finding] = []
    width, height = trim
    expected = (width + BLEED, height + 2 * BLEED) if bleed else (width, height)

    sizes = {(round(float(p.mediabox.width) / POINT, 3), round(float(p.mediabox.height) / POINT, 3)) for p in pages}
    exact = sizes == {(round(expected[0], 3), round(expected[1], 3))}
    findings.append(Finding("page-size", "Page size", PASS if exact else FAIL,
                            ", ".join(f'{w}" × {h}"' for w, h in sorted(sizes)),
                            f'{expected[0]}" × {expected[1]}"' + (" (trim + bleed)" if bleed else "")))

    findings.append(Finding("page-count", "Page count",
                            PASS if MIN_PAGES <= count <= MAX_PAGES else FAIL, str(count),
                            f"{MIN_PAGES}–{MAX_PAGES}"))
    findings.append(Finding("spine-text", "Text on the spine", PASS if count >= SPINE_TEXT_PAGES else WARN,
                            str(count), f"{SPINE_TEXT_PAGES}+ pages",
                            "" if count >= SPINE_TEXT_PAGES else "KDP prints no spine text below 100 pages"))
    per_page = SPINE_PER_PAGE.get(paper)
    if per_page:
        findings.append(Finding("spine-width", "Spine width for the cover", INFO,
                                f'{count * per_page:.4f}"', f"{count} pages × {per_page}\" ({paper} paper)",
                                "The cover is laid out only after the text is frozen: every page changes this."))

    missing = sorted({str(f.get_object().get("/BaseFont")) for p in pages
                      for f in ((p.get("/Resources") or {}).get("/Font") or {}).values()
                      if not _font_embedded(f)})
    findings.append(Finding("fonts-embedded", "All fonts embedded", PASS if not missing else FAIL,
                            "all embedded" if not missing else ", ".join(missing), "every font embedded"))

    texts = [(p.extract_text() or "").strip() for p in pages]
    folio_only = [i + 1 for i, t in enumerate(texts) if re.fullmatch(r"[\divxlcIVXLC]+", t)]
    findings.append(Finding("blank-folio", "Blank pages carry no page number", PASS if not folio_only else FAIL,
                            "none" if not folio_only else "pages " + ", ".join(map(str, folio_only)),
                            "a blank page has no folio"))

    if shutil.which("gs"):
        findings.extend(_margins(pdf, count, trim, bleed))
    else:
        findings.append(Finding("margins", "Margins and gutter", NOT_CHECKED,
                                detail="Ghostscript is not installed; `kdp doctor` says how"))

    if log and log.is_file():
        text = log.read_text("utf-8", errors="replace")
        over = len(re.findall(r"^Overfull \\[hv]box", text, re.M))
        under = len(re.findall(r"^Underfull \\[hv]box", text, re.M))
        findings.append(Finding("overfull", "Overfull boxes", PASS if not over else FAIL, str(over), "0"))
        findings.append(Finding("underfull", "Underfull boxes", PASS if not under else FAIL, str(under), "0"))
    findings.append(Finding("transparency", "Transparency flattened", NOT_CHECKED,
                            detail="not measured yet"))
    return findings


def _margins(pdf: Path, count: int, trim: tuple[float, float], bleed: bool) -> list[Finding]:
    boxes = _bboxes(pdf)
    width, height = trim
    offset_y = BLEED if bleed else 0.0
    gutter_needed = required_gutter(count)
    worst_gutter = worst_outside = worst_top = worst_bottom = 99.0
    where: dict[str, int] = {}
    full_bleed: list[int] = []
    for index, box in enumerate(boxes):
        if box is None:
            continue
        number = index + 1
        x0, y0, x1, y1 = (v / POINT for v in box)
        recto = number % 2 == 1
        # In the bleed file the trimmed page sits at the spine edge: left on a
        # recto, right on a verso, with the bleed on the outer edge.
        left = 0.0 if recto or not bleed else BLEED
        tx0, tx1 = x0 - left, x1 - left
        ty0, ty1 = y0 - offset_y, y1 - offset_y
        if tx0 <= 0.01 and tx1 >= width - 0.01 and ty0 <= 0.01 and ty1 >= height - 0.01:
            full_bleed.append(number)
            continue
        inside, outside = (tx0, width - tx1) if recto else (width - tx1, tx0)
        for name, value in (("gutter", inside), ("outside", outside), ("top", height - ty1), ("bottom", ty0)):
            current = {"gutter": worst_gutter, "outside": worst_outside, "top": worst_top, "bottom": worst_bottom}[name]
            if value < current:
                where[name] = number
                if name == "gutter":
                    worst_gutter = value
                elif name == "outside":
                    worst_outside = value
                elif name == "top":
                    worst_top = value
                else:
                    worst_bottom = value
    findings = [
        Finding("gutter", "Inside margin (gutter)", PASS if worst_gutter >= gutter_needed else FAIL,
                f'{worst_gutter:.3f}" (page {where.get("gutter")})', f'≥ {gutter_needed}" for {count} pages'),
        Finding("outside-margin", "Outside margin", PASS if worst_outside >= MIN_OUTSIDE else FAIL,
                f'{worst_outside:.3f}" (page {where.get("outside")})', f'≥ {MIN_OUTSIDE}"'),
        Finding("top-margin", "Top margin", PASS if worst_top >= MIN_OUTSIDE else FAIL,
                f'{worst_top:.3f}" (page {where.get("top")})', f'≥ {MIN_OUTSIDE}"'),
        Finding("bottom-margin", "Bottom margin", PASS if worst_bottom >= MIN_OUTSIDE else FAIL,
                f'{worst_bottom:.3f}" (page {where.get("bottom")})', f'≥ {MIN_OUTSIDE}"'),
    ]
    if full_bleed:
        findings.append(Finding("full-bleed", "Full-bleed pages", PASS if bleed else FAIL,
                                f"{len(full_bleed)} (pages {', '.join(map(str, full_bleed))})",
                                "only in a file with bleed",
                                "Ink to the edge; margins are not measured on these pages."))
    return findings

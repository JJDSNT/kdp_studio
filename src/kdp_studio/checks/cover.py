"""The cover, measured against the publisher's profile and the book as it is now.

Values are taken from the built files -- the ebook cover's pixels, the wrap's
page box and fonts, the height of the back-cover text as typeset -- and from
the interior the wrap was sized for. A wrap built for another page count is
a failure, however good it looks: every page changes the spine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..book import Book
from . import FAIL, INFO, NOT_CHECKED, PASS, WARN, Finding
from .kdp_print import POINT, _font_embedded


def check_cover(book: Book, language: str, folder: Path, report: dict[str, Any]) -> list[Finding]:
    from PIL import Image
    from pypdf import PdfReader

    from ..cover import interior_pages, print_trim, publisher, wrap
    from ..gates import gate_status

    rules = publisher(book)
    findings: list[Finding] = []

    # ------------------------------------------------------------- ebook
    ebook = folder / report["ebook"]["file"]
    with Image.open(ebook) as image:
        size, mode = image.size, image.mode
    wanted = rules.ebook_pixels
    megabytes = ebook.stat().st_size / 1_000_000
    findings.append(Finding("ebook-pixels", "Ebook cover size", PASS if size == wanted else FAIL,
                            f"{size[0]} × {size[1]} px", f"{wanted[0]} × {wanted[1]} px ({rules.title})"))
    findings.append(Finding("ebook-colour", "Ebook cover colour", PASS if mode == "RGB" else FAIL, mode, "RGB"))
    findings.append(Finding("ebook-weight", "Ebook cover file", PASS if megabytes <= rules.ebook_megabytes else FAIL,
                            f"{megabytes:.1f} MB", f"at most {rules.ebook_megabytes:g} MB"))

    # --------------------------------------------------------------- art
    art = report.get("art")
    if art is None:
        findings.append(Finding("art", "Cover art", INFO, "none: a typographic cover", ""))
    else:
        baked = art.get("lettering") == "baked"
        findings.append(Finding(
            "art-lettering", "No lettering in the art", WARN if baked or not art["recorded"] else PASS,
            "baked in" if baked else "declared none" if art["recorded"] else "not recorded",
            "none: every word is set by the template",
            "Words drawn by an image model cannot be corrected or translated, and the template sets them again."
            if baked else "" if art["recorded"] else f"`kdp art add` records how art/{art['id']} was made."))
        used = report["ebook"]["art"]["pixels"]
        findings.append(Finding("art-ebook", "Art behind the ebook cover", PASS if used[0] >= wanted[0] else WARN,
                                f"{used[0]} × {used[1]} px used", f"at least {wanted[0]} px wide",
                                "" if used[0] >= wanted[0] else "the picture is enlarged to fill the cover"))

    # ------------------------------------------------------------- print
    declared = print_trim(book)
    if declared is None:
        return findings
    printed = report.get("print")
    interior = interior_pages(book, language)
    if printed is None or interior is None:
        findings.append(Finding("wrap", "Print wrap", NOT_CHECKED, "not built",
                                "", "The wrap needs the page count: build the print interior, then the cover."))
        return findings
    (trim_w, trim_h), paper = declared
    pages, interior_digest = interior
    sheet = wrap((trim_w, trim_h), pages, paper, rules)
    built = printed["wrap"]
    findings.append(Finding(
        "wrap-pages", "Wrap built for the interior as it is", PASS if built["pages"] == pages else FAIL,
        f"built for {built['pages']} pages", f"{pages} pages now",
        "" if built["pages"] == pages else "Every page changes the spine: build the cover again."))
    reader = PdfReader(str(folder / printed["file"]))
    box = reader.pages[0].mediabox
    measured = (float(box.width) / POINT, float(box.height) / POINT)
    exact = abs(measured[0] - sheet.width) < 0.01 and abs(measured[1] - sheet.height) < 0.01
    findings.append(Finding(
        "wrap-size", "Wrap size", PASS if exact and len(reader.pages) == 1 else FAIL,
        f'{measured[0]:.3f}" × {measured[1]:.3f}", {len(reader.pages)} page(s)',
        f'{sheet.width:.3f}" × {sheet.height:.3f}" (bleed + back + spine + front + bleed), 1 page'))
    findings.append(Finding(
        "spine", "Spine", INFO, f'{sheet.spine:.4f}"',
        f"{rules.spine_base:g} + {pages} pages × {rules.spine_per_page[paper]}\" ({paper} paper)"))
    has_text = bool(printed["spine_text"])
    allowed = pages >= rules.spine_text_pages
    findings.append(Finding("spine-text", "Text on the spine", PASS if has_text == allowed else FAIL,
                            "set" if has_text else "none", f"only from {rules.spine_text_pages} pages"))
    missing = sorted({str(font.get_object().get("/BaseFont", "?")) for page in reader.pages
                      for font in ((page.get("/Resources") or {}).get("/Font") or {}).values()
                      if not _font_embedded(font)})
    findings.append(Finding("wrap-fonts", "All fonts embedded", PASS if not missing else FAIL,
                            ", ".join(missing) or "all embedded", "every font embedded"))
    bottom = printed.get("back_text_bottom")
    barcode_top = sheet.barcode[3]
    if bottom is None:
        findings.append(Finding("barcode", "Back-cover text clear of the barcode", NOT_CHECKED,
                                "", "", "The template did not report the height of the back-cover text."))
    else:
        findings.append(Finding(
            "barcode", "Back-cover text clear of the barcode", PASS if bottom >= barcode_top else FAIL,
            f'text ends {bottom - rules.bleed:.2f}" above the foot',
            f'above {barcode_top - rules.bleed:.2f}" (a {rules.barcode_size[0]:g}" × {rules.barcode_size[1]:g}" '
            "barcode goes there)", "" if bottom >= barcode_top else "Shorten the back-cover copy."))
    margin = printed.get("margin", 0)
    findings.append(Finding("safe", "Words inside the safe area", PASS if margin >= rules.safe else FAIL,
                            f'{margin:.3f}" from the trim, by the template', f'at least {rules.safe:g}"'))
    if art is not None:
        dpi = printed["art"]["dpi"]
        findings.append(Finding("art-print", "Art resolution on the printed cover",
                                PASS if dpi >= rules.dpi else WARN, f"{dpi:.0f} dpi", f"{rules.dpi} dpi",
                                "" if dpi >= rules.dpi else "It will print soft: use a larger picture."))
    frozen = [g for g in gate_status(book) if g["kind"] == "freeze" and g["subject"] == language
              and g["state"] == "approved" and not g["changed_since"]]
    findings.append(Finding("frozen", "Text frozen before the cover", PASS if frozen else WARN,
                            "frozen" if frozen else "no freeze gate approved for the text as it is",
                            "freeze, count the pages, then the cover",
                            "" if frozen else "Until the text is frozen this wrap is a proof: its spine may move."))
    findings.append(Finding("transparency", "Transparency flattened", INFO, "none by construction",
                            "", "The scrim over the art is baked into the picture; the words are opaque."))
    return findings

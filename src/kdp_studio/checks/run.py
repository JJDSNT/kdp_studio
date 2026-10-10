"""Running the checks of an edition and keeping the report beside the build."""

from __future__ import annotations

import json
from typing import Any

from .. import catalog
from ..book import Book
from ..build import build_dir, edition_settings
from ..errors import NotFoundError
from . import summary
from .epub import check_epub
from .kdp_print import check_print


def run_checks(book: Book, language: str, edition: str) -> dict[str, Any]:
    out = build_dir(book, language, edition)
    if edition == "print":
        pdfs = sorted(out.glob("*.pdf"))
        if not pdfs:
            raise NotFoundError(f"The {language} print edition is not built")
        settings = edition_settings(book, "print")
        template = catalog.get("print", settings["template"], book.root)
        paper = template.meta["trims"][settings.get("trim", "6x9")]["paper"]
        trim = tuple(float(v.removesuffix("in")) for v in paper)
        target = pdfs[0]
        findings = check_print(target, trim=trim, bleed=target.stem.endswith("-bleed"),
                               paper=settings.get("paper", "white"), log=out / "book.log",
                               ink=str(settings.get("ink", "color")))
    elif edition == "cover":
        from ..cover import built_report
        from .cover import check_cover

        built = built_report(book, language)
        target = out / (built["print"] or built["ebook"])["file"]
        findings = check_cover(book, language, out, built)
        report = {"edition": edition, "language": language, "target": str(target.relative_to(book.root)),
                  "findings": [f.public_dict() for f in findings], "summary": summary(findings)}
        (out / "check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
    else:
        epubs = sorted(out.glob("*.epub"))
        if not epubs:
            raise NotFoundError(f"The {language} ebook is not built")
        target = epubs[0]
        findings = check_epub(target)
    report = {"edition": edition, "language": language, "target": str(target.relative_to(book.root)),
              "findings": [f.public_dict() for f in findings], "summary": summary(findings)}
    (out / "check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def last_report(book: Book, language: str, edition: str) -> dict[str, Any] | None:
    path = build_dir(book, language, edition) / "check.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text("utf-8"))
    return data if isinstance(data, dict) else None

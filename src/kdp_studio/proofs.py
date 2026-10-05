"""Page proofs: the print interior rasterised, to be looked at.

A log without errors once hid a chapter label that vanished from the page. The
only check for that is to look, so every build can be seen page by page.
Images go to ``builds/<language>/print/proofs/`` and are regenerated when the
PDF is newer.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .book import Book
from .build import build_dir
from .errors import NotFoundError, ToolUnavailableError

RESOLUTION = 72


def interior(book: Book, language: str) -> Path:
    pdfs = sorted(build_dir(book, language, "print").glob("*.pdf"))
    if not pdfs:
        raise NotFoundError(f"The {language} print edition is not built")
    return pdfs[0]


def proofs(book: Book, language: str) -> list[Path]:
    pdf = interior(book, language)
    folder = pdf.parent / "proofs"
    existing = sorted(folder.glob("p*.png"))
    if existing and existing[0].stat().st_mtime >= pdf.stat().st_mtime:
        return existing
    if not shutil.which("gs"):
        raise ToolUnavailableError("Ghostscript is needed to look at pages; `kdp doctor` says how")
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir()
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m", f"-r{RESOLUTION}",
                    "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4", f"-sOutputFile={folder}/p%03d.png", str(pdf)],
                   check=True, capture_output=True)
    return sorted(folder.glob("p*.png"))

"""What works on this machine, and the exact line that fixes what does not.

A capability reported as working when nothing calls it would be a lie told by
the one command whose whole job is to tell the truth, so tools KDP Studio can
detect but does not use yet are listed apart.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass

OK, MISSING = "ok", "missing"


@dataclass(frozen=True)
class Capability:
    name: str
    enables: str
    status: str
    detail: str = ""
    remedy: str = ""
    wired: bool = True


def _module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _font(name: str) -> bool:
    if not shutil.which("luaotfload-tool"):
        return False
    run = subprocess.run(["luaotfload-tool", "--find", name], capture_output=True, text=True)
    return run.returncode == 0


def capabilities() -> list[Capability]:
    version = ".".join(map(str, sys.version_info[:3]))
    caps = [
        Capability("Python 3.12+", "everything", OK if sys.version_info[:2] >= (3, 12) else MISSING,
                   f"running {version}", "Install Python 3.12 or newer."),
        Capability("Book format", "reading a book, checking it, deciding gates",
                   OK if all(_module(m) for m in ("yaml", "markdown_it", "mdit_py_plugins", "jinja2")) else MISSING,
                   remedy="uv sync"),
        Capability("Build extra", "QR codes, measuring PDFs",
                   OK if all(_module(m) for m in ("qrcode", "PIL", "pypdf")) else MISSING,
                   remedy="uv sync --extra build"),
        Capability("LuaLaTeX", "the print interior", OK if shutil.which("lualatex") else MISSING,
                   remedy="sudo apt install texlive-luatex texlive-latex-extra texlive-fonts-extra"),
        Capability("Book fonts", "the Nocturne template (Pagella, Adventor, DejaVu Sans Mono)",
                   OK if all(_font(f) for f in ("TeX Gyre Pagella", "TeX Gyre Adventor", "DejaVu Sans Mono"))
                   else MISSING, remedy="sudo apt install tex-gyre fonts-dejavu"),
        Capability("Ghostscript", "measuring margins, rasterising pages to look at them",
                   OK if shutil.which("gs") else MISSING, remedy="sudo apt install ghostscript"),
        Capability("Git", "a history of every decision in the book", OK if shutil.which("git") else MISSING,
                   remedy="sudo apt install git"),
        Capability("EPUBCheck", "the reference EPUB validator", OK if shutil.which("epubcheck") else MISSING,
                   remedy="sudo apt install epubcheck"),
    ]
    return caps


def report() -> str:
    lines = []
    for cap in capabilities():
        mark = "ok     " if cap.status == OK else "missing"
        line = f"  {mark}  {cap.name:16} {cap.enables}"
        if cap.detail:
            line += f"  ({cap.detail})"
        lines.append(line)
        if cap.status != OK and cap.remedy:
            lines.append(f"           -> {cap.remedy}")
    missing = [c for c in capabilities() if c.status != OK]
    lines.append("")
    lines.append("Ready, with everything installed." if not missing else
                 f"{len(missing)} capability(ies) missing; each line above says how to add it.")
    return "\n".join(lines)

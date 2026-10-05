"""EPUB structure, and the reader traps from docs/origin §10.

This is not EPUBCheck. When EPUBCheck is installed it also runs, and its
verdict is reported as its own finding.
"""

from __future__ import annotations

import json
import re
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .. import tools
from ..errors import ToolUnavailableError
from . import FAIL, NOT_CHECKED, PASS, WARN, Finding

OPF = "{http://www.idpf.org/2007/opf}"
DC = "{http://purl.org/dc/elements/1.1/}"
#: Kindle's recommended ebook cover, in pixels.
KINDLE_COVER = (1600, 2560)


def check_epub(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        first = archive.infolist()[0]
        mimetype_ok = (first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
                       and archive.read("mimetype") == b"application/epub+zip")
        findings.append(Finding("mimetype", "mimetype first and uncompressed", PASS if mimetype_ok else FAIL))

        malformed = []
        for name in names:
            if name.endswith((".xhtml", ".opf", ".ncx", ".xml")):
                try:
                    ET.fromstring(archive.read(name))
                except ET.ParseError as error:
                    malformed.append(f"{name}: {error}")
        findings.append(Finding("well-formed", "Every XML document well-formed", PASS if not malformed else FAIL,
                                "all" if not malformed else "; ".join(malformed[:3])))

        container = ET.fromstring(archive.read("META-INF/container.xml"))
        opf_path = next(e.attrib["full-path"] for e in container.iter() if e.tag.endswith("rootfile"))
        base = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""
        opf = ET.fromstring(archive.read(opf_path))
        manifest = {item.attrib["id"]: item.attrib for item in opf.iter(f"{OPF}item")}
        spine = [ref.attrib["idref"] for ref in opf.iter(f"{OPF}itemref")]

        nav = [i for i, item in manifest.items() if "nav" in item.get("properties", "").split()]
        findings.append(Finding("nav-in-spine", "Contents page in the reading order",
                                PASS if nav and nav[0] in spine else FAIL,
                                detail="A nav document outside the spine is never shown by many readers."))
        ncx = any(item.get("media-type") == "application/x-dtbncx+xml" for item in manifest.values())
        findings.append(Finding("ncx", "NCX for older readers", PASS if ncx else FAIL))

        missing = [item["href"] for item in manifest.values() if base + item["href"] not in names]
        findings.append(Finding("manifest-files", "Every manifest item present", PASS if not missing else FAIL,
                                "all" if not missing else ", ".join(missing[:5])))

        titles = list(opf.iter(f"{DC}title"))
        findings.append(Finding("separate-titles", "Title and subtitle in separate dc:title",
                                PASS if len(titles) >= 1 and all(":" not in (t.text or "") for t in titles) else WARN,
                                f"{len(titles)} dc:title"))

        css = "".join(archive.read(n).decode("utf-8") for n in names if n.endswith(".css"))
        body_background = re.search(r"(^|[\s,}])body\s*\{[^}]*background", css)
        findings.append(Finding("body-background", "No background forced on body",
                                PASS if not body_background else FAIL,
                                detail="It breaks dark mode and draws a box inside the reader's page."))

        cover = next((item for item in manifest.values() if "cover-image" in item.get("properties", "")), None)
        if cover is None:
            findings.append(Finding("cover", "Ebook cover", WARN, "none",
                                    f"{KINDLE_COVER[0]} × {KINDLE_COVER[1]} px recommended",
                                    "Add cover/<language>/ebook.jpg; KDP also takes the cover separately."))
        else:
            findings.append(_cover_size(archive.read(base + cover["href"])))

    findings.append(_epubcheck(path))
    return findings


def _epubcheck(path: Path) -> Finding:
    """The reference validator, when installed (`kdp tools install epubcheck`)."""

    try:
        command = tools.command("epubcheck")
    except ToolUnavailableError as error:
        return Finding("epubcheck", "EPUBCheck", NOT_CHECKED, detail=error.message)
    run = subprocess.run([*command, "--json", "-", str(path)], capture_output=True, text=True)
    try:
        report = json.loads(run.stdout)
    except ValueError:
        tail = (run.stdout + run.stderr).strip().splitlines()[-1:] or [""]
        return Finding("epubcheck", "EPUBCheck", FAIL if run.returncode else PASS, detail=tail[0])
    messages = report.get("messages") or []
    severe = [m for m in messages if m.get("severity") in ("FATAL", "ERROR")]
    warnings = [m for m in messages if m.get("severity") == "WARNING"]
    version = (report.get("checker") or {}).get("checkerVersion", "")
    first = severe[0] if severe else (warnings[0] if warnings else None)
    detail = f"{first['ID']}: {first['message']}" if first else ""
    return Finding("epubcheck", f"EPUBCheck {version}".strip(), FAIL if severe else (WARN if warnings else PASS),
                   f"{len(severe)} error(s), {len(warnings)} warning(s)", "0 errors", detail)


def _cover_size(data: bytes) -> Finding:
    try:
        from io import BytesIO

        from PIL import Image

        width, height = Image.open(BytesIO(data)).size
    except Exception:  # noqa: BLE001 - any failure means we could not measure
        return Finding("cover", "Ebook cover size", NOT_CHECKED, detail="could not read the image")
    ok = (width, height) >= KINDLE_COVER and abs(height / width - 1.6) < 0.02
    return Finding("cover", "Ebook cover size", PASS if ok else WARN, f"{width} × {height} px",
                   f"{KINDLE_COVER[0]} × {KINDLE_COVER[1]} px (1:1.6)")

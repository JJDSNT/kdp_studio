"""Open tools KDP Studio uses as resources, installed for this user only.

Mature open tools do jobs better than anything rewritten here: Vale lints
prose against YAML rules, LanguageTool checks grammar and style (Brazilian
Portuguese included), EPUBCheck is the reference EPUB validator. `kdp tools
install <name>` fetches a pinned release from its official source into
`~/.local/share/kdp-studio/tools/`, verifies its checksum, and touches nothing
else on the machine. Removing that directory removes them.

A tool already on PATH is used as it is.
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import stat
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .errors import NotFoundError, ToolUnavailableError, ValidationError


def home() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "kdp-studio" / "tools"


@dataclass(frozen=True)
class Tool:
    name: str
    version: str
    url: str
    sha256: str
    #: The executable or jar, relative to the tool's directory.
    entry: str
    license: str
    enables: str
    needs_java: bool = False


TOOLS = {
    "vale": Tool(
        "vale", "3.24.0",
        "https://github.com/vale-cli/vale/releases/download/v3.24.0/vale_3.24.0_Linux_64-bit.tar.gz",
        "", "vale", "MIT", "prose linting with Vale rules and styles"),
    "epubcheck": Tool(
        "epubcheck", "5.4.0",
        "https://github.com/w3c/epubcheck/releases/download/v5.4.0/epubcheck-5.4.0.zip",
        "33350c61038e71dfb3d45a76aed04bf5481e6d5500cb780f6e98db8bbd15a28c",
        "epubcheck-5.4.0/epubcheck.jar", "BSD-3-Clause", "the reference EPUB validator", needs_java=True),
    "languagetool": Tool(
        "languagetool", "6.6",
        "https://languagetool.org/download/LanguageTool-6.6.zip",
        # No published checksum: pinned at the first verified download (2026-10-04),
        # so a later install that differs is refused.
        "53600506b399bb5ffe1e4c8dec794fd378212f14aaf38ccef9b6f89314d11631",
        "LanguageTool-6.6/languagetool-server.jar", "LGPL-2.1",
        "grammar, spelling and style, Brazilian Portuguese included", needs_java=True),
}

#: Checksums published beside a release, when the project publishes them.
CHECKSUM_FILES = {
    "vale": "https://github.com/vale-cli/vale/releases/download/v3.24.0/vale_3.24.0_checksums.txt",
}


def location(name: str) -> Path | None:
    """Where the tool is: on PATH, or installed by KDP Studio; None if absent."""

    tool = TOOLS[name]
    if not tool.needs_java and shutil.which(name):
        return Path(shutil.which(name))
    path = home() / name / tool.entry
    return path if path.is_file() else None


def command(name: str) -> list[str]:
    """How to run the tool, or raise with the line that installs it."""

    found = location(name)
    if found is None:
        raise ToolUnavailableError(f"{name} is not installed: kdp tools install {name}")
    if TOOLS[name].needs_java:
        if not shutil.which("java"):
            raise ToolUnavailableError(f"{name} needs Java 17+: sudo apt install default-jre")
        return ["java", "-jar", str(found)]
    return [str(found)]


def _fetch(url: str, timeout: float) -> bytes:
    # Some download hosts refuse Python's default user agent; say who asks.
    request = urllib.request.Request(url, headers={"User-Agent": "kdp-studio (+https://github.com/JJDSNT/kdp_studio)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except OSError as error:
        raise ToolUnavailableError(f"Could not download {url}: {error}") from error


def _expected_sha256(tool: Tool) -> str:
    if tool.sha256:
        return tool.sha256
    listing = CHECKSUM_FILES.get(tool.name)
    if not listing:
        return ""
    for line in _fetch(listing, 60).decode().splitlines():
        digest, _, filename = line.partition("  ")
        if filename.strip() == tool.url.rsplit("/", 1)[-1]:
            return digest.strip()
    raise ValidationError(f"No checksum for {tool.name} in {listing}")


def install(name: str) -> Path:
    if name not in TOOLS:
        raise NotFoundError(f"Unknown tool {name!r}", tools=sorted(TOOLS))
    tool = TOOLS[name]
    target = home() / name
    data = _fetch(tool.url, 900)
    digest = hashlib.sha256(data).hexdigest()
    expected = _expected_sha256(tool)
    if expected and digest != expected:
        raise ValidationError(f"{name}: checksum mismatch; nothing was installed", expected=expected, got=digest)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    if tool.url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            archive.extractall(target)
    else:
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            archive.extractall(target, filter="data")
    entry = target / tool.entry
    if not tool.needs_java:
        entry.chmod(entry.stat().st_mode | stat.S_IXUSR)
    (target / "INSTALLED").write_text(f"{tool.name} {tool.version}\n{tool.url}\nsha256 {digest}\n"
                                      f"verified {'yes' if expected else 'no published checksum'}\n")
    return entry

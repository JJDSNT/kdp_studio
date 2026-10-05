"""Open linters as engines of the style report: Vale and LanguageTool.

The catalogue (style.py) says what the book's writing must follow; these
engines are resources that check more than KDP Studio should rewrite itself.
Both receive only the reader's text -- never prompts, code or editorial
comments -- one paragraph per line group, and every alert comes back mapped to
the section's file and line.

A book turns them on in its `style.yaml`:

    vale:
      packages: [write-good]     # Vale packages, synced on first use
      styles: vale/              # the book's own Vale styles (optional)
    languagetool:
      disabled_rules: [WHITESPACE_RULE]
      level: picky               # default | picky
    words: [WSL, Codex]          # names and terms of the book, never misspellings
"""

from __future__ import annotations

import json
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from . import tools
from .book import Book, Section
from .errors import ToolUnavailableError
from .style import Finding, Unit, section_line, units


def _document(section: Section) -> tuple[str, list[Unit]]:
    found = list(units(section.body))
    return "\n\n".join(u.text for u in found) + "\n", found


def _line_map(found: list[Unit]) -> list[Unit]:
    """For each line of the generated document, the unit it came from."""

    mapping: list[Unit] = []
    for unit in found:
        mapping.extend([unit] * (unit.text.count("\n") + 1))
        mapping.append(unit)  # the blank separator line
    return mapping


# ------------------------------------------------------------------ Vale

def run_vale(book: Book, language: str, sections: list[Section], settings: dict[str, Any]) -> list[Finding]:
    command = tools.command("vale")
    with tempfile.TemporaryDirectory(prefix="kdp-vale-") as tmp:
        work = Path(tmp)
        styles = settings.get("styles")
        styles_path = (book.root / styles).resolve() if styles else work / "styles"
        styles_path.mkdir(parents=True, exist_ok=True)
        packages = list(settings.get("packages") or [])
        own = sorted(p.name for p in styles_path.iterdir() if p.is_dir()) if styles else []
        # Vale's own base style spells in English: only for English books.
        base = ["Vale"] if language.startswith("en") else []
        based = ", ".join([*base, *[p.rsplit("/", 1)[-1].removesuffix(".zip") for p in packages], *own])
        (work / ".vale.ini").write_text(
            f"StylesPath = {styles_path}\nMinAlertLevel = {settings.get('min_level', 'suggestion')}\n"
            + (f"Packages = {', '.join(packages)}\n" if packages else "")
            + f"\n[*.md]\nBasedOnStyles = {based}\n", encoding="utf-8")
        if packages:
            subprocess.run([*command, "--config", str(work / ".vale.ini"), "sync"], cwd=work,
                           capture_output=True, text=True)
        if not based:
            return []
        files: dict[str, tuple[Section, list[Unit]]] = {}
        for section in sections:
            text, found = _document(section)
            (work / f"{section.id}.md").write_text(text, encoding="utf-8")
            files[f"{section.id}.md"] = (section, found)
        run = subprocess.run([*command, "--config", str(work / ".vale.ini"), "--output=JSON", "--no-exit",
                              *sorted(files)], cwd=work, capture_output=True, text=True)
        try:
            report = json.loads(run.stdout or "{}")
        except ValueError as error:
            raise ToolUnavailableError(f"Vale did not answer in JSON: {run.stderr.strip()[:300]}") from error
    out = []
    for name, alerts in report.items():
        section, found = files[Path(name).name]
        mapping = _line_map(found)
        for alert in alerts:
            unit = mapping[min(alert["Line"] - 1, len(mapping) - 1)] if mapping else None
            line = section_line(section, unit) if unit else 0
            out.append(Finding(f"vale:{alert['Check']}", section.id, line,
                               (unit.text[:200] if unit else ""), alert.get("Match", ""), alert.get("Message", "")))
    return out


# ----------------------------------------------------------- LanguageTool

class LanguageToolServer:
    """A local LanguageTool server for the length of one report. Nothing leaves the machine."""

    def __init__(self) -> None:
        self.port = 0
        self.process: subprocess.Popen | None = None

    def __enter__(self) -> "LanguageToolServer":
        command = tools.command("languagetool")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        jar = command[-1]
        self.process = subprocess.Popen(["java", "-cp", jar, "org.languagetool.server.HTTPServer",
                                         "--port", str(self.port)], stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/v2/languages", timeout=2).read()
                return self
            except OSError:
                time.sleep(0.5)
        self.__exit__()
        raise ToolUnavailableError("LanguageTool did not start within a minute")

    def __exit__(self, *exc) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=10)

    def check(self, text: str, language: str, settings: dict[str, Any]) -> list[dict[str, Any]]:
        fields = {"text": text, "language": language}
        if settings.get("disabled_rules"):
            fields["disabledRules"] = ",".join(settings["disabled_rules"])
        if settings.get("level"):
            fields["level"] = settings["level"]
        data = urllib.parse.urlencode(fields).encode()
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/v2/check", data=data, timeout=120) as response:
            return json.loads(response.read())["matches"]


def run_languagetool(book: Book, language: str, sections: list[Section], settings: dict[str, Any]) -> list[Finding]:
    out = []
    with LanguageToolServer() as server:
        for section in sections:
            text, found = _document(section)
            # Offsets back to units: each unit starts after the previous one and a blank line.
            starts, position = [], 0
            for unit in found:
                starts.append(position)
                position += len(unit.text) + 2
            for match in server.check(text, language, settings):
                offset = match["offset"]
                index = max(i for i, start in enumerate(starts) if start <= offset) if starts else 0
                unit = found[index]
                local = offset - starts[index]
                rule = match["rule"]
                out.append(Finding(f"lt:{rule['id']}", section.id, section_line(section, unit),
                                   unit.text[max(0, local - 60):local + match["length"] + 60],
                                   unit.text[local:local + match["length"]],
                                   match.get("message", "") + (
                                       f" → {', '.join(r['value'] for r in match['replacements'][:3])}"
                                       if match.get("replacements") else "")))
    return out

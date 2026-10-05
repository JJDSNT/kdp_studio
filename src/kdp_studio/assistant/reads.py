"""What the assistant may look up. Reads change nothing."""

from __future__ import annotations

from typing import Any, Callable

from ..checks.run import last_report
from ..server import Studio
from ..versions import list_versions, version_report


def overview(studio: Studio) -> str:
    data = studio.overview()
    lines = [f"Book {data['id']} by {data['author']}; source language {data['source_language']}; "
             f"languages {', '.join(data['languages'])}; state revision {data['revision']}."]
    for language, info in data["languages"].items():
        lines.append(f"[{language}] {info['title']} — {info['subtitle']}")
        for entry in info["contents"]:
            sections = entry["sections"] if entry["type"] == "part" else [entry]
            if entry["type"] == "part":
                label = f"Part {entry['number']}" if entry["kind"] == "part" else entry["kind"].title()
                lines.append(f"  {label}: {entry['title']}")
            for s in sections:
                number = f"ch. {s['number']}" if s["number"] else s["kind"]
                extra = f", {s['candidates']} candidate version(s)" if s["candidates"] else ""
                lines.append(f"    - {s['id']} ({number}) {s['title']} — {s['words']} words{extra}")
    waiting = [g for g in data["gates"] if g["state"] == "waiting"]
    decided = [g for g in data["gates"] if g["state"] != "waiting"]
    lines.append(f"Gates: {len(waiting)} waiting, {len(decided)} decided.")
    for gate in data["gates"]:
        changed = " (files changed since)" if gate["changed_since"] else ""
        lines.append(f"  - {gate['id']} {gate['kind']} {gate['subject']}: {gate['state']}{changed}")
    return "\n".join(lines)


def _section(studio: Studio, args: dict[str, Any]) -> str:
    data = studio.section(args["language"], args["section"])
    return f"Section {data['section']} ({data['language']}), digest {data['digest'][:12]}:\n\n{data['text']}"


def _versions(studio: Studio, args: dict[str, Any]) -> str:
    found = list_versions(studio.book, args.get("language"), args.get("section"))
    if not found:
        return "No versions."
    return "\n".join(f"- {v['id']} of {v['section']} ({v['language']}): {v['state']}, scope {v['scope']}, "
                     f"by {v['proposed_by']['id']} — {v['rationale']}" for v in found)


def _version(studio: Studio, args: dict[str, Any]) -> str:
    report = version_report(studio.book, args["version"])
    fidelity = report["fidelity"]
    changes = sum(1 for segment in report["diff"] if segment["op"] != "equal")
    return (f"Version {report['id']} of {report['section']}: {report['state']}, scope {report['scope']}; "
            f"{changes} changed passage(s); facts added {fidelity['facts_added']}, removed "
            f"{fidelity['facts_removed']}; violations {report['violations'] or 'none'}; "
            f"applies to the current text: {report['base_is_current']}.")


def _checks(studio: Studio, args: dict[str, Any]) -> str:
    report = last_report(studio.book, args.get("language") or studio.book.source_language,
                         args.get("edition", "print"))
    if not report:
        return "No check has run for this edition yet."
    lines = [f"{report['edition']} [{report['language']}] {report['target']}: {report['summary']}"]
    lines += [f"- {f['verdict']}: {f['item']} {f['measured']} (required {f['required']})"
              for f in report["findings"]]
    return "\n".join(lines)


#: name -> (what it returns, what it needs, how)
READS: dict[str, tuple[str, str, Callable[[Studio, dict[str, Any]], str]]] = {
    "book": ("the structure, words per section, candidate versions and gates", "", lambda s, a: overview(s)),
    "section": ("a section's full Markdown text", "language, section", _section),
    "intentions": ("intentions.md, the author's intention", "", lambda s, a: s.document("intentions.md")["text"]),
    "documents": ("the list of editorial documents", "", lambda s, a: "\n".join(s.documents())),
    "document": ("one editorial document", "path", lambda s, a: s.document(a["path"])["text"]),
    "versions": ("candidate and decided versions", "language and section, optional", _versions),
    "version": ("one version's fidelity report", "version", _version),
    "checks": ("the last measured checks of an edition", "edition (print|ebook), language", _checks),
}


def read(studio: Studio, name: str, args: dict[str, Any]) -> str:
    if name not in READS:
        return f"(no read named {name!r})"
    try:
        text = READS[name][2](studio, args)
    except KeyError as missing:
        return f"(this read needs {missing.args[0]!r})"
    except Exception as error:  # noqa: BLE001 - the answer can still say what failed
        return f"(could not read: {getattr(error, 'message', error)})"
    return text if len(text) < 60000 else text[:60000] + "\n(truncated)"

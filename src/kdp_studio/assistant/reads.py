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
                plan = f" [covers: {s['synopsis']}]" if s.get("synopsis") else ""
                extra = f", {s['candidates']} candidate version(s)" if s["candidates"] else ""
                review = s.get("review")
                if review:
                    extra += f", review {review['state']}" + (" but changed since" if review["changed_since"] else "")
                elif language == data["source_language"]:
                    extra += ", not reviewed"
                lines.append(f"    - {s['id']} ({number}) {s['title']} — {s['words']} words{extra}{plan}")
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


def _style(studio: Studio, args: dict[str, Any]) -> str:
    from ..style import check_style

    section = args.get("section")
    report = check_style(studio.book, args.get("language") or studio.book.source_language,
                         [section] if section else None, engines=False).public_dict()
    lines = [f"Counts: {report['counts'] or 'none'}"]
    lines += [f"- [{f['practice']}] {f['section']}:{f['line']} “{f['match']}” — {f['excerpt'][:140]}"
              for f in report["findings"][:80]]
    lines.append("Not checked by code (depends on a reader): "
                 + "; ".join(u["rule"] for u in report["coverage"]["unenforced"]))
    return "\n".join(lines)


def _jobs(studio: Studio, args: dict[str, Any]) -> str:
    from ..jobs import list_jobs

    found = list_jobs(studio.book)[:10]
    lines = [f"- {j['id']} {j['kind']} {j['payload']}: {j['state']}"
             + (f" → {j['result']}" if j.get("result") else "")
             + (f" ({j['error']})" if j.get("error") else "") for j in found]
    return "\n".join(lines) or "No jobs."


def _research(studio: Studio, args: dict[str, Any]) -> str:
    from ..agents.researcher import dossiers

    if args.get("path"):
        return studio.document_any(args["path"])
    found = dossiers(studio.book)
    lines = [f"- {d['slug']}: {d['title']} ({d['words']} words) — read with path {d['path']}" for d in found]
    return "\n".join(lines) or "No research yet."


def _translation(studio: Studio, args: dict[str, Any]) -> str:
    from ..translation import report

    book = studio.book
    languages = [lang for lang in book.languages if lang != book.source_language]
    if not languages:
        return f"The book has only {book.source_language}. A language is added with `add_language`."
    language = args.get("language") if args.get("language") in languages else languages[0]
    found = report(book, language, [args["section"]] if args.get("section") else None)
    g = found["glossary"]
    lines = [f"{language}, translated from {found['source_language']}: "
             + ", ".join(f"{n} {state}" for state, n in sorted(found["states"].items())) + ". "
             + (f"Glossary: {g['terms']} term(s), {g['keep']} kept name(s)." if g["present"]
                else "No glossary.yaml yet (`propose_glossary` drafts one).")]
    lines += [f"- meta.yaml {f['item']}: {f['verdict']} — {f['measured']} {f['detail']}".rstrip()
              for f in found["meta"] if f["verdict"] not in ("pass", "info")]
    for section in found["sections"]:
        waiting = f", {section['candidates']} candidate(s) to read" if section["candidates"] else ""
        lines.append(f"- {section['id']}: {section['state']}{waiting}")
        lines += [f"    {f['verdict']} {f['item']}: {f['measured']}"
                  + (f" (required {f['required']})" if f["required"] else "") + (f" — {f['detail']}" if f["detail"] else "")
                  for f in section["findings"] if f["verdict"] != "pass"]
    return "\n".join(lines)


def _plans(studio: Studio, args: dict[str, Any]) -> str:
    import json as _json

    from ..agents.architect import plans

    found = plans(studio.book)
    if not found:
        return "No plan proposed yet."
    latest = found[0]
    return f"{latest['id']} ({latest['state']}):\n" + _json.dumps(latest["plan"], ensure_ascii=False, indent=1)


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
    "style": ("writing-vice findings (register, form, the book's own decisions)", "language; section optional",
              _style),
    "jobs": ("background jobs and their results", "", _jobs),
    "research": ("the research dossiers, or one of them", "path optional (research/<slug>.md)", _research),
    "plan": ("the latest plan the architect proposed", "", _plans),
    "translation": ("a translated language against its source: each section's state (untranslated, translated, "
                    "stale, unrecorded) and what was measured", "language; section optional", _translation),
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

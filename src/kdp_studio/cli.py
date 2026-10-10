"""`kdp`: the command line. Every command works on a book directory."""

from __future__ import annotations

import argparse
import getpass
import json
import subprocess
import sys
from pathlib import Path

from . import catalog, doctor, gates
from .book import Book, Part, load_book
from .build import build_dir, build_ebook, build_print
from .checks import FAIL
from .errors import KdpStudioError
from .fidelity import compare, compare_pdfs
from .state import Actor, read_state

MARK = {"pass": "pass", "fail": "FAIL", "warn": "warn", "not_checked": " -- ", "info": "info"}


def _actor() -> Actor:
    name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
    return Actor(name or getpass.getuser(), "human")


def _languages(book: Book, requested: str | None) -> list[str]:
    return [requested] if requested else book.languages


def _editions(requested: str) -> list[str]:
    # The wrap needs the interior's page count, and the ebook embeds the cover.
    return ["print", "cover", "ebook"] if requested == "all" else [requested]


def cmd_doctor(args) -> int:
    print(doctor.report())
    return 0


def cmd_status(args) -> int:
    book = load_book(args.book)
    print(f"{book.id} — {book.author}   ({book.root})")
    for language in book.languages:
        meta = book.meta(language)
        entries = book.contents(language)
        sections = book.sections(language)
        chapters = [s for s in sections if s.kind == "chapter"]
        parts = [e for e in entries if isinstance(e, Part)]
        words = sum(s.words for s in sections)
        print(f"\n  [{language}] {meta.get('title', '')}")
        print(f"    {len(parts)} parts, {len(chapters)} chapters, {len(sections)} sections, {words:,} words")
        for edition, settings in book.editions.items():
            out = build_dir(book, language, edition)
            built = sorted(out.glob("*.pdf")) + sorted(out.glob("*.epub"))
            print(f"    {edition:6} template {settings.get('template')}: "
                  + (f"built {built[0].name}" if built else "not built"))
    state = read_state(book.root)
    print(f"\n  Gates (state revision {state['revision']}):")
    status = gates.gate_status(book)
    if not status:
        print("    none opened yet — `kdp gate open intention`")
    for gate in status:
        changed = "  ⚠ changed since" if gate["changed_since"] else ""
        print(f"    {gate['id']:24} {gate['state']:18} {gate['subject'] or '':10}{changed}")
    return 0


def cmd_templates(args) -> int:
    root = load_book(args.book).root if args.book else None
    for template in catalog.catalog(root):
        print(f"  {template.kind:6} {template.name:14} {template.source:9} {template.description}")
    return 0


def cmd_build(args) -> int:
    book = load_book(args.book)
    for language in _languages(book, args.lang):
        for edition in _editions(args.edition):
            if edition not in book.editions:
                continue
            if edition == "print":
                result = build_print(book, language, bleed=False if args.no_bleed else None)
                d = result.details
                print(f"  print [{language}] {result.output.relative_to(book.root)}  "
                      f"(overfull {d['overfull']}, underfull {d['underfull']})")
            elif edition == "cover":
                from .cover import build_cover

                d = build_cover(book, language).details
                print(f"  cover [{language}] {d['ebook']}")
                print(f"  cover [{language}] " + (f"{d['print']}  ({d['pages']} pages, spine {d['spine']}\")"
                                                  if d["print"] else "no print wrap: the interior is not built"))
            else:
                result = build_ebook(book, language)
                print(f"  ebook [{language}] {result.output.relative_to(book.root)}")
    return 0


def cmd_check(args) -> int:
    from .checks.run import run_checks

    book = load_book(args.book)
    failed = False
    for language in _languages(book, args.lang):
        for edition in _editions(args.edition):
            if edition not in book.editions:
                continue
            try:
                report = run_checks(book, language, edition)
            except KdpStudioError as error:
                print(f"  {edition} [{language}] {error.message} — `kdp build --edition {edition}`")
                failed = True
                continue
            print(f"\n  {edition} [{language}] {report['target']}")
            for f in report["findings"]:
                measured = f"  {f['measured']}" if f["measured"] else ""
                required = f"  (required {f['required']})" if f["required"] else ""
                print(f"    {MARK[f['verdict']]}  {f['item']}{measured}{required}")
                if f["detail"] and f["verdict"] != "pass":
                    print(f"          {f['detail']}")
            counts = report["summary"]
            print("    " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
            failed |= counts.get(FAIL, 0) > 0
    return 1 if failed else 0


def cmd_gate(args) -> int:
    book = load_book(args.book)
    if args.action == "list":
        for gate in gates.gate_status(book):
            print(json.dumps(gate, ensure_ascii=False))
        return 0
    if args.action == "open":
        gate = gates.open_gate(book, args.kind, args.subject or "", actor=_actor(), note=args.note or "")
        print(f"  {gate['id']} waiting: {gate['question']}")
        return 0
    decision = {"approve": "approved", "changes": "changes_requested", "reject": "rejected"}[args.action]
    gate = gates.decide_gate(book, args.gate_id, decision, actor=_actor(), rationale=args.rationale or "")
    print(f"  {gate['id']} {gate['state']}")
    return 0


def cmd_compare(args) -> int:
    before, after = Path(args.before), Path(args.after)
    if before.suffix == ".pdf":
        result = compare_pdfs(before, after)
        print(f"  pages {result['pages_before']} -> {result['pages_after']}, "
              f"{result['identical_pages']} identical")
        for change in result["text_changes"]:
            print(f"    - {change['removed'][:100]!r}\n    + {change['added'][:100]!r}")
        return 1 if result["text_changes"] else 0
    report = compare(before.read_text("utf-8"), after.read_text("utf-8"))
    print(f"  identical bytes: {report.identical_bytes}   identical words: {report.identical_words}")
    for difference in report.word_differences:
        print(f"    - {difference['removed']!r}\n    + {difference['added']!r}")
    for fact in report.facts_added:
        print(f"    fact added   {fact}")
    for fact in report.facts_removed:
        print(f"    fact removed {fact}")
    return 0 if report.ok else 1


def cmd_serve(args) -> int:
    import socket

    import uvicorn

    from .server import create_app

    root = load_book(args.book).root
    copilot_url, reason = "", ""
    if args.assistant:
        from .assistant.host import AssistantHost, unavailable_reason

        reason = unavailable_reason()
        if reason:
            print(f"  assistant off: {reason}")
        else:
            def free_port() -> int:
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", 0))
                    return probe.getsockname()[1]

            host = AssistantHost(root, free_port(), free_port())
            host.start()
            copilot_url = host.copilot_url
            print("  assistant on (model: " + __import__("os").environ.get("KDP_MODEL", "claude-cli") + ")")
    app = create_app(root, copilot_url=copilot_url, assistant_reason=reason)
    print(f"  KDP Studio: {root.name} at http://127.0.0.1:{args.port}/")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


def cmd_style(args) -> int:
    from .style import check_style

    book = load_book(args.book)
    for language in _languages(book, args.lang):
        report = check_style(book, language, args.section or None, engines=not args.no_engines).public_dict()
        coverage = report["coverage"]
        print(f"\n  [{language}] {coverage['enforced']}/{coverage['total']} practices enforced by a check")
        for name, state in report["engines"].items():
            print(f"    engine {name}: {state}")
        for finding in report["findings"]:
            print(f"    {finding['practice']:28} {finding['section']}:{finding['line']}  “{finding['match']}”"
                  + (f"  — {finding['message']}" if finding["message"] else ""))
        print("    " + (", ".join(f"{k} {v}" for k, v in sorted(report["counts"].items())) or "no findings"))
        if coverage["unenforced"]:
            print("    Still depends on a reader:")
            for item in coverage["unenforced"]:
                print(f"      - {item['id']}: {item['rule']}")
    return 0


def cmd_continuity(args) -> int:
    from .continuity import repetitions

    book = load_book(args.book)
    for language in _languages(book, args.lang):
        found = repetitions(book, language, args.min_words)
        print(f"\n  [{language}] {len(found)} passage(s) recur across sections")
        for group in found:
            where = ", ".join(str(o["number"] or o["section"]) for o in group["occurrences"])
            print(f"    {group['sections']}× ({where})  “{group['passage'][:110]}”")
    return 0


def cmd_tools(args) -> int:
    from . import tools

    if args.action == "install":
        for name in args.names:
            print(f"  {name}: {tools.install(name)}")
        return 0
    for tool in tools.TOOLS.values():
        found = tools.location(tool.name)
        print(f"  {tool.name:13} {tool.version:7} {tool.license:13} {'installed' if found else 'missing  '}  "
              f"{tool.enables}")
    return 0


def cmd_revise(args) -> int:
    from . import jobs

    book = load_book(args.book)
    job = jobs.start(book, "revise_voice", {"language": args.lang or book.source_language,
                                            "section": args.section}, _actor(), wait=True)
    print(json.dumps(job["result"] or job["error"], ensure_ascii=False, indent=2))
    return 0 if job["state"] == "done" else 1


def cmd_move(args) -> int:
    from .structure import move

    book = load_book(args.book)
    where = {k: v for k, v in (("before", args.before), ("after", args.after), ("into", args.into)) if v}
    what = {"part": args.what} if args.part else {"section": args.what}
    result = move(book, actor=_actor(), reason=args.reason, **what, **where)
    for language, impact in result["impact"].items():
        print(f"  [{language}] {len(impact['renumbered'])} chapter(s) renumbered")
        for ref in impact["references"]:
            print(f"    {ref['section']}:{ref['line']} says “{ref['says']}”, which is now {ref['now']}")
    return 0


def cmd_language(args) -> int:
    from . import jobs
    from .commands import dispatch

    book = load_book(args.book)
    if args.copy_meta:
        result = dispatch(book, "add_language", {"language": args.language, "reason": args.reason or ""}, _actor())
    else:
        job = jobs.start(book, "add_language", {"language": args.language, "reason": args.reason or ""}, _actor(),
                         wait=True)
        if job["state"] != "done":
            print(f"error: {job['error']}", file=sys.stderr)
            return 1
        result = job["result"]
    print(f"  {result['language']} added: {result['sections']} section(s) waiting for translation")
    print(f"  read manuscript/{result['language']}/meta.yaml"
          + (" (translated by the translator; the title is yours to decide)" if result["meta_translated"]
             else " (a copy of the source: translate it)"))
    if result.get("notes"):
        print(f"  translator: {result['notes']}")
    print(f"  next: kdp glossary {args.book} {result['language']} — then kdp translate {args.book} "
          f"{result['language']} <section>")
    return 0


def cmd_glossary(args) -> int:
    from . import jobs
    from .translation import glossary

    book = load_book(args.book)
    found = glossary(book)
    if found.present and not args.draft:
        for forms_a, forms_b, note in found.pairs(book.source_language, args.language):
            print(f"  {' / '.join(forms_a):34} {' / '.join(forms_b)}" + (f"   — {note}" if note else ""))
        if found.keep:
            print("  never translated: " + ", ".join(found.keep))
        return 0
    job = jobs.start(book, "propose_glossary", {"language": args.language}, _actor(), wait=True)
    if job["state"] != "done":
        print(f"error: {job['error']}", file=sys.stderr)
        return 1
    result = job["result"]
    print(f"  {result['summary']}")
    if not result["written"]:
        print(result["glossary"])
    if result["notes"]:
        print(f"  translator: {result['notes']}")
    return 0


def cmd_translate(args) -> int:
    from . import jobs

    book = load_book(args.book)
    payload = {"language": args.language, "instruction": args.instruction or ""}
    kind = "translate_section" if args.section else "translate_book"
    if args.section:
        payload["section"] = args.section
    job = jobs.start(book, kind, payload, _actor(), wait=True)
    if job["state"] != "done":
        print(f"error: {job['error']}", file=sys.stderr)
        return 1
    result = job["result"]
    for item in [result] if args.section else result["translated"]:
        counts = ", ".join(f"{v} {k}" for k, v in sorted(item["checks"].items()))
        print(f"  {item['section']:44} {item['version']}  {item['words']} words  ({counts})")
    for item in result.get("failed") or []:
        print(f"  {item['section']:44} FAILED: {item['error']}")
    for finding in result.get("findings") or []:
        print(f"    {MARK[finding['verdict']]}  {finding['item']}  {finding['measured']}"
              + (f"  (required {finding['required']})" if finding["required"] else ""))
        if finding["detail"]:
            print(f"          {finding['detail']}")
    for adaptation in result.get("adaptations") or []:
        print(f"    adapted: “{adaptation['source']}” → “{adaptation['target']}” — {adaptation['why']}")
    print(f"  candidates wait for you: kdp translation {args.book} --lang {args.language}")
    return 1 if result.get("failed") else 0


def cmd_translation(args) -> int:
    from .translation import report

    book = load_book(args.book)
    languages = [args.lang] if args.lang else [lang for lang in book.languages if lang != book.source_language]
    if not languages:
        print(f"  the book has only {book.source_language} — `kdp language add {args.book} <language>`")
        return 0
    failed = False
    for language in languages:
        found = report(book, language, args.section or None)
        g = found["glossary"]
        print(f"\n  [{language}] from {found['source_language']}: "
              + (", ".join(f"{v} {k}" for k, v in sorted(found["states"].items())) or "no sections")
              + (f"; glossary of {g['terms']} term(s), {g['keep']} kept name(s)" if g["present"]
                 else "; no glossary.yaml"))
        for f in found["meta"]:
            if f["verdict"] not in ("pass", "info") or args.all:
                print(f"    {MARK[f['verdict']]}  {f['item']}  {f['measured']}" + (f"  — {f['detail']}" if f["detail"] else ""))
        for section in found["sections"]:
            waiting = f"  ({section['candidates']} candidate(s) to read)" if section["candidates"] else ""
            ratio = f"{section['words']}/{section['source_words']} words" if section["words"] else ""
            print(f"    {section['state']:13} {section['id']:44} {ratio}{waiting}")
            for f in section["findings"]:
                if f["verdict"] != "pass" or args.all:
                    print(f"        {MARK[f['verdict']]}  {f['item']}: {f['measured']}"
                          + (f"  (required {f['required']})" if f["required"] else ""))
                    if f["detail"]:
                        print(f"              {f['detail']}")
        failed |= found["summary"].get(FAIL, 0) > 0 or found["meta_summary"].get(FAIL, 0) > 0
        failed |= any(k != "translated" for k in found["states"])
    return 1 if failed else 0


def cmd_art(args) -> int:
    from . import art

    book = load_book(args.book)
    if args.action == "add":
        if not args.file or not args.id:
            print("error: kdp art add <book> <file> --id <id>", file=sys.stderr)
            return 2
        found = art.add(book, Path(args.file), args.id, actor=_actor(), purpose=args.purpose, prompt=args.prompt or "",
                        model=args.model or "", provider=args.provider or "", seed=args.seed,
                        derived_from=args.derived_from or "", lettering=args.lettering, notes=args.notes or "")
        print(f"  {found['id']}: {found['path']}  {found['width']} × {found['height']} px")
        return 0
    for found in art.records(book):
        how = found.get("model") or ("recorded" if found["recorded"] else "not recorded")
        print(f"  {found['id']:24} {found.get('purpose', ''):13} {found['width']} × {found['height']} px  "
              f"lettering {found.get('lettering', '?'):6} {how}"
              + ("  ⚠ changed since it was recorded" if found["changed_since"] else ""))
    return 0


def cmd_new(args) -> int:
    from .structure import slug

    root = Path(args.path).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        print(f"error: {root} exists and is not empty", file=sys.stderr)
        return 2
    (root / "manuscript" / args.language).mkdir(parents=True)
    import yaml

    manifest = {"schema": 1, "id": slug(args.title), "author": args.author, "source_language": args.language,
                "languages": [args.language], "contents": [],
                "editions": {"print": {"template": "nocturne", "trim": "6x9", "paper": "cream", "bleed": True},
                             "ebook": {"template": "nocturne"}}}
    (root / "book.yaml").write_text(f"# {args.title} — a KDP Studio book (docs/book-format.md).\n"
                                    + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (root / "manuscript" / args.language / "meta.yaml").write_text(
        yaml.safe_dump({"title": args.title, "parts": {}}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    idea = args.idea or "(the idea, in the author's words)"
    (root / "intentions.md").write_text(f"# {args.title}\n\n{idea}\n", encoding="utf-8")
    (root / "style.yaml").write_text("# This book's style decisions (docs/book-format.md).\npractices: []\n",
                                     encoding="utf-8")
    (root / ".gitignore").write_text("builds/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"New book: {args.title}"], cwd=root, check=True)
    print(f"  {args.title}: {root}")
    print(f"  next: kdp serve {root} --assistant — and tell the assistant your idea")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kdp", description="KDP Studio: books from idea to KDP.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="what works on this machine").set_defaults(func=cmd_doctor)

    p = sub.add_parser("new", help="start a book from an idea")
    p.add_argument("path")
    p.add_argument("--title", required=True)
    p.add_argument("--author", required=True)
    p.add_argument("--language", default="pt-BR")
    p.add_argument("--idea", help="the idea, in your words; becomes the first intentions.md")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("status", help="a book at a glance")
    p.add_argument("book", nargs="?", default=".")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("templates", help="the edition template catalogue")
    p.add_argument("book", nargs="?")
    p.set_defaults(func=cmd_templates)

    for name, func, text in (("build", cmd_build, "build editions"), ("check", cmd_check, "measure editions")):
        p = sub.add_parser(name, help=text)
        p.add_argument("book", nargs="?", default=".")
        p.add_argument("--lang")
        p.add_argument("--edition", choices=["print", "ebook", "cover", "all"], default="all")
        if name == "build":
            p.add_argument("--no-bleed", action="store_true", help="a reading proof without bleed")
        p.set_defaults(func=func)

    p = sub.add_parser("gate", help="human gates")
    gate_sub = p.add_subparsers(dest="action", required=True)
    g = gate_sub.add_parser("list")
    g.add_argument("book", nargs="?", default=".")
    g = gate_sub.add_parser("open")
    g.add_argument("kind", choices=sorted(gates.KINDS))
    g.add_argument("subject", nargs="?")
    g.add_argument("--book", default=".")
    g.add_argument("--note")
    for action in ("approve", "changes", "reject"):
        g = gate_sub.add_parser(action)
        g.add_argument("gate_id")
        g.add_argument("--book", default=".")
        g.add_argument("--rationale", "-m")
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("style", help="the writing-vice catalogue, checked")
    p.add_argument("book", nargs="?", default=".")
    p.add_argument("--lang")
    p.add_argument("--section", action="append")
    p.add_argument("--no-engines", action="store_true", help="only the catalogue's own checks")
    p.set_defaults(func=cmd_style)

    p = sub.add_parser("continuity", help="passages that recur across sections")
    p.add_argument("book", nargs="?", default=".")
    p.add_argument("--lang")
    p.add_argument("--min-words", type=int, default=7)
    p.set_defaults(func=cmd_continuity)

    p = sub.add_parser("revise", help="the voice reviser on one section: a candidate version")
    p.add_argument("book")
    p.add_argument("section")
    p.add_argument("--lang")
    p.set_defaults(func=cmd_revise)

    p = sub.add_parser("move", help="reorder: a section (or --part) before/after another, or into a part")
    p.add_argument("book")
    p.add_argument("what", help="the section id (or the part id, with --part)")
    p.add_argument("--part", action="store_true")
    p.add_argument("--before")
    p.add_argument("--after")
    p.add_argument("--into", help="the part to append the section to")
    p.add_argument("--reason", "-m", required=True)
    p.set_defaults(func=cmd_move)

    p = sub.add_parser("art", help="the book's pictures (cover art, illustrations), each with how it was made")
    p.add_argument("action", choices=["list", "add"])
    p.add_argument("book")
    p.add_argument("file", nargs="?")
    p.add_argument("--id")
    p.add_argument("--purpose", choices=["cover", "illustration"], default="cover")
    p.add_argument("--lettering", choices=["none", "baked"], default="none",
                   help="baked: the picture already carries words")
    p.add_argument("--prompt")
    p.add_argument("--model")
    p.add_argument("--provider")
    p.add_argument("--seed", type=int)
    p.add_argument("--derived-from", help="the art id this picture was made from")
    p.add_argument("--notes")
    p.set_defaults(func=cmd_art)

    p = sub.add_parser("language", help="add a language to the book (meta.yaml and a stub per section)")
    p.add_argument("action", choices=["add"])
    p.add_argument("book")
    p.add_argument("language")
    p.add_argument("--copy-meta", action="store_true", help="copy the source meta.yaml instead of translating it")
    p.add_argument("--reason", "-m")
    p.set_defaults(func=cmd_language)

    p = sub.add_parser("glossary", help="the book's bilingual glossary; drafted by the translator when it has none")
    p.add_argument("book")
    p.add_argument("language")
    p.add_argument("--draft", action="store_true", help="ask for a draft even when glossary.yaml exists (printed)")
    p.set_defaults(func=cmd_glossary)

    p = sub.add_parser("translate", help="the translator: one section, or every pending one, as candidate versions")
    p.add_argument("book")
    p.add_argument("language")
    p.add_argument("section", nargs="?")
    p.add_argument("--instruction", "-m")
    p.set_defaults(func=cmd_translate)

    p = sub.add_parser("translation", help="a translated language measured against its source")
    p.add_argument("book", nargs="?", default=".")
    p.add_argument("--lang")
    p.add_argument("--section", action="append")
    p.add_argument("--all", action="store_true", help="also what passed")
    p.set_defaults(func=cmd_translation)

    p = sub.add_parser("tools", help="open tools KDP Studio uses (Vale, LanguageTool, EPUBCheck)")
    p.add_argument("action", choices=["list", "install"], nargs="?", default="list")
    p.add_argument("names", nargs="*")
    p.set_defaults(func=cmd_tools)

    p = sub.add_parser("serve", help="the control room, on this machine")
    p.add_argument("book", nargs="?", default=".")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--assistant", action="store_true", help="the LangGraph assistant through CopilotKit")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("compare", help="fidelity: did the words change? (Markdown or PDF)")
    p.add_argument("before")
    p.add_argument("after")
    p.set_defaults(func=cmd_compare)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KdpStudioError as error:
        print(f"error [{error.code}]: {error.message}", file=sys.stderr)
        for key, value in error.details.items():
            print(f"  {key}: {value}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

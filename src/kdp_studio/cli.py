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
from .build import build_dir, build_ebook, build_print, edition_settings
from .checks import FAIL, summary
from .checks.epub import check_epub
from .checks.kdp_print import check_print
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
    return ["print", "ebook"] if requested == "all" else [requested]


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
            else:
                result = build_ebook(book, language)
                print(f"  ebook [{language}] {result.output.relative_to(book.root)}")
    return 0


def cmd_check(args) -> int:
    book = load_book(args.book)
    failed = False
    for language in _languages(book, args.lang):
        for edition in _editions(args.edition):
            if edition not in book.editions:
                continue
            out = build_dir(book, language, edition)
            if edition == "print":
                pdfs = sorted(out.glob("*.pdf"))
                if not pdfs:
                    print(f"  print [{language}] not built — `kdp build --edition print`")
                    failed = True
                    continue
                settings = edition_settings(book, "print")
                template = catalog.get("print", settings["template"], book.root)
                paper = template.meta["trims"][settings.get("trim", "6x9")]["paper"]
                trim = tuple(float(v.removesuffix("in")) for v in paper)
                findings = check_print(pdfs[0], trim=trim, bleed=pdfs[0].stem.endswith("-bleed"),
                                       paper=settings.get("paper", "white"), log=out / "book.log")
                target = pdfs[0]
            else:
                epubs = sorted(out.glob("*.epub"))
                if not epubs:
                    print(f"  ebook [{language}] not built — `kdp build --edition ebook`")
                    failed = True
                    continue
                findings = check_epub(epubs[0])
                target = epubs[0]
            print(f"\n  {edition} [{language}] {target.relative_to(book.root)}")
            for f in findings:
                measured = f"  {f.measured}" if f.measured else ""
                required = f"  (required {f.required})" if f.required else ""
                print(f"    {MARK[f.verdict]}  {f.item}{measured}{required}")
                if f.detail and f.verdict != "pass":
                    print(f"          {f.detail}")
            counts = summary(findings)
            print("    " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
            (out / "check.json").write_text(json.dumps([f.public_dict() for f in findings], ensure_ascii=False,
                                                       indent=2), encoding="utf-8")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kdp", description="KDP Studio: books from idea to KDP.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="what works on this machine").set_defaults(func=cmd_doctor)

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
        p.add_argument("--edition", choices=["print", "ebook", "all"], default="all")
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

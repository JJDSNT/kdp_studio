"""The designer: a new theme from a brief and from references, checked by building it.

It works from what exists -- an *internal* reference, a theme of the
catalogue it starts from -- and, when the author points at one, an *external*
reference: a page on the web (a template gallery, a publisher's book). From
an external reference it takes the design -- proportions, hierarchy, how a
chapter opens, the temperament of the page -- and writes its own code; it
records where it looked, under what licence, and what it took. Code is
copied only where the licence allows it, and that is said.

It answers with blocks, not with a file (ADR 0009): the fonts, the part
opening, the chapter head, the section head, the palette, what the ebook
adds. KDP Studio assembles them over the base theme, refuses what a template
has no business doing, and **builds the specimen with the result**: a theme
that does not compile is sent back with the error, and one that still does
not is not catalogued. What passes joins the person's own catalogue and
shows in the gallery beside the others.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from .. import catalog, gallery
from ..book import Book
from ..errors import KdpStudioError, ValidationError
from ..jobs import Progress, kind
from ..model import Model, model_from_env
from ..state import Actor, now

AGENT = Actor("designer", "agent")
_NAME = re.compile(r"[a-z][a-z0-9-]{1,30}")
ROLES = ("ink", "night", "deep", "cold", "cold_dark", "warm", "warm_dark", "shade", "shade_light", "grey", "cream",
         "rule")
COVER_ROLES = ("night", "cream", "cold", "warm", "grey")
MARK = "% ---------------------------------------------------------------- "
#: What a template has no business doing: running code, reading or writing other files.
FORBIDDEN = (r"\directlua", r"\write18", r"\input", r"\include", r"\openout", r"\openin", r"\immediate",
             r"\catcode", r"\csname", r"\luaexec", r"\ShellEscape", r"\usepackage", r"\RequirePackage")
CSS_FORBIDDEN = ("@import", "url(", "expression(", "<", "javascript:")

SYSTEM = (
    "You are the designer of a book production tool: you draw a THEME — how a book looks in print, as an ebook "
    "and on its cover — from the author's brief. You do not write a template from nothing: you answer with the "
    "blocks that give a theme its character, and the tool assembles them over a base theme and builds a specimen "
    "book with the result. Design as a book designer does: decide the temperament first, then let two or three "
    "decisions carry it everywhere (a face, an alignment, one accent). A theme must differ from the base by "
    "more than its colours.\n\n"
    "References. The base theme is your internal reference: its blocks are below, and they are the syntax to "
    "follow. When the author gives a web address, open it and look: from an external reference you take the "
    "DESIGN — proportions, hierarchy, how a part and a chapter open, the mood — and write your own code. Find "
    "the licence the page states and record it in `references`, with what you took. Copy code from it only "
    "when the licence clearly allows adaptation (public domain, MIT, LPPL, CC BY, CC BY-SA), and say so; with "
    "no licence stated, or a non-commercial or no-derivatives one, take ideas only. Never claim an endorsement.\n\n"
    "The blocks, all LaTeX for LuaLaTeX with the memoir class and fontspec:\n"
    "- `fonts`: \\setmainfont, \\newfontfamily\\displayfont (heads, numbers), \\newfontfamily\\labelfont (small "
    "labels, always letterspaced through the font), \\setmonofont. Use ONLY the installed families listed; "
    "fontspec is loaded by the tool.\n"
    "- `parts`: the part opening: \\partnamefont, \\partnumfont, \\parttitlefont, \\printparttitle, "
    "\\printpartname, \\printpartnum, \\midpartskip, \\beforepartskip, \\afterpartskip. A ground from edge to "
    "edge uses \\AddToShipoutPictureBG* as the base does, and then `needs_bleed` is true.\n"
    "- `chapter_style`: \\makechapterstyle{NAME}{…} then \\chapterstyle{NAME}, NAME being the theme's name. The "
    "label (\"Chapter 4\") arrives in \\kdpchapterlabel and is printed inside \\printchaptertitle, as in the "
    "base; write ## for # inside it.\n"
    "- `section_head`: one \\setsecheadstyle{…} line.\n"
    "- `palette`: twelve colours by ROLE, six hex digits each: ink (text), deep (heads), cold (the accent of "
    "the narrative) and cold_dark (the same, for small type), warm and warm_dark (the accent of exercises), "
    "shade and shade_light (grounds of an exercise and of a prompt), grey, cream, rule (hairlines), night (a "
    "dark ground). Small type in an accent must stay readable on white.\n"
    "- `css_extra`: CSS added to the base ebook stylesheet (already recoloured with your palette) to carry the "
    "same decisions: alignment, weights, rules. Its classes: h1 (chapter title), h2–h4, .chapter-label, "
    ".front-label, .chapter-rule, .part-opening, .part-label, .part-rule, .part-title, .title-page, .subtitle, "
    ".tagline, .callout, .callout-label, .callout-title, .callout-framework, section.exercise, .exercise-label, "
    ".exercise-title, .sublabel, .prompt, .prompt-label, .prompt-text. Never a background on body; never a "
    "distinction by colour alone.\n"
    "- `cover_palette`: night (the cover's ground), cream (the words on it), cold (the accent), warm, grey; "
    "`cover_display_font` and `cover_text_font` from the installed families.\n"
    "Do not load packages, read files or run code: such blocks are refused. Colour names in LaTeX are the roles "
    "without the underscore (colddark, warmdark, shadelight), plus white and black."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "fonts": {"type": "string"},
        "parts": {"type": "string"},
        "chapter_style": {"type": "string"},
        "section_head": {"type": "string"},
        "needs_bleed": {"type": "boolean"},
        "palette": {"type": "object", "properties": {role: {"type": "string"} for role in ROLES},
                    "required": list(ROLES)},
        "css_extra": {"type": "string"},
        "cover_palette": {"type": "object", "properties": {role: {"type": "string"} for role in COVER_ROLES},
                          "required": list(COVER_ROLES)},
        "cover_display_font": {"type": "string"},
        "cover_text_font": {"type": "string"},
        "references": {"type": "array", "items": {"type": "object", "properties": {
            "url": {"type": "string"}, "title": {"type": "string"}, "license": {"type": "string"},
            "taken": {"type": "string"}}, "required": ["url", "title", "license", "taken"]}},
        "notes": {"type": "string"},
    },
    "required": ["title", "description", "fonts", "parts", "chapter_style", "section_head", "needs_bleed",
                 "palette", "css_extra", "cover_palette", "cover_display_font", "cover_text_font", "references",
                 "notes"],
}


def installed_fonts() -> list[str]:
    """Font families this machine can typeset with (fontconfig); empty when it cannot say."""

    if not shutil.which("fc-list"):
        return []
    run = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True)
    return sorted({line.split(",")[0].strip() for line in run.stdout.splitlines() if line.strip()})


def _slice(text: str, start: str, end: str) -> tuple[int, int]:
    try:
        a = text.index(start)
        return a, text.index(end, a)
    except ValueError:
        raise ValidationError("This theme cannot be a base: its print template does not have the sections "
                              "the designer replaces") from None


def base_blocks(print_template: str) -> dict[str, str]:
    """The blocks of a base theme the designer is shown, and replaces."""

    fonts = _slice(print_template, MARK + "fonts", MARK + "micro")
    parts = _slice(print_template, MARK + "parts", MARK + "chapters")
    style = _slice(print_template, r"\newcommand{\kdpchapterlabel}{}", r"\setsecnumdepth{part}")
    head = re.search(r"\\setsecheadstyle\{.*\}\n", print_template)
    if head is None:
        raise ValidationError("This theme cannot be a base: it sets no section head")
    return {"fonts": print_template[fonts[0]:fonts[1]], "parts": print_template[parts[0]:parts[1]],
            "chapter_style": print_template[style[0]:style[1]], "section_head": head.group(0)}


def _hex(value: Any, what: str) -> str:
    text = str(value).strip().lstrip("#").upper()
    if not re.fullmatch(r"[0-9A-F]{6}", text):
        raise ValidationError(f"{what}: {value!r} is not a colour (six hex digits)")
    return text


def _refuse(block: str, what: str) -> None:
    found = [word for word in FORBIDDEN if word in block]
    if found:
        raise ValidationError(f"The {what} block does what a template may not: {', '.join(found)}")


def _fonts_named(block: str) -> list[str]:
    return re.findall(r"\\(?:setmainfont|setsansfont|setmonofont|newfontfamily\\[A-Za-z]+)\s*\{([^}]+)\}", block)


def assemble(name: str, base: str, answer: dict[str, Any], destination: Path, *, brief: str = "") -> dict[str, Any]:
    """Write the theme's three templates from the base theme and the designer's blocks."""

    templates = {kind_: catalog.get(kind_, base) for kind_ in gallery.KINDS}
    source = (templates["print"].path / "book.tex.j2").read_text("utf-8")
    blocks = base_blocks(source)
    # fontspec is the one package a fonts block needs; the tool loads it, so the block need not.
    answer = {**answer, "fonts": re.sub(r"\\usepackage\{fontspec\}\s*", "", str(answer["fonts"]))}
    for key in ("fonts", "parts", "chapter_style", "section_head"):
        _refuse(str(answer[key]), key)
    fonts = installed_fonts()
    named = _fonts_named(str(answer["fonts"])) + [str(answer["cover_display_font"]), str(answer["cover_text_font"])]
    missing = sorted({font for font in named if fonts and font not in fonts})
    if missing:
        raise ValidationError("Fonts that are not installed here: " + ", ".join(missing))
    if f"\\makechapterstyle{{{name}}}" not in str(answer["chapter_style"]) or \
            f"\\chapterstyle{{{name}}}" not in str(answer["chapter_style"]):
        raise ValidationError(f"chapter_style must define and select the chapter style {name!r}")
    if not str(answer["section_head"]).strip().startswith("\\setsecheadstyle{"):
        raise ValidationError("section_head must be one \\setsecheadstyle{…} line")
    css_extra = str(answer.get("css_extra") or "")
    bad = [word for word in CSS_FORBIDDEN if word in css_extra]
    if bad:
        raise ValidationError(f"css_extra does what an ebook stylesheet may not: {', '.join(bad)}")
    palette = {role: _hex(answer["palette"][role], f"palette.{role}") for role in ROLES}
    cover_palette = {role: _hex(answer["cover_palette"][role], f"cover_palette.{role}") for role in COVER_ROLES}

    text = source
    text = text.replace(blocks["fonts"], MARK + "fonts\n\\usepackage{fontspec}\n" + str(answer["fonts"]).strip()
                        + "\n\n")
    part_macros = ("\n\\aliaspagestyle{part}{empty}\n\n\\newcommand{\\kdppart}[2]{\\part{#2}}\n"
                   "\\newcommand{\\kdpunnumberedpart}[2]{%\n  \\cleartorecto\n  \\addcontentsline{toc}{part}{#1}%\n"
                   "  \\part*{#2}}\n\n")
    eso = "\\usepackage{eso-pic}\n" if "AddToShipoutPicture" in str(answer["parts"]) else ""
    text = text.replace(blocks["parts"], MARK + "parts\n" + eso + str(answer["parts"]).strip() + part_macros)
    text = text.replace(blocks["chapter_style"], "\\newcommand{\\kdpchapterlabel}{}\n"
                        + str(answer["chapter_style"]).strip() + "\n")
    text = text.replace(blocks["section_head"], str(answer["section_head"]).strip() + "\n")
    text = re.sub(r"\A\(\(=.*?=\)\)", f"((= {answer['title']} — print template, drawn by the designer over {base}. "
                  "See docs/templates.md for the contract. =))", text, count=1, flags=re.S)
    text = re.sub(rf"\b{re.escape(base)}(note|framework|exercise|chapter)?\b",
                  lambda m: name + (m.group(1) or ""), text)

    provenance: dict[str, Any] = {"designed_by": "designer", "designed_at": now(), "based_on": base}
    if brief.strip():
        provenance["brief"] = brief.strip()
    if answer.get("references"):
        provenance["inspired_by"] = [dict(reference) for reference in answer["references"]]
    base_palette = {role: str(value).upper() for role, value in (templates["print"].meta.get("colors") or {}).items()}

    def manifest(kind_: str, more: dict[str, Any]) -> str:
        data = {"name": name, "kind": kind_, "title": str(answer["title"]), "description": str(answer["description"]),
                **more, **provenance}
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)

    for kind_ in gallery.KINDS:
        folder = destination / kind_ / name
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
    (destination / "print" / name / "book.tex.j2").write_text(text, encoding="utf-8")
    (destination / "print" / name / "template.yaml").write_text(manifest("print", {
        "engine": "lualatex", "fonts": sorted(set(_fonts_named(str(answer["fonts"])))),
        "trims": templates["print"].meta.get("trims"), "colors": palette,
        "needs_bleed": bool(answer["needs_bleed"])}), encoding="utf-8")
    css = (templates["ebook"].path / "style.css").read_text("utf-8")
    # The base stylesheet names its colours by value: each becomes the new colour of the same role.
    css = re.sub(r"#([0-9A-Fa-f]{6})\b", lambda m: "#" + next(
        (palette[role] for role, value in base_palette.items() if value == m.group(1).upper() and role in palette),
        m.group(1)), css)
    (destination / "ebook" / name / "style.css").write_text(
        css + f"\n/* {answer['title']}: what this theme adds. */\n" + css_extra.strip() + "\n", encoding="utf-8")
    (destination / "ebook" / name / "template.yaml").write_text(manifest("ebook", {}), encoding="utf-8")
    cover = (templates["cover"].path / "cover.tex.j2").read_text("utf-8")
    cover = re.sub(r"(\\newfontfamily\\(?:displayfont|spacedfont)\{)[^}]*(\})",
                   lambda m: m.group(1) + str(answer["cover_display_font"]) + m.group(2), cover)
    cover = re.sub(r"(\\setmainfont\{)[^}]*(\})", lambda m: m.group(1) + str(answer["cover_text_font"]) + m.group(2),
                   cover)
    cover = cover.replace("UprightFont=*-Bold", "")
    (destination / "cover" / name / "cover.tex.j2").write_text(cover, encoding="utf-8")
    cover_meta = {key: templates["cover"].meta[key] for key in ("scrim", "edge_fade", "margin")
                  if key in templates["cover"].meta}
    (destination / "cover" / name / "template.yaml").write_text(manifest("cover", {
        "engine": "lualatex", "fonts": sorted({str(answer["cover_display_font"]), str(answer["cover_text_font"])}),
        "colors": cover_palette, **cover_meta}), encoding="utf-8")
    return provenance


DESIGN = "design.json"


def _record(name: str) -> Path:
    return catalog.user_root() / "print" / name / DESIGN


def design_theme(book: Book, name: str, brief: str, *, based_on: str = "nocturne", reference: str = "",
                 language: str = "", model: Model | None = None, attempts: int = 3, critic: Model | None = None,
                 rounds: int = 0, look: bool = False, revising: dict[str, Any] | None = None,
                 instruction: str = "", progress=lambda message: None) -> dict[str, Any]:
    """Draw a theme (or, with `revising`, draw one again from its last answer and an instruction).

    With `look`, a critic looks at the built pages once and its criticism is kept beside the theme: the
    work then stops, and drawing again is the author's call. `rounds` lets the designer answer the critic
    by itself that many times -- never the default, because a person has not read the criticism yet.
    """

    if not _NAME.fullmatch(name):
        raise ValidationError(f"{name!r} is not a theme name (lowercase letters, digits and hyphens)")
    if not brief.strip():
        raise ValidationError("A theme starts from a brief: what the book is and how it should feel")
    taken = {theme["name"] for theme in gallery.themes(book.root)}
    if name in taken and revising is None:
        raise ValidationError(f"A theme named {name!r} exists; nothing is replaced — give this one another name")
    if based_on not in taken:
        raise ValidationError(f"No theme {based_on!r} to start from", available=sorted(taken))
    language = language or book.source_language
    source = (catalog.get("print", based_on).path / "book.tex.j2").read_text("utf-8")
    blocks = base_blocks(source)
    base_meta = catalog.get("print", based_on).meta
    fonts = installed_fonts()
    others = "\n".join(f"- {theme['name']}: {theme['kinds'].get('print', {}).get('description', '')}"
                       for theme in gallery.themes(book.root))
    prompt = (f"The theme's name: {name}\n\nThe author's brief:\n{brief.strip()}\n\n"
              + (f"External reference to open and look at: {reference}\n\n" if reference else "")
              + f"Themes the catalogue already has (be different from each):\n{others}\n\n"
              f"Installed font families (use only these):\n{', '.join(fonts) or '(unknown: use TeX Gyre families)'}\n\n"
              f"The base theme, {based_on}. Its palette:\n{yaml.safe_dump(base_meta.get('colors'), sort_keys=False)}\n"
              f"Its `fonts` block:\n{blocks['fonts']}\nIts `parts` block (the three \\kdp… macros at its end are "
              f"added by the tool; leave them out):\n{blocks['parts']}\nIts `chapter_style` block:\n"
              f"{blocks['chapter_style']}\nIts `section_head`:\n{blocks['section_head']}")
    import json

    from . import critic as critics

    chosen = model or model_from_env()
    destination = catalog.user_root()
    kept = destination.with_name("templates.keep") / name
    answer: dict[str, Any] = dict(revising or {})
    history: list[dict[str, Any]] = []
    if revising is not None and _record(name).is_file():
        history = json.loads(_record(name).read_text("utf-8")).get("history", [])
    request = instruction.strip()
    verdicts: list[dict[str, Any]] = []
    render: dict[str, Any] = {}
    provenance: dict[str, Any] = {}
    attempt = 0
    for round_ in range(rounds + 1):
        problem = ""
        previous = answer
        # What stands is set aside: a revision that does not build must not cost the theme it revises.
        if kept.exists():
            shutil.rmtree(kept)
        for kind_ in gallery.KINDS:
            if (destination / kind_ / name).is_dir():
                shutil.copytree(destination / kind_ / name, kept / kind_)
        for attempt in range(1, attempts + 1):
            progress(("Revising" if previous else "Drawing") + f" {name}"
                     + (f" (attempt {attempt}: {problem[:80]})" if problem else ""))
            ask = prompt
            if previous:
                ask += ("\n\nYou already drew this theme. Your answer was:\n"
                        + json.dumps({k: v for k, v in previous.items() if k != "notes"}, ensure_ascii=False)
                        + f"\n\nRevise it — answer again in full, changing what this asks and keeping the rest:\n"
                          f"{request}")
            if problem:
                ask += f"\n\nYour last answer did not build. Fix it and answer again in full.\nThe error:\n{problem}"
            answer = chosen.ask(SYSTEM, ask, SCHEMA, web=bool(reference) and not previous)
            try:
                provenance = assemble(name, based_on, answer, destination, brief=brief)
                if previous.get("references") and not answer.get("references"):
                    answer["references"] = previous["references"]
                progress("Building the specimen with it")
                render = gallery.build(name, language, book.root)
                problem = ""
                break
            except KdpStudioError as error:
                problem = error.message + ("\n" + str(error.details.get("log_tail", "")) if error.details else "")
                for kind_ in gallery.KINDS:
                    shutil.rmtree(destination / kind_ / name, ignore_errors=True)
        if problem:
            for kind_ in gallery.KINDS:  # back to what stood before this round, if anything did
                if (kept / kind_).is_dir():
                    shutil.copytree(kept / kind_, destination / kind_ / name)
            shutil.rmtree(kept, ignore_errors=True)
            if not previous:
                raise ValidationError(f"The theme {name!r} did not build after {attempts} attempt(s), and was not "
                                      f"catalogued: {problem[:600]}")
            raise ValidationError(f"The revision of {name!r} did not build after {attempts} attempt(s); the theme "
                                  f"stays as it was: {problem[:600]}")
        shutil.rmtree(kept, ignore_errors=True)
        history.append({"at": now(), "instruction": request, "answer": answer})
        _record(name).write_text(json.dumps({"name": name, "brief": brief, "based_on": based_on,
                                             "reference": reference, "history": history},
                                            ensure_ascii=False, indent=2), encoding="utf-8")
        if round_ == rounds:
            break
        seen = critics.critique(book, name, language=language, brief=brief, model=critic, progress=progress)
        verdicts.append(seen)
        if seen["verdict"] == "accept":
            break
        request = critics.as_instruction(seen)
    if rounds and (not verdicts or verdicts[-1]["verdict"] != "accept") and len(verdicts) == rounds:
        # The last drawing answered a criticism: it is looked at too, so what is shown is about what stands.
        verdicts.append(critics.critique(book, name, language=language, brief=brief, model=critic,
                                         progress=progress))
    if look and not rounds:
        verdicts.append(critics.critique(book, name, language=language, brief=brief, model=critic,
                                         progress=progress))
    progress(f"{name} is in your catalogue and in the gallery")
    return {"theme": name, "title": answer["title"], "description": answer["description"], "based_on": based_on,
            "references": provenance.get("inspired_by", []), "notes": answer.get("notes", ""),
            "overfull": render.get("overfull", 0), "underfull": render.get("underfull", 0),
            "path": str(destination), "attempts": attempt, "drawings": len(history),
            "critiques": [{k: v[k] for k in ("verdict", "defects", "overall")} for v in verdicts],
            "summary": f"Theme {answer['title']} ({name}) built over the specimen and joined the gallery. "
                       "Look at it before taking it."}


def revise_theme(book: Book, name: str, instruction: str = "", *, language: str = "", model: Model | None = None,
                 critic: Model | None = None, rounds: int = 0, look: bool = False,
                 progress=lambda message: None) -> dict[str, Any]:
    """Draw one of the person's themes again: as they ask, or — with no instruction — as its last criticism asks."""

    import json

    from . import critic as critics

    path = _record(name)
    if not path.is_file():
        raise ValidationError(f"{name!r} is not a theme the designer drew: only those can be revised by it")
    record = json.loads(path.read_text("utf-8"))
    if not instruction.strip():
        last = critics.latest(name)
        if last is None:
            raise ValidationError("Say what to change, or have the critic look at the theme first")
        instruction = critics.as_instruction(last)
    return design_theme(book, name, record["brief"], based_on=record["based_on"], reference=record.get("reference", ""),
                        language=language, model=model, critic=critic, rounds=rounds, look=look,
                        revising=record["history"][-1]["answer"], instruction=instruction, progress=progress)


def remove_theme(name: str) -> dict[str, Any]:
    """Out of the person's catalogue. A book that took the theme keeps its own copy."""

    removed = []
    for kind_ in gallery.KINDS:
        folder = catalog.user_root() / kind_ / name
        if folder.is_dir():
            shutil.rmtree(folder)
            removed.append(kind_)
    if not removed:
        raise ValidationError(f"{name!r} is not in your catalogue (built-in themes cannot be removed)")
    return {"theme": name, "removed": removed}


@kind("revise_theme", "Designer: draw one of your themes again, as you ask or as its last criticism asks")
def revise_theme_job(book: Book, payload: dict[str, Any], actor: Actor, progress: Progress) -> dict[str, Any]:
    return revise_theme(book, payload["theme"], payload.get("instruction", ""), language=payload.get("language", ""),
                        rounds=int(payload.get("rounds", 0)), look=bool(payload.get("look", True)),
                        progress=progress)


@kind("design_theme", "Designer: a new theme from a brief and references, built over the specimen and catalogued")
def design_theme_job(book: Book, payload: dict[str, Any], actor: Actor, progress: Progress) -> dict[str, Any]:
    return design_theme(book, payload["name"], payload.get("brief", ""), based_on=payload.get("based_on") or "nocturne",
                        reference=payload.get("reference", ""), language=payload.get("language", ""),
                        rounds=int(payload.get("rounds", 0)), look=bool(payload.get("look", True)),
                        progress=progress)
